# frozen_string_literal: true

require_relative '../spec_helper'
require 'json'
require 'open3'
require 'stringio'
require 'tmpdir'
require_relative '../support/headless_chromium'
require_relative '../support/typescript_compiler'
require 'react/converters/converter_table'

# A size class's key that no ResponsiveHelper mapper draws is carried the way
# iOS and Android draw a size class — the node redrawn with the block merged in
# (ticket rjui-responsive-columns-linespacing-border-not-drawn): the converter's
# own classes for the merged node, less its classes without the keys, scoped by
# the size class's variants (BaseConverter#carry_size_class). Until jsonui-cli
# 2.3.31 every such key was said and not drawn: a Collection's columns,
# lineSpacing and columnSpacing, a border's colour, width and style, the
# align / center keys. Measured on v2.3.30 over 17 types x their attributes
# (1800 pairs): 1190 said, 105 attributes rjui draws at the base; 192 pairs are
# carried now, and drawn in Chromium each equals the value written at the base
# in the size class's window and the base in the other. What it cannot carry —
# a class the base draws that the merged node drops, an inline style, other
# markup — is still said, with why.
RSpec.describe 'a size class key no mapper draws is carried by the converter' do
  def converters = RjuiTools::React::Converters::ConverterTable.table
  def support_dir = File.expand_path('../support', __dir__)

  def emit(node, typescript: false)
    old = $stdout
    $stdout = StringIO.new
    jsx = converters.fetch(node['type']).new(JSON.parse(JSON.generate(node)), { 'use_tailwind' => true, 'typescript' => typescript })
                    .convert_node(0).strip
    [jsx, $stdout.string.lines.map { |l| l.sub(/\e\[\d+m\[WARN\]\e\[0m /, '').strip }]
  ensure
    $stdout = old
  end

  def classes_of(jsx, id) = jsx[/<[A-Za-z][^<>]*?\bid="#{id}"[^<>]*?className="([^"]*)"/m, 1].to_s.split

  def collection(id, extra)
    { 'type' => 'Collection', 'id' => id, 'items' => '@{items}', 'cellClasses' => ['RowCell'] }.merge(extra)
  end

  def frame(type, id, extra = {})
    { 'type' => type, 'id' => id, 'width' => 120, 'height' => 40, 'borderWidth' => 1, 'borderColor' => '#000000' }
      .merge(type == 'TextField' ? {} : { 'child' => [] }).merge(extra)
  end

  describe 'what is emitted' do
    it "a Collection's columns, lineSpacing and columnSpacing" do
      jsx, said = emit(collection('c', 'columns' => 3, 'columnSpacing' => 4, 'responsive' => { 'compact' => { 'columns' => 1 } }))
      expect(classes_of(jsx, 'c')).to include('grid-cols-3', 'max-md:flex', 'max-md:flex-col')
      jsx2, said2 = emit(collection('c', 'columns' => 7, 'columnSpacing' => 12, 'responsive' => { 'compact' => { 'columns' => 2, 'columnSpacing' => 4 } }))
      expect(classes_of(jsx2, 'c')).to include('max-md:grid-cols-2', 'max-md:gap-x-[0.25rem]')
      jsx3, said3 = emit(collection('c', 'columns' => 2, 'lineSpacing' => 4, 'responsive' => { 'regular' => { 'lineSpacing' => 16 } }))
      expect(classes_of(jsx3, 'c')).to include('lg:gap-y-[1rem]')
      expect(said + said2 + said3).to eq([])
    end

    it "a padded Collection's carried classes go on its scroll box, the element with its id" do
      node = collection('c', 'paddings' => [16, 16, 16, 16], 'lineSpacing' => 12, 'sections' => [{ 'cell' => 'RowCell' }],
                             'responsive' => { 'minWidth:840' => { 'columns' => 3, 'columnSpacing' => 12 } })
      jsx, said = emit(node)
      expect(said).to eq([])
      expect(classes_of(jsx, 'c')).to include('min-[840px]:grid', 'min-[840px]:grid-cols-3', 'min-[840px]:gap-x-[0.75rem]')
      expect(jsx.lines.first).not_to include('min-[840px]')
    end

    it 'a border is switched as the base draws it: ::after, outline or border' do
      [['View', 'after:border'], ['ScrollView', 'outline'], ['TextField', 'border']].each do |type, drawn|
        jsx, said = emit(frame(type, 'f', 'responsive' => { 'regular' => { 'borderWidth' => 3, 'borderColor' => '#FF0000' } }))
        expect(said).to eq([]), type
        expect(classes_of(jsx, 'f')).to include("lg:#{drawn}-[#FF0000]"), "#{type}: #{classes_of(jsx, 'f')}"
      end
    end

    it 'a border taken away (borderWidth 0) is a reset for the way the base draws it' do
      { 'View' => 'max-md:after:border-0', 'ScrollView' => 'max-md:outline-0', 'TextField' => 'max-md:border-0' }.each do |type, reset|
        jsx, said = emit(frame(type, 'f', 'responsive' => { 'compact' => { 'borderWidth' => 0 } }))
        expect(said).to eq([]), type
        expect(classes_of(jsx, 'f')).to include(reset), "#{type}: #{classes_of(jsx, 'f')}"
      end
    end

    it 'the align and center keys' do
      jsx, said = emit({ 'type' => 'View', 'id' => 'v', 'width' => 60, 'height' => 20, 'responsive' => { 'regular' => { 'centerHorizontal' => true } } })
      expect(said).to eq([])
      expect(classes_of(jsx, 'v')).to include('lg:mx-auto')
    end

    it 'says what it cannot carry, and why' do
      _, said = emit(collection('c', 'sections' => [{ 'cell' => 'RowCell' }, { 'cell' => 'RowCell' }],
                                     'responsive' => { 'regular' => { 'columns' => 2 } }))
      expect(said).to eq(["Collection 'c': responsive 'regular' sets 'columns', which is not drawn on web — the web draws it in an inline style or the markup here, which no class can switch"])
      _, said = emit({ 'type' => 'TextView', 'id' => 't', 'borderWidth' => 1, 'borderColor' => '#000000',
                       'responsive' => { 'regular' => { 'borderColor' => '#FF0000' } } })
      expect(said.first).to end_with('the web draws it in an inline style or the markup here, which no class can switch')
      _, said = emit({ 'type' => 'Label', 'id' => 'l', 'text' => 'x', 'responsive' => { 'regular' => { 'offsetX' => 4 } } })
      expect(said.first).to end_with('the web draws an offset as an inline transform, which no class can replace')
    end

    it 'the emit compiles as TypeScript', :typescript_compile do
      elements = [emit(collection('c', 'columns' => 3, 'responsive' => { 'compact' => { 'columns' => 1 } }), typescript: true).first,
                  emit(frame('View', 'f', 'responsive' => { 'compact' => { 'borderWidth' => 0 } }), typescript: true).first]
      ambient = TypeScriptCompiler::AMBIENT + <<~TS
        declare const data: { items?: { sections?: { cells?: { data?: Record<string, unknown>[] } }[] } };
        declare const RowCell: (props: { id: string; data: RowCellData }) => JSX.Element;
        declare namespace JSX { interface IntrinsicAttributes { key?: unknown } }
        interface RowCellData {}
        declare namespace React { type CSSProperties = { [property: string]: string | number | undefined } }
      TS
      expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(ambient)
    end
  end

  describe 'drawn in headless Chromium' do
    def node_modules = File.join(support_dir, 'node_modules')

    def tools_ready?
      %w[.bin/esbuild .bin/tailwindcss playwright].all? { |p| File.exist?(File.join(node_modules, p)) }
    end

    # {window => {id => reading}}: a Collection's distinct cell columns, a
    # frame's drawn border width (::after, outline or border), a child's left
    def draw(elements, reads, windows)
      Dir.mktmpdir('rjui_size_class_keys') do |dir|
        File.write(File.join(dir, 'content.html'), elements.join("\n") + "\nw-full h-[20px]\n")
        File.write(File.join(dir, 'in.css'), %(@import "#{node_modules}/tailwindcss/index.css" source(none);\n@source "./content.html";\n))
        log, st = Open3.capture2e(File.join(node_modules, '.bin/tailwindcss'), '-i', File.join(dir, 'in.css'), '-o', File.join(dir, 'out.css'))
        raise "tailwindcss: #{log}" unless st.success?

        refs = elements.join("\n").scan(/ref=\{(\w+)\}/).flatten.uniq.map { |r| "const #{r} = { current: null };" }.join("\n")
        File.write(File.join(dir, 'app.jsx'), <<~JSX)
          const h = (tag, props, ...kids) => {
            props = props || {};
            if (typeof tag === 'function') return tag({ ...props, children: kids });
            const el = document.createElement(tag);
            for (const [k, v] of Object.entries(props)) {
              if (k === 'className') el.className = v;
              else if (k === 'style') { for (const [p, x] of Object.entries(v || {})) if (x != null) el.style[p] = x; }
              else if (k === 'id') el.id = v;
            }
            for (const c of kids.flat(Infinity)) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
            return el;
          };
          const React = { Fragment: 'div' };
          const ColorManager = { resolveColor: (c) => c };
          const RowCell = ({ id }) => h('div', { id, className: 'w-full h-[20px]' });
          #{refs}
          const data = { items: { sections: [{ cells: { data: [{}, {}, {}, {}, {}, {}] } }] } };
          for (const el of [#{elements.join(",\n")}]) { const box = document.createElement('div'); box.style.cssText = 'display:flex;flex-direction:column;width:360px'; box.append(el); document.body.append(box); }
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
                for (const [id, kind] of Object.entries(reads)) {
                  const el = document.getElementById(id);
                  if (kind === 'columns') r[id] = new Set([...el.children].map((c) => Math.round(c.getBoundingClientRect().left))).size;
                  else if (kind === 'border') {
                    const a = getComputedStyle(el, '::after'), s = getComputedStyle(el);
                    r[id] = Math.max(parseFloat(a.content !== 'none' ? a.borderTopWidth : '0') || 0,
                                     s.outlineStyle !== 'none' ? parseFloat(s.outlineWidth) || 0 : 0, parseFloat(s.borderTopWidth) || 0);
                  } else r[id] = Math.round(el.getBoundingClientRect().left - el.parentElement.getBoundingClientRect().left);
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

    it 'the columns, the frames and the centring change at their windows and hold the base in the others' do
      HeadlessChromium.ensure!(self)
      unless tools_ready?
        reason = 'esbuild / tailwindcss / playwright are not installed under spec/support'
        raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

        skip reason
      end

      nodes = [
        collection('cols', 'columns' => 3, 'responsive' => { 'compact' => { 'columns' => 1 } }),
        collection('kpis', 'columns' => 3, 'itemSpacing' => 12, 'lineSpacing' => 12, 'lazy' => 'none', 'responsive' => { 'compact' => { 'columns' => 1 } }),
        collection('padded', 'paddings' => [8, 8, 8, 8], 'sections' => [{ 'cell' => 'RowCell' }],
                             'responsive' => { 'minWidth:840' => { 'columns' => 3, 'columnSpacing' => 12 } }),
        frame('View', 'after'), frame('View', 'afterOff', 'responsive' => { 'compact' => { 'borderWidth' => 0 } }),
        frame('ScrollView', 'outlineOff', 'responsive' => { 'compact' => { 'borderWidth' => 0 } }),
        frame('TextField', 'borderOff', 'responsive' => { 'compact' => { 'borderWidth' => 0 } }),
        frame('View', 'thick', 'responsive' => { 'regular' => { 'borderWidth' => 4 } }),
        { 'type' => 'View', 'id' => 'centre', 'width' => 60, 'height' => 20, 'responsive' => { 'regular' => { 'centerHorizontal' => true } } }
      ]
      reads = { 'cols' => 'columns', 'kpis' => 'columns', 'padded' => 'columns', 'after' => 'border', 'afterOff' => 'border', 'outlineOff' => 'border',
                'borderOff' => 'border', 'thick' => 'border', 'centre' => 'left' }
      got = draw(nodes.map { |n| emit(n).first }, reads, 'compact' => { width: 390, height: 900 }, 'regular' => { width: 1200, height: 1400 })
      expect(got['regular']).to eq('cols' => 3, 'kpis' => 3, 'padded' => 3, 'after' => 1, 'afterOff' => 1, 'outlineOff' => 1, 'borderOff' => 1,
                                   'thick' => 4, 'centre' => 150), got.inspect
      expect(got['compact']).to eq('cols' => 1, 'kpis' => 1, 'padded' => 1, 'after' => 1, 'afterOff' => 0, 'outlineOff' => 0, 'borderOff' => 0,
                                   'thick' => 1, 'centre' => 0), got.inspect
    end
  end
end
