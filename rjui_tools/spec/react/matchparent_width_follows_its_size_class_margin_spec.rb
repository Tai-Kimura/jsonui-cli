# frozen_string_literal: true

require_relative '../spec_helper'
require 'json'
require 'open3'
require 'stringio'
require 'tmpdir'
require_relative '../support/headless_chromium'
require_relative '../support/typescript_compiler'
require 'react/converters/converter_table'

# A matchParent width less its horizontal margins follows a size class that
# changes the margins or the width (ticket rjui-matchparent-margin-calc-width-
# ignores-responsive-margin). The width was an inline `calc(100% - <margins>)`
# from the base's margins, so once a size class's margins were drawn (2.3.29)
# the width stayed the base's: a leftMargin 44 set to 0 below 768px left 44px
# on the right, and a size class's own width lost to the inline calc. Measured
# on v2.3.31 in Chromium over 7 bases (left / right / both / start / end /
# `margins` / none) x 7 overrides: 13 of 44 drew what the same values written
# at the base draw. The calc is a class now (`w-[calc(100%_-_2.75rem)]`), and a
# size class that changes the width or a horizontal margin draws the merged
# node's width class (BaseConverter#size_class_width); `margins` counts
# towards the calc, where a matchParent width with `margins` ran past its
# parent before.
RSpec.describe 'a matchParent width less its margins follows its size class' do
  def converters = RjuiTools::React::Converters::ConverterTable.table
  def support_dir = File.expand_path('../support', __dir__)

  def emit(node, typescript: false)
    old = $stdout
    $stdout = StringIO.new
    converters.fetch(node['type']).new(JSON.parse(JSON.generate(node)), { 'use_tailwind' => true, 'typescript' => typescript })
              .convert_node(0).strip
  ensure
    $stdout = old
  end

  def row(id, extra) = { 'type' => 'View', 'id' => id, 'width' => 'matchParent', 'height' => 20, 'child' => [] }.merge(extra)

  describe 'what is emitted' do
    it "the ticket's row: the calc is a class, and below 768 it is the width of no margin" do
      out = emit(row('row_sub', 'leftMargin' => 44, 'responsive' => { 'maxWidth:768' => { 'leftMargin' => 0 } }))
      expect(out).to include('w-[calc(100%_-_2.75rem)]', 'max-[768px]:ml-[0rem]', 'max-[768px]:w-full')
      expect(out).not_to include('style=')
    end

    it 'a size class with its own width, or new margins, draws its width' do
      expect(emit(row('r', 'leftMargin' => 44, 'responsive' => { 'compact' => { 'width' => 150 } })))
        .to include('max-md:w-[150px]')
      expect(emit(row('r', 'leftMargin' => 10, 'rightMargin' => 30, 'responsive' => { 'compact' => { 'leftMargin' => 8 } })))
        .to include('max-md:w-[calc(100%_-_2.375rem)]')
      expect(emit(row('r', 'responsive' => { 'compact' => { 'leftMargin' => 12 } }))).to include('max-md:w-[calc(100%_-_0.75rem)]')
    end

    it '`margins` counts towards the calc' do
      expect(emit(row('r', 'margins' => [0, 16, 0, 16]))).to include('w-[calc(100%_-_2rem)]')
      expect(emit(row('r', 'margins' => [0, 16]))).to include('w-[calc(100%_-_2rem)]')
    end

    it 'control: a bound margin keeps no calc of it, and a fixed width no calc at all' do
      expect(emit(row('r', 'leftMargin' => '@{m}'))).not_to include('calc(')
      expect(emit(row('r', 'leftMargin' => 44).merge('width' => 100))).not_to include('calc(')
    end

    it 'the emit compiles as TypeScript', :typescript_compile do
      element = emit(row('row_sub', 'leftMargin' => 44, 'responsive' => { 'maxWidth:768' => { 'leftMargin' => 0 } }), typescript: true)
      expect(TypeScriptCompiler.component(element)).to compile_as_typescript
    end
  end

  describe 'drawn in headless Chromium' do
    def node_modules = File.join(support_dir, 'node_modules')

    def tools_ready?
      %w[.bin/esbuild .bin/tailwindcss playwright].all? { |p| File.exist?(File.join(node_modules, p)) }
    end

    # {window => {id => [left gap, right gap, width]}} in a 300 wide column
    def draw(elements, windows)
      Dir.mktmpdir('rjui_calc_width') do |dir|
        File.write(File.join(dir, 'content.html'), elements.join("\n"))
        File.write(File.join(dir, 'in.css'), %(@import "#{node_modules}/tailwindcss/index.css" source(none);\n@source "./content.html";\n))
        log, st = Open3.capture2e(File.join(node_modules, '.bin/tailwindcss'), '-i', File.join(dir, 'in.css'), '-o', File.join(dir, 'out.css'))
        raise "tailwindcss: #{log}" unless st.success?

        File.write(File.join(dir, 'app.jsx'), <<~JSX)
          const h = (tag, props, ...kids) => {
            const el = document.createElement(tag);
            for (const [k, v] of Object.entries(props || {})) {
              if (k === 'className') el.className = v;
              else if (k === 'style') { for (const [p, x] of Object.entries(v || {})) if (x != null) el.style[p] = x; }
              else if (k === 'id') el.id = v;
            }
            for (const c of kids.flat(Infinity)) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
            return el;
          };
          const React = { Fragment: 'div' };
          for (const el of [#{elements.join(",\n")}]) { const p = document.createElement('div'); p.style.cssText = 'display:flex;flex-direction:column;width:300px'; p.append(el); document.body.append(p); }
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
              out[name] = await page.evaluate(() => Object.fromEntries([...document.querySelectorAll('[id]')].map((e) => {
                const p = e.parentElement.getBoundingClientRect(), r = e.getBoundingClientRect();
                return [e.id, [Math.round(r.left - p.left), Math.round(p.right - r.right), Math.round(r.width)]];
              })));
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

    it 'each row fills its column less its margins, in the size class and out of it' do
      HeadlessChromium.ensure!(self)
      unless tools_ready?
        reason = 'esbuild / tailwindcss / playwright are not installed under spec/support'
        raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

        skip reason
      end

      nodes = [
        row('ticket', 'leftMargin' => 44, 'responsive' => { 'maxWidth:768' => { 'leftMargin' => 0 } }),
        row('both', 'leftMargin' => 10, 'rightMargin' => 30, 'responsive' => { 'compact' => { 'rightMargin' => 0 } }),
        row('fixed', 'leftMargin' => 44, 'responsive' => { 'compact' => { 'width' => 150 } }),
        row('added', 'responsive' => { 'compact' => { 'leftMargin' => 12 } }),
        row('margins', 'margins' => [0, 16, 0, 16])
      ]
      got = draw(nodes.map { |n| emit(n) }, 'narrow' => { width: 390, height: 600 }, 'wide' => { width: 1200, height: 600 })
      expect(got['narrow']).to eq('ticket' => [0, 0, 300], 'both' => [10, 0, 290], 'fixed' => [44, 106, 150], 'added' => [12, 0, 288],
                                  'margins' => [16, 16, 268]), got.inspect
      expect(got['wide']).to eq('ticket' => [44, 0, 256], 'both' => [10, 30, 260], 'fixed' => [44, 0, 256], 'added' => [0, 0, 300],
                                'margins' => [16, 16, 268]), got.inspect
    end
  end
end
