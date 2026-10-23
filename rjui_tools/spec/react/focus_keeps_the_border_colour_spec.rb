# frozen_string_literal: true

require_relative '../spec_helper'
require 'json'
require 'open3'
require 'tmpdir'
require_relative '../support/headless_chromium'
require 'react/converters/select_box_converter'
require 'react/converters/text_field_converter'

# A focused input keeps its border colour (ticket 2026-10-24-rjui-selectbox-focus-border-hides-bound-border-color).
# A SelectBox's focus sign was `focus:border-blue-500` beside its ring, so a border colour of the layout's — a bound
# error colour a VM sets as it moves focus to the field in error — turned blue while it had focus; a TextField's focus
# is the ring only. The SelectBox's is the ring too now, and its border turns blue on focus only when the layout gives
# it no border colour, as before.
#
# Drawn for real, as bound_colors_keep_state_colors_spec.rb draws: the converters' JSX in headless Chromium
# (Playwright), styled by Tailwind 4.2.1 compiled from that JSX; each element focused and its border colour and ring
# read back with getComputedStyle.
module FocusKeepsTheBorder
  CONV = RjuiTools::React::Converters
  SUPPORT = File.expand_path('../support', __dir__)
  RED = '#ff0000'
  ITEMS = { 'items' => %w[a b], 'selectedItem' => '@{v}' }.freeze
  CASES = {
    # id => [converter, json, the border it must have while focused: a colour, or :blue (blue-500, as before)]
    'boundSelect' => [CONV::SelectBoxConverter, { 'type' => 'SelectBox', 'borderColor' => '@{c}', 'borderWidth' => 1 }.merge(ITEMS), RED],
    'boundDate' => [CONV::SelectBoxConverter, { 'type' => 'SelectBox', 'selectItemType' => 'Date', 'borderColor' => '@{c}', 'borderWidth' => 1 }, RED],
    'fixedSelect' => [CONV::SelectBoxConverter, { 'type' => 'SelectBox', 'borderColor' => RED, 'borderWidth' => 1 }.merge(ITEMS), RED],
    'plainSelect' => [CONV::SelectBoxConverter, { 'type' => 'SelectBox' }.merge(ITEMS), :blue],
    # the control: a TextField's focus never repainted its border
    'boundField' => [CONV::TextFieldConverter, { 'type' => 'TextField', 'text' => '@{t}', 'borderColor' => '@{c}', 'borderWidth' => 1 }, RED]
  }.freeze
end

RSpec.describe 'rjui: a focused input keeps its border colour (in a browser)' do
  def node_modules = File.join(FocusKeepsTheBorder::SUPPORT, 'node_modules')

  def tools_ready?
    %w[.bin/esbuild .bin/tailwindcss playwright].all? { |p| File.exist?(File.join(node_modules, p)) }
  end

  def jsx(id, converter, json)
    converter.new({ 'id' => id }.merge(json), { 'use_tailwind' => true }).convert.strip
  end

  def rgb(hex) = "rgb(#{hex.delete('#').scan(/../).map { |h| h.to_i(16) }.join(', ')})"

  # Every case on one page, with a probe carrying `border-blue-500`; returns {id => {rest:, focus:, ring:}, probe:}.
  def draw(cases)
    Dir.mktmpdir('rjui_focus_border') do |dir|
      elements = cases.map { |id, (conv, json, _)| jsx(id, conv, json) }
      probe = '<div id="probe" className="border border-blue-500">probe</div>'
      File.write(File.join(dir, 'content.html'), (elements + [probe]).join("\n"))
      File.write(File.join(dir, 'in.css'), %(@import "#{node_modules}/tailwindcss/index.css" source(none);\n@source "./content.html";\n))
      log, st = Open3.capture2e(File.join(node_modules, '.bin/tailwindcss'), '-i', File.join(dir, 'in.css'), '-o', File.join(dir, 'out.css'))
      raise "tailwindcss: #{log}" unless st.success?

      File.write(File.join(dir, 'app.jsx'), <<~JSX)
        const h = (tag, props, ...kids) => {
          const el = document.createElement(tag);
          for (const [k, v] of Object.entries(props || {})) {
            if (k === 'className') el.className = v;
            else if (k === 'style') for (const [p, x] of Object.entries(v)) { if (p.startsWith('--')) el.style.setProperty(p, x); else el.style[p] = x; }
            else if (k === 'id' || k === 'type' || k === 'value') el.setAttribute(k, v);
          }
          for (const c of kids.flat()) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
          return el;
        };
        const ColorManager = { resolveColor: (c) => c };
        const data = { c: '#{FocusKeepsTheBorder::RED}', v: 'a', t: '' };
        const boundFieldRef = null;
        for (const el of [#{(elements + [probe]).join(",\n")}]) { const box = document.createElement('div'); box.style.margin = '12px'; box.append(el); document.body.append(box); }
      JSX
      log, st = Open3.capture2e(File.join(node_modules, '.bin/esbuild'), File.join(dir, 'app.jsx'), '--bundle', '--jsx-factory=h', '--outfile=' + File.join(dir, 'app.js'))
      raise "esbuild: #{log}" unless st.success?

      File.write(File.join(dir, 'page.html'), %(<html><head><link rel="stylesheet" href="out.css"></head><body><script src="app.js"></script></body></html>))
      File.write(File.join(dir, 'read.js'), <<~JS)
        const { chromium } = require('playwright');
        (async () => {
          const browser = await chromium.launch({ executablePath: #{HeadlessChromium.path.to_json} });
          const page = await browser.newPage();
          await page.goto('file://#{File.join(dir, 'page.html')}');
          const read = (id) => page.evaluate((i) => { const s = getComputedStyle(document.getElementById(i)); return [s.borderTopColor, s.boxShadow]; }, id);
          const settle = () => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
          const out = { probe: (await read('probe'))[0] };
          for (const id of #{cases.keys.to_json}) {
            const [rest] = await read(id);
            await page.focus('#' + id);
            await settle();
            await page.waitForTimeout(250);
            const [focus, ring] = await read(id);
            const focused = await page.evaluate(() => document.activeElement && document.activeElement.id);
            out[id] = { rest, focus, ring, focused };
            await page.evaluate(() => document.activeElement && document.activeElement.blur());
          }
          console.log('AT' + JSON.stringify(out));
          await browser.close();
        })();
      JS
      log, st = Open3.capture2e({ 'NODE_PATH' => node_modules }, 'node', File.join(dir, 'read.js'), chdir: FocusKeepsTheBorder::SUPPORT)
      raise "playwright: #{log}" unless st.success?

      JSON.parse(log[/AT(\{.*\})/, 1] || raise("no result in:\n#{log}"))
    end
  end

  it 'keeps a fixed or bound border colour while focused, and turns a SelectBox without one blue, as before' do
    HeadlessChromium.ensure!(self)
    unless tools_ready?
      reason = 'esbuild / tailwindcss / playwright are not installed under spec/support'
      raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

      skip reason
    end

    got = draw(FocusKeepsTheBorder::CASES)
    blue = got['probe']
    expect(blue).not_to eq(rgb(FocusKeepsTheBorder::RED))
    FocusKeepsTheBorder::CASES.each do |id, (_, _, want)|
      read = got[id]
      expect(read['focused']).to eq(id), "#{id} took focus: #{read.inspect}"
      expect(read['focus']).to eq(want == :blue ? blue : rgb(want)), "#{id} focused: #{read.inspect} (blue-500 is #{blue})"
      # Tailwind 4 always lists transparent shadows: the ring is the one in blue-500
      expect(read['ring']).to include(blue), "#{id} shows its blue focus ring: #{read.inspect}"
    end
  end

  it 'writes the SelectBox focus as a ring, and a blue border only when the layout gives no border colour' do
    FocusKeepsTheBorder::CASES.each do |id, (conv, json, want)|
      out = jsx(id, conv, json)
      expect(out).to include('focus:ring-2 focus:ring-blue-500')
      expect(out.include?('focus:border-blue-500')).to eq(want == :blue), "#{id}: #{out[/className=[^>]*/]}"
    end
  end
end
