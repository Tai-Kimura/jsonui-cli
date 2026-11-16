# frozen_string_literal: true

require_relative '../spec_helper'
require 'json'
require 'open3'
require 'stringio'
require 'tmpdir'
require_relative '../support/headless_chromium'
require_relative '../support/typescript_compiler'
require 'react/converters/converter_table'

# A bordered ScrollView or Collection keeps its border while it has focus
# (ticket rjui-scroll-border-outline-replaced-by-focus-ring). Since 2.3.29 a
# box that scrolls drew its border as its own outline, so it stayed on the
# edges whatever scrolled — and an app's :focus-visible outline replaced it
# when the box took focus. Measured in Chromium (a 200 x 120 scroll box,
# cells touching its edges, an app outline of 3px at an offset of 2px, corner
# 0 and 12, at rest / focused / scrolled to the end): the outline lost its
# border to the focus ring; an inset box-shadow lay under the cells; a CSS
# border held but pushed the content 2px (against ruling B); a fixed ::after
# in a contained or transformed box drew nothing; a still box around the
# scroll box, its ::after the border, held in every state beside the ring and
# pushed nothing. A ScrollView and a Collection that scroll draw that box now;
# a View whose className scrolls it keeps the outline and is said at build.
RSpec.describe 'a bordered scroll box keeps its border under a focus ring' do
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

  def border = { 'borderWidth' => 2, 'borderColor' => '#FF0000', 'cornerRadius' => 12 }
  def tall = { 'type' => 'View', 'width' => 400, 'height' => 300, 'background' => '#93C5FD' }

  def boxes
    {
      'scroll' => { 'type' => 'ScrollView', 'width' => 200, 'height' => 120, 'child' => [tall] }.merge(border),
      'coll' => { 'type' => 'Collection', 'width' => 200, 'height' => 120, 'items' => '@{items}', 'cellClasses' => ['RowCell'] }.merge(border),
      'viewOverflow' => { 'type' => 'View', 'width' => 200, 'height' => 120, 'className' => 'overflow-auto', 'child' => [tall] }.merge(border)
    }
  end

  describe 'what is emitted' do
    it 'a ScrollView and a Collection: the border on a still box, the scroll and the id inside it' do
      %w[scroll coll].each do |id|
        jsx, said = emit(boxes[id].merge('id' => id))
        outer = jsx[/\A\s*<div className="([^"]*)"/, 1].to_s.split
        inner = jsx[/<div id="#{id}"[^>]*?className="([^"]*)"/, 1].to_s.split
        expect(outer).to include('relative', 'after:border-[length:2px]', 'after:border-[#FF0000]', 'rounded-xl'), "#{id}: #{outer}"
        expect(inner).to include('rounded-[inherit]', 'overflow-y-auto'), "#{id}: #{inner}"
        expect(inner.grep(/\A(after:|outline)/)).to eq([]), id
        expect(said).to eq([]), id
      end
    end

    it 'a View whose className scrolls it keeps the outline, and says how to keep its border' do
      jsx, said = emit(boxes['viewOverflow'].merge('id' => 'v'))
      expect(jsx).to include('outline-[length:2px]')
      expect(said).to eq(["View 'v': its border is an outline, because its className scrolls it, and a focus ring's outline " \
                          '(:focus-visible) replaces it while it has focus — write the scrolling as a ScrollView, or put the ' \
                          'border on a View around the one that scrolls, and the border stays'])
    end

    it 'control: a ScrollView without a border, or one the window scrolls, is one element' do
      [{ 'type' => 'ScrollView', 'id' => 's', 'child' => [] },
       { 'type' => 'ScrollView', 'id' => 's', 'scrollMode' => 'window', 'child' => [] }.merge(border)].each do |node|
        jsx, = emit(node)
        expect(jsx).to start_with('<div id="s"'), node.inspect
      end
    end

    it 'the emit compiles as TypeScript', :typescript_compile do
      elements = [emit(boxes['scroll'].merge('id' => 'scroll'), typescript: true).first]
      expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript
    end
  end

  describe 'drawn in headless Chromium' do
    def node_modules = File.join(support_dir, 'node_modules')

    def tools_ready?
      %w[.bin/esbuild .bin/tailwindcss playwright].all? { |p| File.exist?(File.join(node_modules, p)) }
    end

    # {id => {state => {border:, ring:}}}: the share of the box's inner 1px
    # line (the middle half of each side) that is the border's red, and of a
    # line 4px outside it that is the app's focus ring
    def draw(elements)
      Dir.mktmpdir('rjui_focus_border') do |dir|
        File.write(File.join(dir, 'content.html'), elements.join("\n") + "\nw-[90px] h-[50px] shrink-0 bg-[#93C5FD]\n")
        File.write(File.join(dir, 'in.css'), %(@import "#{node_modules}/tailwindcss/index.css" source(none);\n@source "./content.html";\n))
        log, st = Open3.capture2e(File.join(node_modules, '.bin/tailwindcss'), '-i', File.join(dir, 'in.css'), '-o', File.join(dir, 'out.css'))
        raise "tailwindcss: #{log}" unless st.success?

        File.write(File.join(dir, 'app.jsx'), <<~JSX)
          const h = (tag, props, ...kids) => {
            props = props || {};
            if (typeof tag === 'function') return tag(props);
            const el = document.createElement(tag);
            for (const [k, v] of Object.entries(props)) {
              if (k === 'className') el.className = v;
              else if (k === 'style') { for (const [p, x] of Object.entries(v || {})) if (x != null) { if (p.startsWith('--')) el.style.setProperty(p, x); else el.style[p] = x; } }
              else if (k === 'id') { el.id = v; el.tabIndex = 0; }
            }
            for (const c of kids.flat(Infinity)) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
            return el;
          };
          const React = { Fragment: 'div' };
          const ColorManager = { resolveColor: (c) => c };
          const RowCell = ({ id }) => { const e = h('div', { className: 'w-[90px] h-[50px] shrink-0 bg-[#93C5FD]' }); return e; };
          const data = { items: { sections: [{ cells: { data: Array.from({ length: 8 }, () => ({})) } }] } };
          for (const el of [#{elements.join(",\n")}]) { const box = document.createElement('div'); box.style.margin = '24px'; box.append(el); document.body.append(box); }
        JSX
        log, st = Open3.capture2e(File.join(node_modules, '.bin/esbuild'), File.join(dir, 'app.jsx'), '--bundle', '--jsx-factory=h', '--outfile=' + File.join(dir, 'app.js'))
        raise "esbuild: #{log}" unless st.success?

        # an app's own focus ring, as a stylesheet writes one
        File.write(File.join(dir, 'page.html'), %(<html><head><link rel="stylesheet" href="out.css"><style>:focus-visible{outline:3px solid #2563eb;outline-offset:2px}::-webkit-scrollbar{display:none}</style></head><body><script src="app.js"></script></body></html>))
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
              out[id] = {};
              for (const state of ['rest', 'focused', 'scrolled', 'focusedScrolled']) {
                await page.evaluate(([id, state]) => {
                  const e = document.getElementById(id);
                  document.activeElement && document.activeElement.blur();
                  e.scrollTop = state.includes('crolled') ? 9999 : 0; e.scrollLeft = 0;
                  if (state.startsWith('focused')) e.focus({ focusVisible: true });
                }, [id, state]);
                await page.waitForTimeout(50);
                // the box: the still box when there is one, else the element
                const r = await page.evaluate((id) => { const e = document.getElementById(id); const b = e.parentElement.className.includes('after:border') ? e.parentElement : e; const x = b.getBoundingClientRect(); return [x.x, x.y, x.width, x.height]; }, id);
                const png = (await page.screenshot({ clip: { x: r[0] - 8, y: r[1] - 8, width: r[2] + 16, height: r[3] + 16 } })).toString('base64');
                out[id][state] = await page.evaluate(async ([png, w, h]) => {
                  const img = new Image(); img.src = 'data:image/png;base64,' + png; await img.decode();
                  const c = document.createElement('canvas'); c.width = img.width; c.height = img.height; const g = c.getContext('2d'); g.drawImage(img, 0, 0);
                  const is = (x, y, f) => f(...g.getImageData(x, y, 1, 1).data);
                  const red = (r, gr, b) => r > 200 && gr < 80 && b < 80, blue = (r, gr, b) => b > 200 && r < 80 && gr < 140;
                  const o = 8, mid = (a, n) => Array.from({ length: Math.floor(n / 2) }, (_, i) => a + Math.floor(n / 4) + i);
                  const share = (pts, f) => Math.round(pts.filter(([x, y]) => is(x, y, f)).length / pts.length * 100) / 100;
                  const inner = [...mid(o, w).map((x) => [x, o]), ...mid(o, w).map((x) => [x, o + h - 1]), ...mid(o, h).map((y) => [o, y]), ...mid(o, h).map((y) => [o + w - 1, y])];
                  const ring = [...mid(o, w).map((x) => [x, o - 4]), ...mid(o, h).map((y) => [o - 4, y])];
                  return { border: share(inner, red), ring: share(ring, blue) };
                }, [png, Math.round(r[2]), Math.round(r[3])]);
              }
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

    it 'focused, scrolled, both: the border stays on every side beside the ring' do
      HeadlessChromium.ensure!(self)
      unless tools_ready?
        reason = 'esbuild / tailwindcss / playwright are not installed under spec/support'
        raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

        skip reason
      end

      got = draw(boxes.map { |id, n| emit(n.merge('id' => id)).first })
      %w[scroll coll].each do |id|
        expect(got[id]).to eq('rest' => { 'border' => 1, 'ring' => 0 }, 'focused' => { 'border' => 1, 'ring' => 1 },
                              'scrolled' => { 'border' => 1, 'ring' => 0 }, 'focusedScrolled' => { 'border' => 1, 'ring' => 1 }), "#{id}: #{got.inspect}"
      end
      # the outline the View keeps: the ring takes its place (and the build says so)
      expect(got['viewOverflow']['focused']).to eq('border' => 0, 'ring' => 1), got.inspect
      expect(got['viewOverflow']['rest']['border']).to eq(1), got.inspect
    end
  end
end
