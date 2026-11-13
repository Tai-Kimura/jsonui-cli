# frozen_string_literal: true

require 'json'
require 'open3'
require 'tmpdir'
require_relative '../support/js_templates'

# The web's reorder helper (lib/react/templates/reorder.tsx) drags by the rule the three runtimes share,
# shared/core/reorder_vectors.json (ticket jui-collection-drag-to-reorder, ruling B 2026-11-13): which `to` a drag
# means, the release (inside the Collection decides, over the header the first place, over the footer the last,
# outside cancels), the auto-scroll speed and the screen reader's move up / move down. The template's own rule
# functions are bundled with esbuild (React stubbed: only the pure functions run) and run against every vector.
RSpec.describe 'the web reorder helper and shared/core/reorder_vectors.json' do
  template = File.expand_path('../../lib/react/templates/reorder.tsx', __dir__)
  vectors = File.expand_path('../../../shared/core/reorder_vectors.json', __dir__)

  def run_vectors(template, vectors)
    Dir.mktmpdir('reorder-shim') do |dir|
      shim = File.join(dir, 'react.js')
      File.write(shim, 'module.exports = { createContext: () => ({}), useContext() {}, useEffect() {}, ' \
                       'useMemo() {}, useRef() {}, useState() {} };')
      return run_with_shim(template, vectors, shim)
    end
  end

  def run_with_shim(template, vectors, shim)
    script = <<~JS
      const esbuild = require(#{JSON.generate(JsTemplates.esbuild_module)});
      const out = esbuild.buildSync({
        entryPoints: [#{JSON.generate(template)}], bundle: true, write: false, format: 'cjs', platform: 'node',
        jsx: 'transform', alias: { react: #{JSON.generate(shim)} },
      });
      const m = {}; new Function('module', 'exports', 'require', out.outputFiles[0].text)(m, m.exports = {}, require);
      const R = m.exports;
      const V = JSON.parse(require('fs').readFileSync(#{JSON.generate(vectors)}, 'utf8'));
      const bad = [];
      const check = (section, name, got, want) => { if (JSON.stringify(got) !== JSON.stringify(want)) bad.push(`${section}: ${name}: got ${got}, want ${want}`); };
      let n = 0;
      for (const v of V.drag) { n++; check('drag', v.name, R.jsonuiReorderDragTo(v.heights, v.from, v.dy, v.locked || []), v.to); }
      for (const v of V.release) { n++; check('release', v.name, R.jsonuiReorderRelease(v.heights, v.from, v.grabAt, v.dy, v.locked || [], v.header, v.footer), v.cancelled ? null : v.to); }
      for (const v of V.autoScroll) { n++; const got = R.jsonuiReorderAutoScroll(v.viewport, v.fingerY); check('autoScroll', v.name, Math.abs(got - v.speed) < 1e-9 ? v.speed : got, v.speed); }
      for (const v of V.a11y) { n++; check('a11y', v.name, R.jsonuiReorderA11y(v.rows, v.from, v.action, v.locked || []), v.to); }
      process.stdout.write(JSON.stringify({ n, bad }));
    JS
    out, err, status = Open3.capture3('node', '-e', script)
    raise "node: #{err}" unless status.success?

    JSON.parse(out)
  end

  it 'agrees with every drag, release, auto-scroll and screen-reader vector' do
    reason = JsTemplates.unavailable_reason
    skip reason if reason

    result = run_vectors(template, vectors)
    data = JSON.parse(File.read(vectors))
    expect(result['n']).to eq(%w[drag release autoScroll a11y].sum { |k| data[k].size })
    expect(result['bad']).to eq([])
  end
end
