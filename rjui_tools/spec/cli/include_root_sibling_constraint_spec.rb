# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'
require 'rbconfig'
require_relative '../spec_helper'
require_relative '../support/headless_chromium'
require 'core/config_manager'

# An included layout's root constrained against a sibling of the include
# (alignTopOfView and the other nine) is laid out against that sibling, as
# sjui and kjui (which expand the include first) lay it out (ticket
# rjui-include-root-sibling-constraint-dropped). Measured on v2.5.24 in
# Chromium, a 20x20 root and a 10x10 anchor at margin 50/50 in a 100x100
# frame: the direct child drew at (0,30) for alignTopOfView, (50,0) for
# alignLeftView, (0,45) for alignCenterVerticalView; the include's root drew
# at (0,0) for every one of the ten — the container never saw the constraint,
# and the hoisted applyRelativePositions had no spec for it. Under an include
# with an id the root carries the prefixed id; the anchor, a sibling of the
# include, does not.
#
# Each project is built by a copied rjui (jui build's prefix decision on);
# its generated components, with the helpers they call, are drawn in
# headless Chromium by a small element factory that runs the components'
# effects after mounting (include_reads_the_including_data_spec.rb takes the
# same route through esbuild).
RSpec.describe 'an included root constrained against a sibling of the include, through rjui build' do
  IRSC_RJUI_ROOT = File.expand_path('../..', __dir__)
  IRSC_SUPPORT = File.expand_path('../support', __dir__)
  IRSC_NODE_MODULES = File.join(IRSC_SUPPORT, 'node_modules')

  def self.box(id, extra = {})
    { 'type' => 'View', 'id' => id, 'width' => 20, 'height' => 20, 'background' => '#FF0000' }.merge(extra)
  end

  def self.anchor(id) = box(id, 'width' => 10, 'height' => 10, 'leftMargin' => 50, 'topMargin' => 50, 'background' => '#00AA00')

  def self.frame(key, kids)
    { 'type' => 'View', 'width' => 120, 'height' => 120,
      'child' => [{ 'type' => 'View', 'id' => "frame_#{key}", 'width' => 100, 'height' => 100, 'child' => kids }] }
  end

  # key => [constraint attribute, include id or nil, nested (the partial's
  # root is itself an include)]
  IRSC_CASES = {
    'ato' => ['alignTopOfView', nil, false],
    'aro' => ['alignRightOfView', nil, false],
    'al' => ['alignLeftView', nil, false],
    'ab' => ['alignBottomView', nil, false],
    'acv' => ['alignCenterVerticalView', nil, false],
    'idato' => ['alignTopOfView', 'inc', false],
    'nest' => ['alignTopOfView', 'outer', true],
    # row D4: both elements inside the partial, the include with an id —
    # the elements carry `incS…` / `incA…` and the constraint has to name
    # them so
    'inner' => ['alignTopOfView', 'inc', :inner],
    'innerl' => ['alignLeftView', 'inc', :inner]
  }.freeze

  def self.layouts
    files = {}
    frames = []
    IRSC_CASES.each do |key, (attr, include_id, nested)|
      %w[direct inc].each do |mode|
        k = "#{key}_#{mode}"
        if nested == :inner
          inner = { 'type' => 'View', 'width' => 'matchParent', 'height' => 'matchParent',
                    'child' => [box("s_#{k}", attr => "a_#{k}"), anchor("a_#{k}")] }
          if mode == 'inc'
            files["parts/p_#{k}"] = inner
            inner = { 'include' => "parts/p_#{k}", 'id' => include_id }
          end
          frames << frame(k, [inner])
          next
        end
        subject = box("s_#{k}", attr => "a_#{k}")
        if mode == 'inc'
          if nested
            files["parts/p_#{k}_inner"] = subject
            files["parts/p_#{k}"] = { 'include' => "parts/p_#{k}_inner", 'id' => 'mid' }
          else
            files["parts/p_#{k}"] = subject
          end
          subject = { 'include' => "parts/p_#{k}" }
          subject['id'] = include_id if include_id
        end
        frames << frame(k, [subject, anchor("a_#{k}")])
      end
    end
    files['screen'] = { 'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'wrapContent',
                        'orientation' => 'horizontal', 'flexWrap' => 'wrap', 'child' => frames }
    files
  end

  # The generated sources and the TypeScript of the screen's component.
  def self.build(dir)
    tool = File.join(dir, 'rjui_tools')
    FileUtils.mkdir_p(tool)
    %w[bin lib].each { |d| raise "could not copy #{d}" unless system('cp', '-RL', File.join(IRSC_RJUI_ROOT, d), tool) }
    File.write(File.join(dir, 'rjui.config.json'),
               JSON.generate(RjuiTools::Core::ConfigManager::DEFAULT_CONFIG.merge('typescript' => true)))
    layouts.each do |name, tree|
      path = File.join(dir, 'src', 'Layouts', "#{name}.json")
      FileUtils.mkdir_p(File.dirname(path))
      File.write(path, JSON.generate(tree))
    end
    log, status = Open3.capture2e({ 'JSONUI_INCLUDE_ID_PREFIX' => 'on' }, RbConfig.ruby,
                                  File.join(tool, 'bin', 'rjui'), 'build', chdir: dir)
    raise "rjui build failed:\n#{log}" unless status.success?

    File.join(dir, 'src', 'generated')
  end

  APP = <<~JS
    const effects = [];
    const h = (type, props, ...children) => {
      props = props || {};
      if (typeof type === 'function') return type({ ...props, children: children.length === 1 ? children[0] : children });
      if (type === Frag) { const f = document.createDocumentFragment(); append(f, children); return f; }
      const el = document.createElement(type);
      for (const [k, v] of Object.entries(props)) {
        if (k === 'className') el.className = v;
        else if (k === 'ref') { if (v) v.current = el; }
        else if (k === 'style') { for (const [p, x] of Object.entries(v || {})) if (x != null) el.style[p] = x; }
        else if (k === 'id' && v != null) el.setAttribute('id', v);
      }
      append(el, children);
      return el;
    };
    const append = (el, kids) => { for (const c of kids.flat(Infinity)) if (c != null && c !== false && c !== true) el.append(c.nodeType ? c : String(c)); };
    const Frag = 'frag';
    const React = { Fragment: Frag };
    const useRef = (v) => ({ current: v });
    const useEffect = (fn) => { effects.push(fn); };
    const useState = (v) => [v, () => {}];
    const useMemo = (f) => f();
    const useCallback = (f) => f;
    const useStringManager = () => new Proxy({}, { get: (_, k) => String(k) });
    const screenMarker = () => ({});
  JS

  def self.draw(generated)
    files = %w[includeId.ts includePlace.ts relativePosition.ts].map { |f| File.join(generated, f) }.select { |f| File.file?(f) } +
            Dir.glob(File.join(generated, 'data', '**', '*.ts')) + Dir.glob(File.join(generated, 'components', '**', '*.tsx'))
    Dir.mktmpdir('rjui_include_sibling_draw') do |dir|
      esbuild = File.join(IRSC_NODE_MODULES, 'esbuild')
      File.write(File.join(dir, 'strip.js'), <<~JS)
        const fs = require('fs');
        const esbuild = require(#{esbuild.to_json});
        const files = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
        const strip = (src) => src.split('\\n').filter((l) => !l.startsWith('import ')).join('\\n')
          .replace(/^export default [^;]+;$/gm, '').replace(/^export /gm, '').replace(/^"use client";$/m, '');
        const code = files.map((f) => esbuild.transformSync(strip(fs.readFileSync(f, 'utf8')),
          { loader: 'tsx', jsx: 'transform', jsxFactory: 'h', jsxFragment: 'Frag' }).code).join('\\n');
        fs.writeFileSync(process.argv[3], code);
      JS
      File.write(File.join(dir, 'files.json'), JSON.generate(files))
      log, st = Open3.capture2e('node', File.join(dir, 'strip.js'), File.join(dir, 'files.json'), File.join(dir, 'components.js'))
      raise "esbuild: #{log}" unless st.success?

      app = "#{APP}\n#{File.read(File.join(dir, 'components.js'))}\n" \
            "document.body.append(h(Screen, {}));\nfor (const e of effects) e();\nwindow.__drawn = true;\n"
      File.write(File.join(dir, 'app.js'), "(() => {\n#{app}\n})();\n")
      File.write(File.join(dir, 'content.html'), files.map { |f| File.read(f) }.join("\n"))
      File.write(File.join(dir, 'in.css'), %(@import "#{IRSC_NODE_MODULES}/tailwindcss/index.css" source(none);\n@source "./content.html";\n))
      log, st = Open3.capture2e(File.join(IRSC_NODE_MODULES, '.bin/tailwindcss'), '-i', File.join(dir, 'in.css'), '-o', File.join(dir, 'out.css'))
      raise "tailwindcss: #{log}" unless st.success?

      File.write(File.join(dir, 'page.html'), %(<html><head><link rel="stylesheet" href="out.css"></head><body style="margin:0"><script src="app.js"></script></body></html>))
      File.write(File.join(dir, 'read.js'), <<~JS)
        const { chromium } = require('playwright');
        (async () => {
          const browser = await chromium.launch({ executablePath: #{HeadlessChromium.path.to_json} });
          const page = await browser.newPage({ viewport: { width: 1600, height: 600 } });
          page.on('pageerror', (e) => { console.log('PAGEERROR ' + e.message); process.exit(3); });
          await page.goto('file://#{File.join(dir, 'page.html')}');
          await page.waitForFunction(() => window.__drawn === true);
          await page.waitForTimeout(300);
          const out = await page.evaluate(() => {
            const r = {};
            for (const f of document.querySelectorAll('[id^="frame_"]')) {
              const key = f.id.slice(6);
              const s = [...f.querySelectorAll('[id]')].find((el) => !el.id.startsWith('a_'));
              const fb = f.getBoundingClientRect(), sb = s.getBoundingClientRect();
              r[key] = [s.id, Math.round(sb.left - fb.left), Math.round(sb.top - fb.top)];
            }
            return r;
          });
          console.log('AT' + JSON.stringify(out));
          await browser.close();
        })();
      JS
      log, st = Open3.capture2e({ 'NODE_PATH' => IRSC_NODE_MODULES }, 'node', File.join(dir, 'read.js'), chdir: IRSC_SUPPORT)
      raise "playwright: #{log}" unless st.success?

      JSON.parse(log[/AT(\{.*\})/, 1] || raise("no result in:\n#{log}"))
    end
  end

  it 'hoists a spec for the include, found by the id its root carries here' do
    Dir.mktmpdir('rjui_include_sibling') do |dir|
      screen = File.read(File.join(self.class.build(dir), 'components', 'Screen.tsx'))
      expect(screen).to include("{ id: jsonuiIncludeId(idPrefix, \"s_ato_inc\"), above: 'a_ato_inc' }")
      expect(screen).to include("{ id: jsonuiIncludeId(jsonuiIncludePrefix(idPrefix, \"inc\"), \"s_idato_inc\"), above: 'a_idato_inc' }")
      expect(screen).to include('{ id: jsonuiIncludeId(jsonuiIncludePrefix(jsonuiIncludePrefix(idPrefix, "outer"), "mid"), ' \
                                "\"s_nest_inc\"), above: 'a_nest_inc' }")
      # control: a direct child's spec is as it was
      expect(screen).to include("{ id: 's_ato_direct', above: 'a_ato_direct' }")
      # inside an included layout the spec names its own elements as the DOM does
      part = File.read(File.join(dir, 'src', 'generated', 'components', 'parts', 'PInnerInc.tsx'))
      expect(part).to include('{ id: jsonuiIncludeId(idPrefix, "s_inner_inc"), above: jsonuiIncludeId(idPrefix, "a_inner_inc") }')
      # the include is absolute, as the constrained direct child is
      expect(screen).to match(/<PAtoInc idPrefix=\{idPrefix\} jsonuiPlace=\{\{ add: "absolute" \}\} \/>/)
    end
  end

  it 'draws the root where the same JSON draws as a direct child' do
    HeadlessChromium.ensure!(self)
    unless %w[.bin/esbuild .bin/tailwindcss playwright].all? { |p| File.exist?(File.join(IRSC_NODE_MODULES, p)) }
      reason = 'esbuild / tailwindcss / playwright are not installed under spec/support'
      raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

      skip reason
    end

    Dir.mktmpdir('rjui_include_sibling') do |dir|
      got = self.class.draw(self.class.build(dir))
      at = ->(k) { got.fetch(k)[1..] }
      # the measure: the direct children are where the constraint puts them
      expect(%w[ato aro al ab acv].map { |k| at.call("#{k}_direct") })
        .to eq([[0, 30], [60, 0], [50, 0], [0, 40], [0, 45]]), got.inspect
      IRSC_CASES.each_key do |key|
        expect(at.call("#{key}_inc")).to eq(at.call("#{key}_direct")), "#{key}: #{got.inspect}"
      end
      expect(got['idato_inc'][0]).to eq('incSIdatoInc')
      expect(got['inner_inc'][0]).to eq('incSInnerInc')
    end
  end
end
