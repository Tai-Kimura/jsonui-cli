# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'
require 'rbconfig'
require_relative 'headless_chromium'
require 'core/config_manager'

# Builds a project of layouts with a copied rjui (jui build's include-prefix
# decision on) and draws its Screen component, with the helpers it calls, in
# headless Chromium by a small element factory that runs the components'
# effects after mounting. `draw` returns, for every element whose id starts
# with `frame_`, the first element in it with an id that does not start with
# `a_` (the anchors) — `[id, x, y]` relative to the frame.
module RjuiChromiumDraw
  RJUI_ROOT = File.expand_path('../..', __dir__)
  SUPPORT = __dir__
  NODE_MODULES = File.join(SUPPORT, 'node_modules')

  def self.tools_installed?
    %w[.bin/esbuild .bin/tailwindcss playwright].all? { |p| File.exist?(File.join(NODE_MODULES, p)) }
  end

  # The generated sources and the TypeScript of the screen's component.
  def self.build(dir, layouts)
    tool = File.join(dir, 'rjui_tools')
    FileUtils.mkdir_p(tool)
    %w[bin lib].each { |d| raise "could not copy #{d}" unless system('cp', '-RL', File.join(RJUI_ROOT, d), tool) }
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
      esbuild = File.join(NODE_MODULES, 'esbuild')
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
      File.write(File.join(dir, 'in.css'), %(@import "#{NODE_MODULES}/tailwindcss/index.css" source(none);\n@source "./content.html";\n))
      log, st = Open3.capture2e(File.join(NODE_MODULES, '.bin/tailwindcss'), '-i', File.join(dir, 'in.css'), '-o', File.join(dir, 'out.css'))
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
      log, st = Open3.capture2e({ 'NODE_PATH' => NODE_MODULES }, 'node', File.join(dir, 'read.js'), chdir: SUPPORT)
      raise "playwright: #{log}" unless st.success?

      JSON.parse(log[/AT(\{.*\})/, 1] || raise("no result in:\n#{log}"))
    end
  end
end
