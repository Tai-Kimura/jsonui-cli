# frozen_string_literal: true

require_relative '../spec_helper'
require 'json'
require 'open3'
require 'stringio'
require 'tmpdir'
require_relative '../support/headless_chromium'
require_relative '../support/typescript_compiler'
require 'react/converters/converter_table'

# A bordered ScrollView or Collection, or a Collection with a padding, is a
# still box around a scroll box (2.3.32). Until 2.3.34 the whole className was
# on the still box (ticket rjui-scrollview-classname-overflow-makes-outer-box-
# scroll). Measured in Chromium over 14 shapes x 17 classes: the still box
# never scrolled (its scrollHeight was its clientHeight in all 238), so the
# border did not move — but the classes that steer a scroll did nothing there:
# overscroll-* let the wheel go on to the page, scroll-smooth did not smooth,
# scroll-pt-* did not pad. They go on the scroll box now; an overflow hidden /
# clip / visible on the axis it scrolls along would stop it, so stays and is
# said at build. And a child with a z-index (a sticky header, z-10) covered the
# still box's ::after border (ticket rjui-sticky-child-covers-still-box-
# border): the bordered scroll box is isolated.
RSpec.describe 'a still box’s className: the scroll classes go on the scroll box' do
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

  def boxes(jsx, id)
    [jsx[/\A\s*<div className="([^"]*)"/, 1].to_s.split, jsx[/<div id="#{id}"[^>]*?className="([^"]*)"/, 1].to_s.split]
  end

  def border = { 'borderWidth' => 1, 'borderColor' => '#FF0000' }

  describe 'what is emitted' do
    it 'a bordered ScrollView: the scroll classes inside, whatever their variants; the rest on the still box' do
      jsx, said = emit({ 'type' => 'ScrollView', 'id' => 's', 'height' => 100, 'child' => [],
                         'className' => 'max-h-[9rem] sticky md:overflow-auto overscroll-y-contain !scroll-pt-4 snap-y overflow-x-hidden' }.merge(border))
      outer, inner = boxes(jsx, 's')
      expect(inner).to include('isolate', 'md:overflow-auto', 'overscroll-y-contain', '!scroll-pt-4', 'snap-y', 'overflow-x-hidden')
      expect(outer).to include('max-h-[9rem]', 'sticky')
      expect(outer.grep(/overflow|overscroll|scroll-|snap-/)).to eq([])
      expect(said).to eq([])
    end

    it 'a Collection with a padding: the same, on its scroll container' do
      jsx, said = emit({ 'type' => 'Collection', 'id' => 'c', 'paddings' => [8], 'items' => '@{items}', 'cellClasses' => ['RowCell'],
                         'className' => 'max-h-[9rem] overscroll-contain' })
      outer, inner = boxes(jsx, 'c')
      expect(inner).to include('overscroll-contain')
      expect(outer).to include('max-h-[9rem]')
      expect(outer).not_to include('overscroll-contain')
      expect(inner).not_to include('isolate') # no border, no ::after to keep over the cells
      expect(said).to eq([])
    end

    it 'an overflow that would stop it scrolling stays on the still box and is said' do
      { { 'type' => 'ScrollView', 'child' => [] }.merge(border) => 'overflow-hidden md:overflow-y-clip',
        { 'type' => 'ScrollView', 'orientation' => 'horizontal', 'child' => [] }.merge(border) => 'overflow-x-visible',
        { 'type' => 'Collection', 'paddings' => [8], 'items' => '@{items}', 'cellClasses' => ['RowCell'] } => 'overflow-y-hidden' }.each do |node, stops|
        jsx, said = emit(node.merge('id' => 'x', 'className' => "max-h-[9rem] #{stops}"))
        outer, inner = boxes(jsx, 'x')
        expect(outer).to include(*stops.split)
        expect(inner & stops.split).to eq([])
        expect(said).to eq(["#{node['type']} 'x': className '#{stops}' is not written on the box that scrolls (it would stop it " \
                            'scrolling) — write scrollEnabled: false to stop the scrolling, or remove it']), node.inspect
      end
    end

    it 'control: a ScrollView with no still box, a Collection that does not scroll, a bound className — the className as written' do
      jsx, said = emit({ 'type' => 'ScrollView', 'id' => 'p', 'className' => 'overflow-hidden overscroll-contain', 'child' => [] })
      expect(jsx).to start_with('<div id="p"')
      expect(boxes(jsx, 'p').last).to include('overflow-hidden', 'overscroll-contain')
      expect(said).to eq([])

      jsx, said = emit({ 'type' => 'Collection', 'id' => 'n', 'lazy' => 'none', 'paddings' => [8], 'items' => '@{items}',
                         'cellClasses' => ['RowCell'], 'className' => 'overflow-hidden overscroll-contain' })
      expect(boxes(jsx, 'n').first).to include('overflow-hidden', 'overscroll-contain')
      expect(said).to eq([])

      jsx, = emit({ 'type' => 'ScrollView', 'id' => 'b', 'className' => '@{boxClass}', 'child' => [] }.merge(border))
      expect(jsx.lines.first).to include('boxClass')
      expect(jsx.lines[1]).not_to include('boxClass')
    end

    it 'the emit compiles as TypeScript', :typescript_compile do
      element, = emit({ 'type' => 'ScrollView', 'id' => 's', 'className' => 'max-h-[9rem] overscroll-contain', 'child' => [] }.merge(border),
                      typescript: true)
      expect(TypeScriptCompiler.component(element)).to compile_as_typescript
    end
  end

  describe 'drawn in headless Chromium' do
    def node_modules = File.join(support_dir, 'node_modules')

    def tools_ready?
      %w[.bin/esbuild .bin/tailwindcss playwright].all? { |p| File.exist?(File.join(node_modules, p)) }
    end

    def row(cls, bg) = { 'type' => 'View', 'width' => 'matchParent', 'height' => 44, 'className' => cls, 'background' => bg, 'child' => [] }

    # A bordered ScrollView with a sticky header (z-10), overscroll-y-none in
    # its className: wheeled past its end, {page: how far the page went, top:
    # the share of the border's top edge that is red}
    def draw(element)
      Dir.mktmpdir('rjui_still_class_name') do |dir|
        File.write(File.join(dir, 'content.html'), element)
        File.write(File.join(dir, 'in.css'), %(@import "#{node_modules}/tailwindcss/index.css" source(none);\n@source "./content.html";\n))
        log, st = Open3.capture2e(File.join(node_modules, '.bin/tailwindcss'), '-i', File.join(dir, 'in.css'), '-o', File.join(dir, 'out.css'))
        raise "tailwindcss: #{log}" unless st.success?

        File.write(File.join(dir, 'app.jsx'), <<~JSX)
          const h = (tag, props, ...kids) => {
            const el = document.createElement(tag);
            for (const [k, v] of Object.entries(props || {})) { if (k === 'className') el.className = v; else if (k === 'id') el.id = v; }
            for (const c of kids.flat(Infinity)) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
            return el;
          };
          const React = { Fragment: 'div' };
          const box = document.createElement('div'); box.style.cssText = 'margin:300px 24px 1400px;width:200px;display:flex;flex-direction:column';
          box.append(#{element}); document.body.append(box);
        JSX
        log, st = Open3.capture2e(File.join(node_modules, '.bin/esbuild'), File.join(dir, 'app.jsx'), '--bundle', '--jsx-factory=h', '--outfile=' + File.join(dir, 'app.js'))
        raise "esbuild: #{log}" unless st.success?

        File.write(File.join(dir, 'page.html'), %(<html><head><link rel="stylesheet" href="out.css"><style>::-webkit-scrollbar{display:none}body{margin:0}</style></head><body><script src="app.js"></script></body></html>))
        File.write(File.join(dir, 'read.js'), <<~JS)
          const { chromium } = require('playwright');
          (async () => {
            const browser = await chromium.launch({ executablePath: #{HeadlessChromium.path.to_json} });
            const page = await browser.newPage({ viewport: { width: 400, height: 600 } });
            page.on('pageerror', (e) => { console.log('PAGEERROR ' + e.message); process.exit(3); });
            await page.goto('file://#{File.join(dir, 'page.html')}');
            const r = await page.evaluate(() => { const x = document.getElementById('s').parentElement.getBoundingClientRect(); return [x.x, x.y, x.width, x.height]; });
            await page.mouse.move(r[0] + r[2] / 2, r[1] + r[3] / 2);
            for (let k = 0; k < 6; k++) { await page.mouse.wheel(0, 400); await page.waitForTimeout(60); }
            await page.waitForTimeout(300);
            const moved = await page.evaluate(() => window.scrollY);
            await page.evaluate(() => window.scrollTo(0, 0));
            const png = (await page.screenshot({ clip: { x: r[0], y: r[1], width: r[2], height: 4 } })).toString('base64');
            const top = await page.evaluate(async ([png, w]) => {
              const img = new Image(); img.src = 'data:image/png;base64,' + png; await img.decode();
              const c = document.createElement('canvas'); c.width = img.width; c.height = img.height; const g = c.getContext('2d'); g.drawImage(img, 0, 0);
              const xs = Array.from({ length: Math.floor(w / 2) }, (_, i) => Math.floor(w / 4) + i);
              return Math.round(xs.filter((x) => { const [r, gr, b] = g.getImageData(x, 0, 1, 1).data; return r > 200 && gr < 80 && b < 80; }).length / xs.length * 100) / 100;
            }, [png, Math.round(r[2])]);
            console.log('AT' + JSON.stringify({ page: moved, top, inner: await page.evaluate(() => document.getElementById('s').scrollTop) }));
            await browser.close();
          })();
        JS
        log, st = Open3.capture2e({ 'NODE_PATH' => node_modules }, 'node', File.join(dir, 'read.js'), chdir: support_dir)
        raise "playwright: #{log}" unless st.success?

        JSON.parse(log[/AT(\{.*\})/, 1] || raise("no result in:\n#{log}"))
      end
    end

    it 'the wheel stops at the scroll box’s end, and the sticky header leaves the border on' do
      HeadlessChromium.ensure!(self)
      unless tools_ready?
        reason = 'esbuild / tailwindcss / playwright are not installed under spec/support'
        raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

        skip reason
      end

      node = { 'type' => 'ScrollView', 'id' => 's', 'orientation' => 'vertical', 'width' => 200, 'height' => 160, 'background' => '#FFFFFF',
               'className' => 'overscroll-y-none',
               'child' => [row('sticky top-0 z-10', '#FDE68A')] + Array.new(8) { row('', '#DBEAFE') } }.merge(border)
      got = draw(emit(node).first)
      expect(got['inner']).to be > 0
      expect(got).to include('page' => 0, 'top' => 1)
    end
  end
end
