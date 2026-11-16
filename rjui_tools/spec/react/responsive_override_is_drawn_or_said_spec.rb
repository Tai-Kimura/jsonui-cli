# frozen_string_literal: true

require_relative '../spec_helper'
require 'json'
require 'open3'
require 'stringio'
require 'tmpdir'
require_relative '../support/headless_chromium'
require_relative '../support/typescript_compiler'
require 'react/converters/converter_table'

# A size class's attribute is drawn, or the build says it is not (ticket
# rjui-responsive-unmapped-attributes-are-dropped-silently). ResponsiveHelper
# drew only the keys of ATTRIBUTE_MAPPERS and skipped every other one with no
# word: measured on v2.3.28 over 16 types x their declared attributes (1676
# pairs), 111 attributes rjui draws when declared were dropped from a size
# class — minHeight, the paddings and margins among them — while iOS and
# Android redraw the node with the block merged in and hold them. The ones a
# class carries are drawn now, scoped by the size class; the others are said.
RSpec.describe 'a responsive override is drawn, or the build says it is not' do
  def converters = RjuiTools::React::Converters::ConverterTable.table
  def support_dir = File.expand_path('../support', __dir__)

  # [jsx, what the build printed]
  def emit(node, typescript: false)
    old = $stdout
    $stdout = StringIO.new
    jsx = converters.fetch(node['type']).new(JSON.parse(JSON.generate(node)), { 'use_tailwind' => true, 'typescript' => typescript })
                    .convert_node(0).strip
    [jsx, $stdout.string]
  ensure
    $stdout = old
  end

  def classes(node) = emit(node).first[/className="([^"]*)"/, 1].split

  def label(extra) = { 'type' => 'Label', 'id' => 'l', 'text' => 'Go' }.merge(extra)

  describe 'what is emitted' do
    it "the ticket's own: a narrow window's minHeight on a Button" do
      node = { 'type' => 'Button', 'id' => 'row_status_action_button', 'text' => 'x',
               'responsive' => { 'maxWidth:1023' => { 'minHeight' => 44 } } }
      expect(classes(node)).to include('max-[1023px]:min-h-[44px]')
      expect(emit(node).last).to eq('')
    end

    it 'the bounds, paddings, margins, stacking, clip, hidden, weight and opacity, scoped by the size class' do
      block = { 'minWidth' => 40, 'maxWidth' => 300, 'minHeight' => 44, 'maxHeight' => 90,
                'paddings' => [4, 8], 'topPadding' => 2, 'paddingRight' => 3, 'bottomPadding' => 5, 'paddingLeft' => 6,
                'paddingStart' => 7, 'paddingEnd' => 9,
                'margins' => 12, 'topMargin' => 6, 'rightMargin' => 1, 'bottomMargin' => 10, 'leftMargin' => 11,
                'startMargin' => 13, 'endMargin' => 14,
                'zIndex' => 3, 'hidden' => true, 'clipToBounds' => true, 'fontWeight' => 'bold', 'opacity' => 0.5 }
      got = classes(label('responsive' => { 'regular' => block })).select { |c| c.start_with?('lg:') }
      expect(got).to contain_exactly(
        'lg:min-w-[40px]', 'lg:max-w-[300px]', 'lg:min-h-[44px]', 'lg:max-h-[90px]',
        'lg:py-[0.25rem]', 'lg:px-[0.5rem]', 'lg:pt-[0.125rem]', 'lg:pr-[0.1875rem]', 'lg:pb-[0.3125rem]', 'lg:pl-[0.375rem]',
        'lg:ps-[0.4375rem]', 'lg:pe-[0.5625rem]',
        'lg:m-[0.75rem]', 'lg:mt-[0.375rem]', 'lg:mr-[0.0625rem]', 'lg:mb-[0.625rem]', 'lg:ml-[0.6875rem]',
        'lg:ms-[0.8125rem]', 'lg:me-[0.875rem]',
        'lg:z-[3]', 'lg:invisible', 'lg:overflow-hidden', 'lg:font-bold', 'lg:opacity-50'
      )
    end

    it 'a size class undoes what the base set: shown, unclipped, opaque' do
      got = classes(label('hidden' => true, 'clipToBounds' => true, 'opacity' => 0.5,
                          'responsive' => { 'regular' => { 'hidden' => false, 'clipToBounds' => false, 'opacity' => 1 } }))
      expect(got).to include('invisible', 'overflow-hidden', 'opacity-50', 'lg:visible', 'lg:overflow-visible', 'lg:opacity-100')
    end

    it 'a landscape block draws them under the landscape: variant' do
      jsx, = emit(label('responsive' => { 'landscape' => { 'minHeight' => 44, 'paddings' => 8 } }))
      expect(jsx).to include('landscape:min-h-[44px]', 'landscape:p-[0.5rem]')
    end

    it 'the emit compiles as TypeScript', :typescript_compile do
      elements = [label('responsive' => { 'regular' => { 'minHeight' => 44, 'margins' => [2, 4] } }),
                  label('responsive' => { 'landscape' => { 'paddings' => 8 } })].map { |n| emit(n, typescript: true).first }
      expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript
    end
  end

  describe 'what the build says' do
    # (alignRight is drawn since jsonui-cli 2.3.31 — the converter's own
    # classes for the merged node, BaseConverter#carry_size_class — and a
    # border key's reason says what it lacks.)
    it 'names the type, the id, the size class, the key and why, once each' do
      _jsx, said = emit(label('responsive' => { 'regular' => { 'offsetX' => 4, 'secure' => true, 'minHeight' => '@{h}',
                                                               'borderWidth' => 2, 'alignRight' => true } }))
      lines = said.lines.map { |l| l.sub(/\e\[\d+m\[WARN\]\e\[0m /, '').strip }
      expect(lines).to contain_exactly(
        "Label 'l': responsive 'regular' sets 'offsetX', which is not drawn on web — the web draws an offset as an inline transform, which no class can replace",
        "Label 'l': responsive 'regular' sets 'secure', which is not drawn on web — the web draws nothing for it here",
        "Label 'l': responsive 'regular' sets 'minHeight', which is not drawn on web — a bound value exists at run time only, and a size class is switched by classes",
        "Label 'l': responsive 'regular' sets 'borderWidth', which is not drawn on web — a border is drawn by borderWidth and borderColor together, and this node has not both"
      )
    end

    it 'says nothing of a key it draws, gravity included' do
      _jsx, said = emit(label('responsive' => { 'regular' => { 'gravity' => 'right', 'textAlign' => 'Center', 'minHeight' => 44,
                                                               'fontSize' => 18, 'paddings' => 4 } }))
      expect(said).to eq('')
    end
  end

  describe 'drawn in headless Chromium' do
    def node_modules = File.join(support_dir, 'node_modules')

    def tools_ready?
      %w[.bin/esbuild .bin/tailwindcss playwright].all? { |p| File.exist?(File.join(node_modules, p)) }
    end

    # {width => {id => [height, padding-top, padding-left, margin-top]}}
    def draw(elements, widths)
      Dir.mktmpdir('rjui_responsive_drawn') do |dir|
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
            for (const c of kids.flat(Infinity)) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
            return el;
          };
          const React = { Fragment: 'div' };
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
            for (const width of #{widths.to_json}) {
              const page = await browser.newPage({ viewport: { width, height: 800 } });
              page.on('pageerror', (e) => { console.log('PAGEERROR ' + e.message); process.exit(3); });
              await page.goto('file://#{File.join(dir, 'page.html')}');
              out[width] = await page.evaluate(() => {
                const r = {};
                for (const el of document.querySelectorAll('[id]')) {
                  const cs = getComputedStyle(el);
                  r[el.id] = [Math.round(el.getBoundingClientRect().height), parseFloat(cs.paddingTop), parseFloat(cs.paddingLeft), parseFloat(cs.marginTop)];
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

    it 'a regular window draws the size class: the height, the padding and the margin; a compact one the base' do
      HeadlessChromium.ensure!(self)
      unless tools_ready?
        reason = 'esbuild / tailwindcss / playwright are not installed under spec/support'
        raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

        skip reason
      end

      nodes = [
        { 'type' => 'View', 'id' => 'tall', 'width' => 200, 'minHeight' => 20, 'responsive' => { 'regular' => { 'minHeight' => 60 } } },
        { 'type' => 'View', 'id' => 'padded', 'width' => 200, 'paddings' => 4, 'responsive' => { 'regular' => { 'paddings' => [16, 24] } } },
        { 'type' => 'View', 'id' => 'spaced', 'width' => 200, 'height' => 10, 'topMargin' => 2, 'responsive' => { 'regular' => { 'topMargin' => 30 } } },
        { 'type' => 'View', 'id' => 'narrow', 'width' => 200, 'height' => 10, 'responsive' => { 'maxWidth:600' => { 'minHeight' => 44 } } }
      ]
      got = draw(nodes.map { |n| emit(n).first }, [400, 1200])
      compact, regular = got['400'], got['1200']
      expect([compact['tall'][0], regular['tall'][0]]).to eq([20, 60]), got.inspect
      expect([compact['padded'][1..2], regular['padded'][1..2]]).to eq([[4, 4], [16, 24]]), got.inspect
      expect([compact['spaced'][3], regular['spaced'][3]]).to eq([2, 30]), got.inspect
      expect([compact['narrow'][0], regular['narrow'][0]]).to eq([44, 10]), got.inspect
    end
  end
end
