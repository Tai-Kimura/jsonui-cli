# frozen_string_literal: true

require_relative '../spec_helper'
require 'json'
require 'open3'
require 'tmpdir'
require_relative '../support/headless_chromium'
require_relative '../support/typescript_compiler'
require 'react/converters/converter_table'

# scrollEnabled false stops the user's scrolling only; a scrollTo still moves
# the box (attribute_definitions Collection.scrollEnabled, the 4f ruling
# 2026-09-27). Until jsonui-cli 2.3.28, measured in Chromium (tickets
# rjui-scrollview-bound-scrollenabled-never-stops-scrolling and
# rjui-horizontal-collection-scrollenabled-false-still-scrolls):
#   a bound false (ScrollView, Collection) came out as nothing — the box kept
#     its overflow-*-auto and a wheel scrolled it (scrollTop 0 -> 120);
#   a declared false on a vertical Collection dropped the box — the cells drew
#     past it and a scrollTo moved nothing; on a horizontal one it kept
#     overflow-x-auto and a wheel scrolled it (scrollLeft 0 -> 120).
# Now the box stays and clips (overflow hidden), declared or bound, as a
# ScrollView's declared false always did.
RSpec.describe 'a bound scrollEnabled false stops the scrolling a declared one stops' do
  def converters = RjuiTools::React::Converters::ConverterTable.table
  def support_dir = File.expand_path('../support', __dir__)

  def jsx(node, typescript: false)
    converters.fetch(node['type']).new(node, { 'use_tailwind' => true, 'typescript' => typescript }).convert_node(0).strip
  end

  def scroll(id, enabled)
    { 'type' => 'ScrollView', 'id' => id, 'width' => 200, 'height' => 100, 'scrollEnabled' => enabled,
      'child' => [{ 'type' => 'View', 'id' => "#{id}_tall", 'width' => 200, 'height' => 400, 'background' => '#DDDDDD' }] }
  end

  def collection(extra)
    { 'type' => 'Collection', 'id' => 'c', 'height' => 100, 'items' => '@{items}', 'cellClasses' => ['RowCell'],
      'scrollEnabled' => '@{on}' }.merge(extra)
  end

  describe 'what is emitted' do
    it 'a ScrollView: an inline overflow hidden on a bound false, nothing otherwise' do
      expect(jsx(scroll('s', '@{on}'))).to include("style={{ overflow: data.on === false ? 'hidden' : undefined }}")
      expect(jsx(scroll('s', '@{on}').merge('scrollMode' => 'window'))).not_to include('overflow:')
    end

    it 'a Collection: a bound false keeps the box and clips, as a declared false does' do
      both = "overflowY: data.on === false ? 'hidden' : undefined, overflowX: data.on === false ? 'hidden' : undefined"
      expect(jsx(collection({}))).to include(both)
      expect(jsx(collection('columns' => 2))).to include(both)
      expect(jsx(collection('horizontalScroll' => true))).to include(
        "overflowX: data.on === false ? 'hidden' : undefined, overflowY: data.on === false ? 'hidden' : undefined"
      )
      expect(jsx(collection('horizontalScroll' => true))).not_to include('flexWrap')
      expect(jsx(collection('lazy' => '@{lz}'))).to include(
        "overflowY: data.lz === 'none' ? 'visible' : (data.on === false ? 'hidden' : 'auto')"
      )
    end

    it 'control: the declared forms are as they were' do
      expect(jsx(scroll('s', false))).to include('overflow-hidden')
      expect(jsx(scroll('s', false))).not_to include('style=')
      expect(jsx(collection('scrollEnabled' => false))).to include('overflow-hidden')
      expect(jsx(collection('scrollEnabled' => false, 'horizontalScroll' => true))).to include('overflow-hidden')
      expect(jsx(collection('scrollEnabled' => false, 'horizontalScroll' => true))).not_to include('overflow-x-auto')
    end

    it 'the emit compiles as TypeScript', :typescript_compile do
      ambient = TypeScriptCompiler::AMBIENT + <<~TS
        declare const data: { on?: boolean };
        declare namespace React { type CSSProperties = { [property: string]: string | number | undefined } }
      TS
      expect(TypeScriptCompiler.component(jsx(scroll('s', '@{on}'), typescript: true))).to compile_as_typescript.with_ambient(ambient)
    end
  end

  describe 'drawn in headless Chromium' do
    def node_modules = File.join(support_dir, 'node_modules')

    def tools_ready?
      %w[.bin/esbuild .bin/tailwindcss playwright].all? { |p| File.exist?(File.join(node_modules, p)) }
    end

    def ensure_tools!
      HeadlessChromium.ensure!(self)
      return if tools_ready?

      reason = 'esbuild / tailwindcss / playwright are not installed under spec/support'
      raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

      skip reason
    end

    # Each element alone in a 400 x 500 window (another one's overflow would
    # widen the page): {id => {wheel: [before, after], to: after a
    # programmatic scroll to 50, page: the window's own scroll}}, along the
    # element's axis (x for an id ending in X).
    def wheel(elements, data)
      Dir.mktmpdir('rjui_bound_scroll') do |dir|
        File.write(File.join(dir, 'content.html'), elements.join("\n") + "\nw-[80px] h-[40px] shrink-0\n")
        File.write(File.join(dir, 'in.css'), %(@import "#{node_modules}/tailwindcss/index.css" source(none);\n@source "./content.html";\n))
        log, st = Open3.capture2e(File.join(node_modules, '.bin/tailwindcss'), '-i', File.join(dir, 'in.css'), '-o', File.join(dir, 'out.css'))
        raise "tailwindcss: #{log}" unless st.success?

        File.write(File.join(dir, 'app.jsx'), <<~JSX)
          const h = (tag, props, ...kids) => {
            if (typeof tag === 'function') return tag(props || {});
            const el = document.createElement(tag);
            for (const [k, v] of Object.entries(props || {})) {
              if (k === 'className') el.className = v;
              else if (k === 'style') { for (const [p, x] of Object.entries(v)) if (x != null) el.style[p] = x; }
              else if (k === 'id') el.id = v;
            }
            for (const c of kids.flat(Infinity)) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
            return el;
          };
          const React = { Fragment: 'div' };
          const ColorManager = { resolveColor: (c) => c };
          const RowCell = ({ id }) => h('div', { id, className: 'w-[80px] h-[40px] shrink-0' }, id);
          const data = #{data.to_json};
          for (const el of [#{elements.join(",\n")}]) { const box = document.createElement('div'); box.style.margin = '12px'; box.append(el); document.body.append(box); }
        JSX
        log, st = Open3.capture2e(File.join(node_modules, '.bin/esbuild'), File.join(dir, 'app.jsx'), '--bundle', '--jsx-factory=h', '--outfile=' + File.join(dir, 'app.js'))
        raise "esbuild: #{log}" unless st.success?

        File.write(File.join(dir, 'page.html'), %(<html><head><link rel="stylesheet" href="out.css"></head><body><script src="app.js"></script></body></html>))
        ids = elements.map { |e| e[/\bid="([^"]+)"/, 1] }
        File.write(File.join(dir, 'read.js'), <<~JS)
          const { chromium } = require('playwright');
          (async () => {
            const browser = await chromium.launch({ executablePath: #{HeadlessChromium.path.to_json} });
            const out = {};
            for (const id of #{ids.to_json}) {
              const x = id.endsWith('X');
              const page = await browser.newPage({ viewport: { width: 400, height: 500 } });
              page.on('pageerror', (e) => { console.log('PAGEERROR ' + e.message); process.exit(3); });
              await page.goto('file://#{File.join(dir, 'page.html')}');
              await page.evaluate((id) => { for (const b of [...document.body.children]) if (!b.querySelector('#' + id)) b.remove(); }, id);
              const read = () => page.evaluate(([id, x]) => { const e = document.getElementById(id); return x ? e.scrollLeft : e.scrollTop; }, [id, x]);
              const box = await page.locator('#' + id).boundingBox();
              const before = await read();
              await page.mouse.move(box.x + 40, box.y + 20);
              await page.mouse.wheel(x ? 120 : 0, x ? 0 : 120);
              await page.waitForTimeout(300);
              const after = await read();
              const pageScroll = await page.evaluate(() => [window.scrollX, window.scrollY]);
              await page.evaluate(([id, x]) => document.getElementById(id).scrollTo(x ? { left: 50 } : { top: 50 }), [id, x]);
              out[id] = { wheel: [before, after], to: await read(), page: pageScroll };
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

    it 'a wheel over a ScrollView bound false moves nothing; bound true scrolls as a declared one does' do
      ensure_tools!
      nodes = [scroll('declOn', true), scroll('declOff', false), scroll('boundOn', '@{on}'), scroll('boundOff', '@{off}')]
      got = wheel(nodes.map { |n| jsx(n) }, { on: true, off: false })
      expect(got['declOn']['wheel'].last).to be > 0, got.inspect
      expect(got['declOff']['wheel']).to eq([0, 0]), got.inspect
      expect(got['boundOn']['wheel']).to eq(got['declOn']['wheel']), got.inspect
      expect(got['boundOff']['wheel']).to eq([0, 0]), got.inspect
    end

    it 'a Collection off, vertical or horizontal, declared or bound: a wheel moves nothing, a scrollTo does, and nothing spills onto the page' do
      ensure_tools!
      cells = { sections: [{ cells: { data: Array.new(8) { |i| { n: i } } } }] }
      vertical = ->(id, on) { collection('scrollEnabled' => on).merge('id' => id, 'width' => 200, 'height' => 100) }
      horizontal = ->(id, on) { vertical.(id, on).merge('horizontalScroll' => true, 'height' => 40) }
      nodes = [vertical.('declOn', true), vertical.('declOff', false), vertical.('boundOff', '@{off}'),
               horizontal.('declOnX', true), horizontal.('declOffX', false), horizontal.('boundOffX', '@{off}')]
      got = wheel(nodes.map { |n| jsx(n) }, { on: true, off: false, items: cells })
      expect(got['declOn']['wheel'].last).to be > 0, got.inspect
      expect(got['declOnX']['wheel'].last).to be > 0, got.inspect
      %w[declOff boundOff declOffX boundOffX].each do |id|
        expect(got[id]).to eq('wheel' => [0, 0], 'to' => 50, 'page' => [0, 0]), "#{id}: #{got.inspect}"
      end
    end
  end
end
