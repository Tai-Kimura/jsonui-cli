# frozen_string_literal: true

require_relative '../spec_helper'
require 'json'
require 'open3'
require 'tmpdir'
require_relative '../support/headless_chromium'
require_relative '../support/typescript_compiler'
require 'react/converters/converter_table'

# A landscape override reaches every type, and wins over the base value it
# overrides.
#
# - jsonui-cli 2.3.28 (ticket rjui-label-landscape-override-emits-no-class):
#   only View put a landscape key's classes into its className, so every other
#   type dropped them — a Label's landscape textAlign or gravity left the text
#   where the base put it (measured in Chromium, a 900 x 400 window).
# - jsonui-cli 2.3.30 (ticket rjui-bound-width-inline-style-beats-responsive-
#   width): those classes were unprefixed, under a run-time `isLandscape`, and
#   tied with the base's classes for the same property — the stylesheet's
#   order chose. Measured on literal bases: a landscape height, the paddings
#   and margins, cornerRadius, textAlign Center over Right and both colours
#   lost to the base. 2.3.28's arm passed by that order's luck (text-left over
#   text-right happened to come later). A landscape key is written as media
#   variants now (landscape: / portrait:, ResponsiveHelper.landscape_variants),
#   which come after the base classes and win; this arm draws each conflict
#   and reads the property.
RSpec.describe 'a landscape override reaches every type and wins over its base' do
  def converters = RjuiTools::React::Converters::ConverterTable.table
  def support_dir = File.expand_path('../support', __dir__)

  def jsx(node, typescript: false)
    converters.fetch(node['type']).new(node, { 'use_tailwind' => true, 'typescript' => typescript }).convert_node(0).strip
  end

  def label(id, extra)
    { 'type' => 'Label', 'id' => id, 'text' => 'Go', 'width' => 240, 'height' => 32 }.merge(extra)
  end

  it 'a Label, a Button and a View carry the landscape classes, scoped by the landscape: variant' do
    expect(jsx(label('l', 'textAlign' => 'Right', 'responsive' => { 'landscape' => { 'textAlign' => 'Left' } })))
      .to include('landscape:text-left', 'landscape:justify-start')
    expect(jsx(label('l', 'responsive' => { 'landscape' => { 'gravity' => 'right' } })))
      .to include('landscape:justify-end', 'landscape:text-right')
    expect(jsx({ 'type' => 'Button', 'id' => 'b', 'text' => 'x', 'responsive' => { 'landscape' => { 'cornerRadius' => 8 } } }))
      .to include('landscape:rounded-lg')
    view = jsx({ 'type' => 'View', 'id' => 'v', 'responsive' => { 'landscape' => { 'orientation' => 'horizontal' } }, 'child' => [] })
    expect(view.scan('landscape:flex-row').size).to eq(1)
    expect([view, jsx(label('l', 'responsive' => { 'landscape' => { 'textAlign' => 'Left' } }))].join).not_to include('isLandscape')
  end

  it 'the emit compiles as TypeScript', :typescript_compile do
    elements = [label('a', 'textAlign' => 'Right', 'responsive' => { 'landscape' => { 'textAlign' => 'Left' } }),
                { 'type' => 'Button', 'id' => 'b', 'text' => 'x', 'responsive' => { 'landscape' => { 'cornerRadius' => 8 } } }]
                 .map { |n| jsx(n, typescript: true) }
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript
  end

  it 'control: a block without a landscape key writes no landscape: class' do
    expect(jsx(label('l', 'responsive' => { 'regular' => { 'textAlign' => 'Center' } }))).not_to include('landscape:')
  end

  describe 'drawn in headless Chromium' do
    def node_modules = File.join(support_dir, 'node_modules')

    def tools_ready?
      %w[.bin/esbuild .bin/tailwindcss playwright].all? { |p| File.exist?(File.join(node_modules, p)) }
    end

    # {window => {id => {property => computed value}}}; a Label also reads its
    # text's left / right gap in px
    def draw(elements, reads, windows)
      Dir.mktmpdir('rjui_landscape') do |dir|
        File.write(File.join(dir, 'content.html'), elements.join("\n"))
        File.write(File.join(dir, 'in.css'), %(@import "#{node_modules}/tailwindcss/index.css" source(none);\n@source "./content.html";\n))
        log, st = Open3.capture2e(File.join(node_modules, '.bin/tailwindcss'), '-i', File.join(dir, 'in.css'), '-o', File.join(dir, 'out.css'))
        raise "tailwindcss: #{log}" unless st.success?

        File.write(File.join(dir, 'app.jsx'), <<~JSX)
          const h = (tag, props, ...kids) => {
            const el = document.createElement(tag);
            for (const [k, v] of Object.entries(props || {})) {
              if (k === 'className') el.className = v;
              else if (k === 'style') { for (const [p, x] of Object.entries(v || {})) if (x != null) { if (p.startsWith('--')) el.style.setProperty(p, x); else el.style[p] = x; } }
              else if (k === 'id') el.id = v;
            }
            for (const c of kids.flat(Infinity)) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
            return el;
          };
          const React = { Fragment: 'div' };
          const ColorManager = { resolveColor: (c) => c };
          // what the run-time hook read before 2.3.30, so an earlier emit draws
          // (and fails by what it draws) rather than throwing
          const isLandscape = matchMedia('(orientation: landscape)').matches;
          for (const el of [#{elements.join(",\n")}]) { const box = document.createElement('div'); box.style.display = 'flow-root'; box.append(el); document.body.append(box); }
        JSX
        log, st = Open3.capture2e(File.join(node_modules, '.bin/esbuild'), File.join(dir, 'app.jsx'), '--bundle', '--jsx-factory=h', '--outfile=' + File.join(dir, 'app.js'))
        raise "esbuild: #{log}" unless st.success?

        File.write(File.join(dir, 'page.html'), %(<html><head><link rel="stylesheet" href="out.css"></head><body><script src="app.js"></script></body></html>))
        File.write(File.join(dir, 'read.js'), <<~JS)
          const { chromium } = require('playwright');
          (async () => {
            const browser = await chromium.launch({ executablePath: #{HeadlessChromium.path.to_json} });
            const out = {};
            for (const [name, viewport] of Object.entries(#{windows.to_json})) {
              const page = await browser.newPage({ viewport });
              page.on('pageerror', (e) => { console.log('PAGEERROR ' + e.message); process.exit(3); });
              await page.goto('file://#{File.join(dir, 'page.html')}');
              out[name] = await page.evaluate((reads) => {
                const r = {};
                for (const [id, prop] of Object.entries(reads)) {
                  const el = document.getElementById(id);
                  if (prop === 'gaps') {
                    const range = document.createRange(); range.selectNodeContents(el);
                    const t = range.getBoundingClientRect(), b = el.getBoundingClientRect();
                    r[id] = [Math.round(t.left - b.left), Math.round(b.right - t.right)];
                  } else {
                    r[id] = getComputedStyle(el)[prop];
                  }
                }
                return r;
              }, #{reads.to_json});
              await page.close();
            }
            console.log('AT' + JSON.stringify(out));
            await browser.close();
          })();
        JS
        log, st = Open3.capture2e({ 'NODE_PATH' => node_modules }, 'node', File.join(dir, 'read.js'), chdir: support_dir)
        raise "playwright: #{log}" unless st.success?

        JSON.parse(log[/AT(\{.*\})/, 1] || raise("no result in:\n#{log}"))
      end
    end

    it 'in a landscape window the override wins over the base value of the same property; in a portrait one the base holds' do
      HeadlessChromium.ensure!(self)
      unless tools_ready?
        reason = 'esbuild / tailwindcss / playwright are not installed under spec/support'
        raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

        skip reason
      end

      view = ->(id, base, over) { { 'type' => 'View', 'id' => id, 'width' => 200, 'height' => 40 }.merge(base).merge('responsive' => { 'landscape' => over }) }
      nodes = [
        label('declRight', 'textAlign' => 'Right'), label('declCenter', 'textAlign' => 'Center'),
        label('left', 'textAlign' => 'Right', 'responsive' => { 'landscape' => { 'textAlign' => 'Left' } }),
        label('centerOverRight', 'textAlign' => 'Right', 'responsive' => { 'landscape' => { 'textAlign' => 'Center' } }),
        label('gravity', 'responsive' => { 'landscape' => { 'gravity' => 'right' } }),
        view.('height', { 'height' => 80 }, { 'height' => 30 }),
        view.('padding', { 'paddings' => 20 }, { 'paddings' => 6 }),
        view.('margin', { 'topMargin' => 20 }, { 'topMargin' => 6 }),
        view.('radius', { 'cornerRadius' => 20 }, { 'cornerRadius' => 4 }),
        view.('colour', { 'background' => '#FF0000' }, { 'background' => '#00FF00' })
      ]
      reads = { 'declRight' => 'gaps', 'declCenter' => 'gaps', 'left' => 'gaps', 'centerOverRight' => 'gaps', 'gravity' => 'gaps',
                'height' => 'height', 'padding' => 'paddingTop', 'margin' => 'marginTop', 'radius' => 'borderTopLeftRadius',
                'colour' => 'backgroundColor' }
      got = draw(nodes.map { |n| jsx(n) }, reads, 'landscape' => { width: 900, height: 400 }, 'portrait' => { width: 400, height: 900 })
      land, port = got['landscape'], got['portrait']
      end_, mid = land['declRight'], land['declCenter']
      start = end_.reverse
      expect(end_.first).to be > 40, got.inspect
      expect(land.slice('left', 'centerOverRight', 'gravity')).to eq('left' => start, 'centerOverRight' => mid, 'gravity' => end_), got.inspect
      expect(port.slice('left', 'centerOverRight', 'gravity')).to eq('left' => end_, 'centerOverRight' => end_, 'gravity' => start), got.inspect
      expect(land.slice('height', 'padding', 'margin', 'radius', 'colour'))
        .to eq('height' => '30px', 'padding' => '6px', 'margin' => '6px', 'radius' => '4px', 'colour' => 'rgb(0, 255, 0)'), got.inspect
      expect(port.slice('height', 'padding', 'margin', 'radius', 'colour'))
        .to eq('height' => '80px', 'padding' => '20px', 'margin' => '20px', 'radius' => '20px', 'colour' => 'rgb(255, 0, 0)'), got.inspect
    end
  end
end
