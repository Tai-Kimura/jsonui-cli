# frozen_string_literal: true

require_relative '../spec_helper'
require 'json'
require 'open3'
require 'stringio'
require 'tmpdir'
require_relative '../support/headless_chromium'
require_relative '../support/typescript_compiler'
require 'react/converters/converter_table'

# A bound attribute yields to the size class that overrides it (ticket
# rjui-bound-width-inline-style-beats-responsive-width). A bound value is an
# inline style, and an inline style beats every class: measured on v2.3.29 in
# Chromium, with the base bound and a 'maxWidth:1024' or 'landscape' literal,
# the bound width, height, bounds, paddings, margins, fontSize, cornerRadius,
# opacity, weight, textAlign, fontWeight and clip all held at 390 and in
# landscape. When a size class overrides a bound attribute, its value moves to
# a `--jui-sc-*` custom property of the element and a class reads it, so the
# size class's variant wins in its windows; a bound attribute no size class
# overrides keeps its inline style.
RSpec.describe 'a bound value yields to the size class that overrides it' do
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

  # The ticket's own field.
  def field = { 'type' => 'TextField', 'id' => 'spec_text_input', 'width' => '@{textWidth}',
                'responsive' => { 'maxWidth:1024' => { 'width' => 'matchParent' } } }

  describe 'what is emitted' do
    it "the ticket's field: the bound width rides --jui-sc-width, read by a class beside the size class's" do
      out = emit(field)
      expect(out).to include('max-[1024px]:w-full', '[width:var(--jui-sc-width)]', "'--jui-sc-width': `${data.textWidth}px`")
      expect(out).not_to match(/[{,]\s*width: `/)
    end

    it 'only what a size class overrides moves; the rest of the bound values stay inline' do
      out = emit({ 'type' => 'View', 'id' => 'v', 'width' => '@{w}', 'paddings' => '@{p}', 'opacity' => '@{o}',
                   'responsive' => { 'regular' => { 'paddings' => 4 } }, 'child' => [] })
      expect(out).to include('[padding:var(--jui-sc-padding)]', "'--jui-sc-padding'", 'width: `${data.w}px`', 'opacity: data.o')
      expect(out).not_to include('--jui-sc-width', '--jui-sc-opacity')
    end

    it "a Label's bound textAlign moves with its justify-content, for a textAlign or a gravity override" do
      [{ 'textAlign' => 'Center' }, { 'gravity' => 'right' }].each do |over|
        out = emit({ 'type' => 'Label', 'id' => 'l', 'text' => 'x', 'textAlign' => '@{a}', 'responsive' => { 'landscape' => over } })
        expect(out).to include('[justify-content:var(--jui-sc-justify-content)]'), over.inspect
      end
    end

    it 'the --jui-sc- names are no other custom property of the converters' do
      lib = Dir[File.expand_path('../../lib/react/**/*.rb', __dir__)].map { |f| File.read(f) }.join
      others = lib.scan(/--jui-[a-z-]+/).uniq.reject { |n| n.start_with?('--jui-sc-') }
      expect(others).not_to be_empty
      expect(others.select { |n| n.start_with?('--jui-sc') }).to eq([])
    end

    it 'control: a bound attribute without a size class is as it was' do
      out = emit({ 'type' => 'TextField', 'id' => 't', 'width' => '@{textWidth}' })
      expect(out).to include('width: `${data.textWidth}px`')
      expect(out).not_to include('--jui-sc-')
    end

    it 'the emit compiles as TypeScript', :typescript_compile do
      elements = [emit(field, typescript: true),
                  emit({ 'type' => 'Label', 'id' => 'l', 'text' => 'x', 'textAlign' => '@{a}', 'fontSize' => '@{s}',
                         'responsive' => { 'landscape' => { 'textAlign' => 'Center', 'fontSize' => 12 } } }, typescript: true)]
      ambient = TypeScriptCompiler::AMBIENT + <<~TS
        declare const data: { textWidth: number; a: string; s: number; onSpecTextInputIsFocusedChange?: (v: boolean) => void };
        declare const spec_text_inputRef: unknown;
        declare const specTextInputRef: unknown;
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

    # Each attribute bound at the base and given a literal by 'maxWidth:1024'
    # and by 'landscape': [attribute, bound, literal, property, type].
    def rows = [
      ['width', 320, 'matchParent', 'width', 'TextField'], ['height', 80, 30, 'height', 'View'],
      ['minWidth', 300, 120, 'minWidth', 'View'], ['maxHeight', 90, 15, 'maxHeight', 'View'],
      ['paddings', 20, 6, 'paddingTop', 'View'], ['topMargin', 20, 6, 'marginTop', 'View'],
      ['fontSize', 24, 12, 'fontSize', 'Label'], ['cornerRadius', 20, 4, 'borderTopLeftRadius', 'View'],
      ['opacity', 0.3, 0.9, 'opacity', 'View'], ['textAlign', 'right', 'Center', 'textAlign', 'Label']
    ]

    def nodes
      rows.each_with_index.flat_map do |(attr, _bound, lit, _prop, type), i|
        { 'w' => 'maxWidth:1024', 'l' => 'landscape' }.map do |tag, key|
          n = { 'type' => type, 'id' => "#{attr}_#{tag}", attr => "@{v#{i}}", 'responsive' => { key => { attr => lit } } }
          n['text'] = 'Go' if type == 'Label'
          n['width'] ||= 200 unless %w[width minWidth].include?(attr)
          n['height'] ||= 40 unless %w[height maxHeight].include?(attr) || type == 'Label'
          n['child'] = [{ 'type' => 'View', 'width' => 'matchParent', 'height' => 400 }] if attr == 'maxHeight'
          n
        end
      end
    end

    # {window => {id => computed value of the row's property}}
    def draw(elements, windows)
      Dir.mktmpdir('rjui_bound_size_class') do |dir|
        File.write(File.join(dir, 'content.html'), elements.join("\n"))
        File.write(File.join(dir, 'in.css'), %(@import "#{node_modules}/tailwindcss/index.css" source(none);\n@source "./content.html";\n))
        log, st = Open3.capture2e(File.join(node_modules, '.bin/tailwindcss'), '-i', File.join(dir, 'in.css'), '-o', File.join(dir, 'out.css'))
        raise "tailwindcss: #{log}" unless st.success?

        refs = elements.join("\n").scan(/ref=\{(\w+)\}/).flatten.uniq.map { |r| "const #{r} = null;" }.join("\n")
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
          // what the run-time hook read before 2.3.30
          const isLandscape = matchMedia('(orientation: landscape)').matches;
          #{refs}
          const data = #{rows.each_with_index.to_h { |r, i| ["v#{i}", r[1]] }.to_json};
          for (const el of [#{elements.join(",\n")}]) { const box = document.createElement('div'); box.style.cssText = 'display:flex;width:1000px'; box.append(el); document.body.append(box); }
        JSX
        log, st = Open3.capture2e(File.join(node_modules, '.bin/esbuild'), File.join(dir, 'app.jsx'), '--bundle', '--jsx-factory=h', '--outfile=' + File.join(dir, 'app.js'))
        raise "esbuild: #{log}" unless st.success?

        reads = rows.flat_map { |attr, _, _, prop, _| [["#{attr}_w", prop], ["#{attr}_l", prop]] }.to_h
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
              out[name] = await page.evaluate((reads) => Object.fromEntries(Object.entries(reads).map(([id, p]) => [id, getComputedStyle(document.getElementById(id))[p]])), #{reads.to_json});
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

    it 'the size class shows in its windows (390 wide, landscape), the bound value in the others (1200 wide, portrait)' do
      HeadlessChromium.ensure!(self)
      unless tools_ready?
        reason = 'esbuild / tailwindcss / playwright are not installed under spec/support'
        raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

        skip reason
      end

      got = draw(nodes.map { |n| emit(n) }, 'narrow' => { width: 390, height: 300 }, 'wide' => { width: 1200, height: 1400 },
                                             'landscape' => { width: 1200, height: 600 }, 'portrait' => { width: 390, height: 844 })
      shown = ->(window, tag) { rows.to_h { |attr, *| [attr, got[window]["#{attr}_#{tag}"]] } }
      literal = { 'width' => '1000px', 'height' => '30px', 'minWidth' => '120px', 'maxHeight' => '15px', 'paddings' => '6px',
                  'topMargin' => '6px', 'fontSize' => '12px', 'cornerRadius' => '4px', 'opacity' => '0.9', 'textAlign' => 'center' }
      bound = { 'width' => '320px', 'height' => '80px', 'minWidth' => '300px', 'maxHeight' => '90px', 'paddings' => '20px',
                'topMargin' => '20px', 'fontSize' => '24px', 'cornerRadius' => '20px', 'opacity' => '0.3', 'textAlign' => 'right' }
      expect(shown.('narrow', 'w')).to eq(literal), got.inspect
      expect(shown.('wide', 'w')).to eq(bound), got.inspect
      expect(shown.('landscape', 'l')).to eq(literal), got.inspect
      expect(shown.('portrait', 'l')).to eq(bound), got.inspect
    end
  end
end
