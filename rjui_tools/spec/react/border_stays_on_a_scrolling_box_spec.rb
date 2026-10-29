# frozen_string_literal: true

require_relative '../spec_helper'
require 'json'
require 'open3'
require 'stringio'
require 'tmpdir'
require_relative '../support/headless_chromium'
require_relative '../support/typescript_compiler'
require 'react/converters/converter_table'

# A border stays on the edges of a box that scrolls its content (ticket
# rjui-border-after-pseudo-scrolls-with-overflow-content). The border is laid
# over the content by the element's ::after (absolute, inset-0), and the
# ::after of a scroll container scrolls with its content: scrolled to the end,
# measured in Chromium, none of the four edges kept a line on a View whose
# className scrolls it, a ScrollView either way, or a Collection (list, grid,
# horizontal). Such a box draws its border as an outline pulled in by its own
# width, which is drawn around the box whatever scrolls inside it — still over
# the content, still taking no layout space. A box that does not scroll keeps
# the ::after.
RSpec.describe 'a border stays on the edges of a box that scrolls its content' do
  def converters = RjuiTools::React::Converters::ConverterTable.table
  def support_dir = File.expand_path('../support', __dir__)

  def border = { 'borderWidth' => 2, 'borderColor' => '#FF0000' }

  def emit(node, typescript: false)
    old = $stdout
    $stdout = StringIO.new
    converters.fetch(node['type']).new(JSON.parse(JSON.generate(node)), { 'use_tailwind' => true, 'typescript' => typescript })
              .convert_node(0).strip
  ensure
    $stdout = old
  end

  def root_classes(node) = emit(node)[/className=(?:"([^"]*)"|\{`([^`]*)`\})/] && ($1 || $2).split

  def wide = { 'type' => 'View', 'width' => 400, 'height' => 300, 'background' => '#93C5FD' }

  def scrolling
    {
      'viewAuto' => { 'type' => 'View', 'width' => 200, 'height' => 120, 'className' => 'overflow-auto', 'child' => [wide] },
      'viewX' => { 'type' => 'View', 'width' => 200, 'height' => 120, 'className' => 'p-1 overflow-x-scroll', 'child' => [wide.merge('height' => 100)] },
      'scrollY' => { 'type' => 'ScrollView', 'width' => 200, 'height' => 120, 'child' => [wide.merge('width' => 'matchParent')] },
      'scrollX' => { 'type' => 'ScrollView', 'width' => 200, 'height' => 120, 'horizontalScroll' => true, 'child' => [wide.merge('height' => 100)] },
      'collY' => { 'type' => 'Collection', 'width' => 200, 'height' => 120, 'items' => '@{items}', 'cellClasses' => ['RowCell'] },
      'collX' => { 'type' => 'Collection', 'width' => 200, 'height' => 60, 'items' => '@{items}', 'cellClasses' => ['RowCell'], 'horizontalScroll' => true },
      'collGrid' => { 'type' => 'Collection', 'width' => 200, 'height' => 120, 'items' => '@{items}', 'cellClasses' => ['RowCell'], 'columns' => 2 }
    }.transform_values { |n| n.merge(border) }
  end

  describe 'what is emitted' do
    it 'a box that scrolls draws an outline, not an ::after' do
      scrolling.each do |id, node|
        cls = root_classes(node.merge('id' => id))
        expect(cls).to include('outline-[length:2px]', 'outline-offset-[-2px]', 'outline-[#FF0000]', 'outline-solid'), "#{id}: #{cls.inspect}"
        expect(cls.grep(/\Aafter:/)).to eq([]), id
      end
    end

    it 'control: a box that does not scroll keeps the ::after' do
      [{ 'type' => 'View', 'id' => 'v', 'child' => [] }, { 'type' => 'View', 'id' => 'v', 'clipToBounds' => true, 'child' => [] },
       { 'type' => 'View', 'id' => 'v', 'className' => 'overflow-hidden', 'child' => [] },
       { 'type' => 'ScrollView', 'id' => 's', 'scrollMode' => 'window', 'child' => [] },
       { 'type' => 'Collection', 'id' => 'c', 'items' => '@{i}', 'cellClasses' => ['C'], 'lazy' => 'none' },
       { 'type' => 'Label', 'id' => 'l', 'text' => 'x' }].each do |node|
        cls = root_classes(node.merge(border))
        expect(cls).to include('after:border-[length:2px]', 'relative'), node.inspect
        expect(cls.grep(/\Aoutline/)).to eq([]), node.inspect
      end
    end

    it 'the emit compiles as TypeScript', :typescript_compile do
      elements = scrolling.slice('viewAuto', 'scrollY').map { |id, n| emit(n.merge('id' => id), typescript: true) }
      expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript
    end
  end

  describe 'drawn in headless Chromium' do
    def node_modules = File.join(support_dir, 'node_modules')

    def tools_ready?
      %w[.bin/esbuild .bin/tailwindcss playwright].all? { |p| File.exist?(File.join(node_modules, p)) }
    end

    # {id => {edge => share of its inner 1 px line, along the middle half, that is the border's red}},
    # each box scrolled to its end on both axes
    def edges_scrolled_to_the_end(elements)
      Dir.mktmpdir('rjui_border_scroll') do |dir|
        File.write(File.join(dir, 'content.html'), elements.join("\n") + "\nw-[90px] h-[50px] shrink-0 bg-[#93C5FD] border border-white\n")
        File.write(File.join(dir, 'in.css'), %(@import "#{node_modules}/tailwindcss/index.css" source(none);\n@source "./content.html";\n))
        log, st = Open3.capture2e(File.join(node_modules, '.bin/tailwindcss'), '-i', File.join(dir, 'in.css'), '-o', File.join(dir, 'out.css'))
        raise "tailwindcss: #{log}" unless st.success?

        File.write(File.join(dir, 'app.jsx'), <<~JSX)
          const h = (tag, props, ...kids) => {
            if (typeof tag === 'function') return tag(props || {});
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
          const RowCell = ({ id }) => h('div', { id, className: 'w-[90px] h-[50px] shrink-0 bg-[#93C5FD] border border-white' });
          const data = { items: { sections: [{ cells: { data: Array.from({ length: 12 }, (_, i) => ({ n: i })) } }] } };
          for (const el of [#{elements.join(",\n")}]) { const box = document.createElement('div'); box.style.margin = '16px'; box.append(el); document.body.append(box); }
        JSX
        log, st = Open3.capture2e(File.join(node_modules, '.bin/esbuild'), File.join(dir, 'app.jsx'), '--bundle', '--jsx-factory=h', '--outfile=' + File.join(dir, 'app.js'))
        raise "esbuild: #{log}" unless st.success?

        File.write(File.join(dir, 'page.html'), %(<html><head><link rel="stylesheet" href="out.css"><style>::-webkit-scrollbar{display:none}</style></head><body><script src="app.js"></script></body></html>))
        ids = elements.map { |e| e[/\bid="([^"]+)"/, 1] }
        File.write(File.join(dir, 'read.js'), <<~JS)
          const { chromium } = require('playwright');
          (async () => {
            const browser = await chromium.launch({ executablePath: #{HeadlessChromium.path.to_json} });
            const page = await browser.newPage({ viewport: { width: 400, height: 1400 } });
            page.on('pageerror', (e) => { console.log('PAGEERROR ' + e.message); process.exit(3); });
            await page.goto('file://#{File.join(dir, 'page.html')}');
            const out = {};
            for (const id of #{ids.to_json}) {
              await page.evaluate((id) => { const e = document.getElementById(id); e.scrollTop = e.scrollHeight; e.scrollLeft = e.scrollWidth; }, id);
              const png = (await page.locator('#' + id).screenshot()).toString('base64');
              out[id] = await page.evaluate(async (png) => {
                const img = new Image(); img.src = 'data:image/png;base64,' + png; await img.decode();
                const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
                const g = c.getContext('2d'); g.drawImage(img, 0, 0);
                const red = (x, y) => { const [r, gr, b] = g.getImageData(x, y, 1, 1).data; return r > 200 && gr < 80 && b < 80; };
                const share = (pts) => Math.round(pts.filter(([x, y]) => red(x, y)).length / pts.length * 100) / 100;
                const w = img.width, h = img.height, xs = [], ys = [];
                for (let x = Math.floor(w / 4); x < 3 * w / 4; x++) xs.push(x);
                for (let y = Math.floor(h / 4); y < 3 * h / 4; y++) ys.push(y);
                return { top: share(xs.map((x) => [x, 0])), right: share(ys.map((y) => [w - 1, y])),
                         bottom: share(xs.map((x) => [x, h - 1])), left: share(ys.map((y) => [0, y])) };
              }, png);
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

    it 'scrolled to the end, every edge of every scrolling box keeps its line' do
      HeadlessChromium.ensure!(self)
      unless tools_ready?
        reason = 'esbuild / tailwindcss / playwright are not installed under spec/support'
        raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

        skip reason
      end

      got = edges_scrolled_to_the_end(scrolling.map { |id, n| emit(n.merge('id' => id)) })
      all = { 'top' => 1.0, 'right' => 1.0, 'bottom' => 1.0, 'left' => 1.0 }
      expect(got).to eq(scrolling.keys.to_h { |id| [id, all] }), got.inspect
    end
  end
end
