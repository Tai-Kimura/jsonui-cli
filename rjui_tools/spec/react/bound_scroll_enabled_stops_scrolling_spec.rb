# frozen_string_literal: true

require_relative '../spec_helper'
require 'json'
require 'open3'
require 'tmpdir'
require_relative '../support/headless_chromium'
require_relative '../support/typescript_compiler'
require 'react/converters/converter_table'

# A bound scrollEnabled false is the declared false (ticket
# rjui-scrollview-bound-scrollenabled-never-stops-scrolling). A declared false
# gives a ScrollView overflow-hidden and a vertical Collection no scroll box;
# bound, nothing came until jsonui-cli 2.3.28, so the box kept its
# overflow-*-auto and a wheel still scrolled it (measured in Chromium).
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

    it 'a Collection: what a declared false leaves — no scroll box, or cells that wrap' do
      expect(jsx(collection({}))).to include("overflowY: data.on === false ? 'visible' : undefined")
      expect(jsx(collection('columns' => 2))).to include("overflowY: data.on === false ? 'visible' : undefined")
      expect(jsx(collection('horizontalScroll' => true))).to include("flexWrap: data.on === false ? 'wrap' : undefined")
      expect(jsx(collection('lazy' => '@{lz}'))).to include(
        "overflowY: data.on === false ? 'visible' : (data.lz === 'none' ? 'visible' : 'auto')"
      )
    end

    it 'control: the declared forms are as they were' do
      expect(jsx(scroll('s', false))).to include('overflow-hidden')
      expect(jsx(scroll('s', false))).not_to include('style=')
      expect(jsx(collection('scrollEnabled' => false))).not_to include('overflow-y-auto')
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

    # {id => [scrollTop before, scrollTop after a wheel over it]}
    def wheel(elements, data, ids)
      Dir.mktmpdir('rjui_bound_scroll') do |dir|
        File.write(File.join(dir, 'content.html'), elements.join("\n"))
        File.write(File.join(dir, 'in.css'), %(@import "#{node_modules}/tailwindcss/index.css" source(none);\n@source "./content.html";\n))
        log, st = Open3.capture2e(File.join(node_modules, '.bin/tailwindcss'), '-i', File.join(dir, 'in.css'), '-o', File.join(dir, 'out.css'))
        raise "tailwindcss: #{log}" unless st.success?

        File.write(File.join(dir, 'app.jsx'), <<~JSX)
          const h = (tag, props, ...kids) => {
            const el = document.createElement(tag);
            for (const [k, v] of Object.entries(props || {})) {
              if (k === 'className') el.className = v;
              else if (k === 'style') { for (const [p, x] of Object.entries(v)) if (x != null) el.style[p] = x; }
              else if (k === 'id') el.id = v;
            }
            for (const c of kids.flat()) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
            return el;
          };
          const React = { Fragment: 'div' };
          const ColorManager = { resolveColor: (c) => c };
          const data = #{data.to_json};
          for (const el of [#{elements.join(",\n")}]) { const box = document.createElement('div'); box.style.margin = '12px'; box.append(el); document.body.append(box); }
        JSX
        log, st = Open3.capture2e(File.join(node_modules, '.bin/esbuild'), File.join(dir, 'app.jsx'), '--bundle', '--jsx-factory=h', '--outfile=' + File.join(dir, 'app.js'))
        raise "esbuild: #{log}" unless st.success?

        File.write(File.join(dir, 'page.html'), %(<html><head><link rel="stylesheet" href="out.css"></head><body><script src="app.js"></script></body></html>))
        File.write(File.join(dir, 'read.js'), <<~JS)
          const { chromium } = require('playwright');
          (async () => {
            const browser = await chromium.launch({ executablePath: #{HeadlessChromium.path.to_json} });
            const page = await browser.newPage({ viewport: { width: 400, height: 1200 } });
            page.on('pageerror', (e) => { console.log('PAGEERROR ' + e.message); process.exit(3); });
            await page.goto('file://#{File.join(dir, 'page.html')}');
            const out = {};
            for (const id of #{ids.to_json}) {
              const box = await page.locator('#' + id).boundingBox();
              const before = await page.evaluate((id) => document.getElementById(id).scrollTop, id);
              await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
              await page.mouse.wheel(0, 120);
              await page.waitForTimeout(300);
              out[id] = [before, await page.evaluate((id) => document.getElementById(id).scrollTop, id)];
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
      HeadlessChromium.ensure!(self)
      unless tools_ready?
        reason = 'esbuild / tailwindcss / playwright are not installed under spec/support'
        raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

        skip reason
      end

      nodes = [scroll('declOn', true), scroll('declOff', false), scroll('boundOn', '@{on}'), scroll('boundOff', '@{off}')]
      got = wheel(nodes.map { |n| jsx(n) }, { on: true, off: false }, %w[declOn declOff boundOn boundOff])
      expect(got['declOn'].last).to be > 0, got.inspect
      expect(got['declOff']).to eq([0, 0]), got.inspect
      expect(got['boundOn']).to eq(got['declOn']), got.inspect
      expect(got['boundOff']).to eq([0, 0]), got.inspect
    end
  end
end
