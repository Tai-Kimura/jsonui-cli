# frozen_string_literal: true

require_relative '../spec_helper'
require 'json'
require 'open3'
require 'tmpdir'
require_relative '../support/headless_chromium'
require_relative '../support/typescript_compiler'
require 'react/converters/converter_table'

# A responsive block with a landscape key is drawn at run time, by a class
# expression on `isLandscape` (ticket rjui-label-landscape-override-emits-no-class).
# Only View put it into its className, so until jsonui-cli 2.3.28 every other
# type dropped it: a Label's landscape textAlign or gravity left the text where
# the base put it (measured in Chromium, a 900 x 400 window).
RSpec.describe 'a landscape override reaches every type, not only View' do
  def converters = RjuiTools::React::Converters::ConverterTable.table
  def support_dir = File.expand_path('../support', __dir__)

  def jsx(node)
    converters.fetch(node['type']).new(node, { 'use_tailwind' => true }).convert_node(0).strip
  end

  def label(id, extra)
    { 'type' => 'Label', 'id' => id, 'text' => 'Go', 'width' => 240, 'height' => 32 }.merge(extra)
  end

  it 'a Label and a Button carry the landscape expression; a View carries it once' do
    expect(jsx(label('l', 'textAlign' => 'Right', 'responsive' => { 'landscape' => { 'textAlign' => 'Left' } })))
      .to include('${isLandscape ? "text-left justify-start" : ""}')
    expect(jsx(label('l', 'responsive' => { 'landscape' => { 'gravity' => 'right' } })))
      .to include('${isLandscape ? "justify-end text-right" : ""}')
    expect(jsx({ 'type' => 'Button', 'id' => 'b', 'text' => 'x', 'responsive' => { 'landscape' => { 'cornerRadius' => 8 } } }))
      .to include('${isLandscape ? "rounded-lg" : ""}')
    view = jsx({ 'type' => 'View', 'id' => 'v', 'responsive' => { 'landscape' => { 'orientation' => 'horizontal' } }, 'child' => [] })
    expect(view.scan('isLandscape').size).to eq(1)
  end

  it 'the emit compiles as TypeScript', :typescript_compile do
    elements = [label('a', 'textAlign' => 'Right', 'responsive' => { 'landscape' => { 'textAlign' => 'Left' } }),
                { 'type' => 'Button', 'id' => 'b', 'text' => 'x', 'responsive' => { 'landscape' => { 'cornerRadius' => 8 } } }]
                 .map { |n| converters.fetch(n['type']).new(n, { 'use_tailwind' => true, 'typescript' => true }).convert_node(0).strip }
    ambient = TypeScriptCompiler::AMBIENT + "declare const isLandscape: boolean;\n"
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(ambient)
  end

  it 'control: a block without a landscape key writes no expression' do
    expect(jsx(label('l', 'responsive' => { 'regular' => { 'textAlign' => 'Center' } }))).not_to include('isLandscape')
  end

  describe 'drawn in headless Chromium' do
    def node_modules = File.join(support_dir, 'node_modules')

    def tools_ready?
      %w[.bin/esbuild .bin/tailwindcss playwright].all? { |p| File.exist?(File.join(node_modules, p)) }
    end

    # {window => {id => [left gap, right gap]}}
    def draw(elements, windows)
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
              else if (k === 'id') el.id = v;
            }
            for (const c of kids.flat()) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
            return el;
          };
          const React = { Fragment: 'div' };
          // what the generated hook reads (ResponsiveHelper.landscape_hook_declaration)
          const isLandscape = matchMedia('(orientation: landscape)').matches;
          for (const el of [#{elements.join(",\n")}]) { const box = document.createElement('div'); box.append(el); document.body.append(box); }
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
              out[name] = await page.evaluate(() => {
                const r = {};
                for (const el of document.querySelectorAll('span[id]')) {
                  const range = document.createRange(); range.selectNodeContents(el);
                  const t = range.getBoundingClientRect(), b = el.getBoundingClientRect();
                  r[el.id] = [Math.round(t.left - b.left), Math.round(b.right - t.right)];
                }
                return r;
              });
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

    it "puts a Label's text where its landscape override says, in a landscape window only" do
      HeadlessChromium.ensure!(self)
      unless tools_ready?
        reason = 'esbuild / tailwindcss / playwright are not installed under spec/support'
        raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

        skip reason
      end

      nodes = [label('declRight', 'textAlign' => 'Right'), label('declCenter', 'textAlign' => 'Center'),
               label('left', 'textAlign' => 'Right', 'responsive' => { 'landscape' => { 'textAlign' => 'Left' } }),
               label('center', 'responsive' => { 'landscape' => { 'textAlign' => 'Center' } }),
               label('gravity', 'responsive' => { 'landscape' => { 'gravity' => 'right' } })]
      got = draw(nodes.map { |n| jsx(n) }, 'landscape' => { width: 900, height: 400 }, 'portrait' => { width: 400, height: 900 })
      end_, mid = got['landscape']['declRight'], got['landscape']['declCenter']
      start = end_.reverse
      expect(end_.first).to be > 40, got.inspect
      expect(got['landscape'].slice('left', 'center', 'gravity')).to eq('left' => start, 'center' => mid, 'gravity' => end_), got.inspect
      expect(got['portrait'].slice('left', 'center', 'gravity')).to eq('left' => end_, 'center' => start, 'gravity' => start), got.inspect
    end
  end
end
