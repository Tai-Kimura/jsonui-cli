# frozen_string_literal: true

require_relative '../spec_helper'
require 'json'
require 'open3'
require 'tmpdir'
require_relative '../support/headless_chromium'
require_relative '../support/typescript_compiler'
require 'react/converters/button_converter'
require 'react/converters/view_converter'

# A bound colour never hides a state colour (ticket
# rjui-bound-background-overrides-tap-background). A bound `background` was an
# inline `backgroundColor`, and an inline style beats every class: a Button's
# tapBackground (`hover:` / `active:`), its disabledBackground (`disabled:`) and
# a tappable View's tapBackground never showed over it; a bound `fontColor` hid
# highlightColor and disabledFontColor the same way. iOS (StateAwareButtonView,
# PressedBackground) and Android (the button's interaction source, the modifier's
# pressed background) draw the state colour over a bound base exactly as over a
# fixed one, so the web does too: the bound value rides a custom property read by
# a class (`bg-[var(--jui-bg)]`, `text-[var(--jui-color)]`), and the state classes
# beat it.
#
# Drawn for real: the converters' JSX rendered in headless Chromium (Playwright),
# styled by Tailwind 4.2.1 itself (the version the web consumers build with,
# pinned in spec/support) compiled from that JSX; the colours read back with
# getComputedStyle at rest, under the pointer, pressed and disabled.
module BoundColoursKeepStates
  CONV = RjuiTools::React::Converters
  SUPPORT = File.expand_path('../support', __dir__)
  BASE = '#0000ff'
  FG = '#123456'
  CASES = {
    # [converter, json, the reads]: each read is [state, CSS property, the colour it must be]
    'tap' => [CONV::ButtonConverter, { 'type' => 'Button', 'text' => 'Go', 'background' => '@{bg}', 'tapBackground' => '#00ff00', 'onClick' => '@{go}' },
              [['rest', 'backgroundColor', BASE], ['hover', 'backgroundColor', '#00ff00'], ['press', 'backgroundColor', '#00ff00']]],
    'disabled' => [CONV::ButtonConverter, { 'type' => 'Button', 'text' => 'Go', 'background' => '@{bg}', 'disabledBackground' => '#999999', 'enabled' => '@{off}', 'onClick' => '@{go}' },
                   [['rest', 'backgroundColor', '#999999']]],
    'highlight' => [CONV::ButtonConverter, { 'type' => 'Button', 'text' => 'Go', 'fontColor' => '@{fg}', 'highlightColor' => '#ff00ff', 'onClick' => '@{go}' },
                    [['rest', 'color', FG], ['hover', 'color', '#ff00ff']]],
    'disabledText' => [CONV::ButtonConverter, { 'type' => 'Button', 'text' => 'Go', 'fontColor' => '@{fg}', 'disabledFontColor' => '#555555', 'enabled' => '@{off}', 'onClick' => '@{go}' },
                       [['rest', 'color', '#555555']]],
    'viewTap' => [CONV::ViewConverter, { 'type' => 'View', 'width' => 60, 'height' => 40, 'background' => '@{bg}', 'tapBackground' => '#00ff00', 'onClick' => '@{go}' },
                  [['rest', 'backgroundColor', BASE], ['press', 'backgroundColor', '#00ff00']]],
    # the control: a fixed background with the same state, which always worked
    'fixed' => [CONV::ButtonConverter, { 'type' => 'Button', 'text' => 'Go', 'background' => '#0000ff', 'tapBackground' => '#00ff00', 'onClick' => '@{go}' },
                [['rest', 'backgroundColor', BASE], ['hover', 'backgroundColor', '#00ff00'], ['press', 'backgroundColor', '#00ff00']]],
  }.freeze

end

RSpec.describe 'rjui bound colours keep their state colours (in a browser)' do
  include BoundColoursKeepStates

  def node_modules = File.join(BoundColoursKeepStates::SUPPORT, 'node_modules')

  def tools_ready?
    %w[.bin/esbuild .bin/tailwindcss playwright].all? { |p| File.exist?(File.join(node_modules, p)) }
  end

  def jsx(id, converter, json, typescript: false)
    converter.new({ 'id' => id }.merge(json), { 'use_tailwind' => true, 'typescript' => typescript }).convert.strip
  end

  def rgb(hex) = "rgb(#{hex.delete('#').scan(/../).map { |h| h.to_i(16) }.join(', ')})"

  # Every case drawn on one page; returns {case => {state => {prop => colour}}}.
  def draw(cases)
    Dir.mktmpdir('rjui_state_colours') do |dir|
      elements = cases.map { |id, (conv, json, _)| jsx(id, conv, json) }
      File.write(File.join(dir, 'content.html'), elements.join("\n"))
      File.write(File.join(dir, 'in.css'), %(@import "#{node_modules}/tailwindcss/index.css" source(none);\n@source "./content.html";\n))
      log, st = Open3.capture2e(File.join(node_modules, '.bin/tailwindcss'), '-i', File.join(dir, 'in.css'), '-o', File.join(dir, 'out.css'))
      raise "tailwindcss: #{log}" unless st.success?

      File.write(File.join(dir, 'app.jsx'), <<~JSX)
        const h = (tag, props, ...kids) => {
          const el = document.createElement(tag);
          for (const [k, v] of Object.entries(props || {})) {
            if (k === 'className') el.className = v;
            else if (k === 'style') for (const [p, x] of Object.entries(v)) { if (p.startsWith('--')) el.style.setProperty(p, x); else el.style[p] = x; }
            else if (k === 'disabled') el.disabled = !!v;
            else if (k === 'id') el.id = v;
          }
          for (const c of kids.flat()) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
          return el;
        };
        const ColorManager = { resolveColor: (c) => c };
        const data = { bg: '#{BoundColoursKeepStates::BASE}', fg: '#{BoundColoursKeepStates::FG}', off: false, go: () => {} };
        for (const el of [#{elements.join(",\n")}]) { const box = document.createElement('div'); box.style.margin = '12px'; box.append(el); document.body.append(box); }
      JSX
      log, st = Open3.capture2e(File.join(node_modules, '.bin/esbuild'), File.join(dir, 'app.jsx'), '--bundle', '--jsx-factory=h', '--outfile=' + File.join(dir, 'app.js'))
      raise "esbuild: #{log}" unless st.success?

      File.write(File.join(dir, 'page.html'), %(<html><head><link rel="stylesheet" href="out.css"></head><body><script src="app.js"></script></body></html>))
      reads = cases.transform_values { |(_, _, r)| r }
      File.write(File.join(dir, 'read.js'), <<~JS)
        const { chromium } = require('playwright');
        (async () => {
          const browser = await chromium.launch({ executablePath: #{HeadlessChromium.path.to_json} });
          const page = await browser.newPage({ hasTouch: false });
          await page.goto('file://#{File.join(dir, 'page.html')}');
          const reads = #{reads.to_json}, out = {};
          const style = (id, prop) => page.evaluate(([i, p]) => getComputedStyle(document.getElementById(i))[p], [id, prop]);
          for (const [id, list] of Object.entries(reads)) {
            out[id] = {};
            const box = await page.locator('#' + id).boundingBox();
            await page.mouse.move(0, 0);
            for (const [state, prop] of list) {
              if (state === 'hover') await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
              if (state === 'press') { await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2); await page.mouse.down(); }
              await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
              // transition-colors: read once the transition is over
              await page.waitForTimeout(250);
              (out[id][state] = out[id][state] || {})[prop] = await style(id, prop);
              if (state === 'press') await page.mouse.up();
              await page.mouse.move(0, 0);
            }
          }
          console.log('AT' + JSON.stringify(out));
          await browser.close();
        })();
      JS
      log, st = Open3.capture2e({ 'NODE_PATH' => node_modules }, 'node', File.join(dir, 'read.js'), chdir: BoundColoursKeepStates::SUPPORT)
      raise "playwright: #{log}" unless st.success?

      JSON.parse(log[/AT(\{.*\})/, 1] || raise("no result in:\n#{log}"))
    end
  end

  it 'draws each state colour over a bound base, as over a fixed one' do
    HeadlessChromium.ensure!(self)
    unless tools_ready?
      reason = 'esbuild / tailwindcss / playwright are not installed under spec/support'
      raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

      skip reason
    end

    got = draw(BoundColoursKeepStates::CASES)
    BoundColoursKeepStates::CASES.each do |id, (_, json, reads)|
      reads.each do |state, prop, want|
        expect(got.dig(id, state, prop)).to eq(rgb(want)), "#{id} #{json.slice('background', 'fontColor').inspect} #{state} #{prop}: #{got[id].inspect}"
      end
    end
  end

  it 'gives a bound colour no inline backgroundColor / color (the shape that hid the states)' do
    BoundColoursKeepStates::CASES.except('fixed').each do |id, (conv, json, _)|
      out = jsx(id, conv, json)
      expect(out).not_to match(/backgroundColor:|[{ ,]color:/), "#{id}: #{out}"
      expect(out).to include('bg-[var(--jui-bg)]') if json['background']
      expect(out).to include('text-[var(--jui-color)]') if json['fontColor']
    end
  end

  it 'the emit compiles as TypeScript (the custom properties ride the CSSProperties cast)', :typescript_compile do
    elements = BoundColoursKeepStates::CASES.map { |id, (conv, json, _)| jsx(id, conv, json, typescript: true) }
    ambient = TypeScriptCompiler::AMBIENT + <<~TS
      declare const data: Record<string, any>;
      declare const ColorManager: { resolveColor(c: unknown): string };
      declare namespace React { type CSSProperties = { [property: string]: string | number | undefined } }
    TS
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(ambient)
  end
end
