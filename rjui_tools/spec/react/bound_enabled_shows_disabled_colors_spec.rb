# frozen_string_literal: true

require_relative '../spec_helper'
require 'json'
require 'open3'
require 'tmpdir'
require_relative '../support/headless_chromium'
require_relative '../support/typescript_compiler'
require 'react/converters/view_converter'
require 'react/converters/label_converter'
require 'react/converters/button_converter'

# The disabled colours follow `enabled` whether it is written or bound (ticket
# 2026-10-23-bound-enabled-disabled-colors-three-faces). A View's
# disabledBackground was not drawn at all on the web, and a Label's
# disabledFontColor only for a literal `enabled: false`: a bound `enabled` that
# turned false left the label in its base colour. iOS and Android now draw both
# for a bound `enabled` too; the web carries the state on aria-disabled, read by
# `aria-disabled:` classes that beat the base colour, fixed or bound.
#
# Drawn for real, as bound_colors_keep_state_colors_spec.rb draws: the converters'
# JSX, Tailwind 4.2.1's own CSS, headless Chromium; each case rendered with
# `enabled` true and with it false, the colours read with getComputedStyle.
module BoundEnabledDisabledColours
  CONV = RjuiTools::React::Converters
  SUPPORT = File.expand_path('../support', __dir__)
  BG = '#0000ff'
  FG = '#123456'
  CASES = {
    # [converter, json, CSS property, the colour while enabled, the colour while disabled]
    'viewBound' => [CONV::ViewConverter, { 'type' => 'View', 'width' => 60, 'height' => 40, 'background' => '@{bg}', 'disabledBackground' => '#999999', 'enabled' => '@{on}' },
                    'backgroundColor', BG, '#999999'],
    'viewFixed' => [CONV::ViewConverter, { 'type' => 'View', 'width' => 60, 'height' => 40, 'background' => '#0000ff', 'disabledBackground' => '#999999', 'enabled' => '@{on}' },
                    'backgroundColor', BG, '#999999'],
    'labelBound' => [CONV::LabelConverter, { 'type' => 'Label', 'text' => 'x', 'fontColor' => '@{fg}', 'disabledFontColor' => '#555555', 'enabled' => '@{on}' },
                     'color', FG, '#555555'],
    'labelFixed' => [CONV::LabelConverter, { 'type' => 'Label', 'text' => 'x', 'fontColor' => '#123456', 'disabledFontColor' => '#555555', 'enabled' => '@{on}' },
                     'color', FG, '#555555'],
    'buttonBound' => [CONV::ButtonConverter, { 'type' => 'Button', 'text' => 'Go', 'background' => '@{bg}', 'disabledBackground' => '#999999', 'enabled' => '@{on}', 'onClick' => '@{go}' },
                      'backgroundColor', BG, '#999999'],
  }.freeze
end

RSpec.describe 'rjui disabled colours follow a bound enabled (in a browser)' do
  def node_modules = File.join(BoundEnabledDisabledColours::SUPPORT, 'node_modules')

  def tools_ready?
    %w[.bin/esbuild .bin/tailwindcss playwright].all? { |p| File.exist?(File.join(node_modules, p)) }
  end

  def jsx(id, converter, json, typescript: false)
    converter.new({ 'id' => id }.merge(json), { 'use_tailwind' => true, 'typescript' => typescript }).convert.strip
  end

  def rgb(hex) = "rgb(#{hex.delete('#').scan(/../).map { |h| h.to_i(16) }.join(', ')})"

  # {case => {'on' => colour, 'off' => colour}}
  def draw(cases)
    Dir.mktmpdir('rjui_disabled_colours') do |dir|
      parts = cases.flat_map do |id, (conv, json, _)|
        %w[on off].map { |state| ["#{id}_#{state}", state == 'on', jsx("#{id}_#{state}", conv, json)] }
      end
      File.write(File.join(dir, 'content.html'), parts.map(&:last).join("\n"))
      File.write(File.join(dir, 'in.css'), %(@import "#{node_modules}/tailwindcss/index.css" source(none);\n@source "./content.html";\n))
      log, st = Open3.capture2e(File.join(node_modules, '.bin/tailwindcss'), '-i', File.join(dir, 'in.css'), '-o', File.join(dir, 'out.css'))
      raise "tailwindcss: #{log}" unless st.success?

      renders = parts.map do |_, on, element|
        "(() => { const data = { bg: '#{BoundEnabledDisabledColours::BG}', fg: '#{BoundEnabledDisabledColours::FG}', on: #{on}, go: () => {} }; return (#{element}); })()"
      end
      File.write(File.join(dir, 'app.jsx'), <<~JSX)
        const h = (tag, props, ...kids) => {
          const el = document.createElement(tag);
          for (const [k, v] of Object.entries(props || {})) {
            if (k === 'className') el.className = v;
            else if (k === 'style') for (const [p, x] of Object.entries(v)) { if (p.startsWith('--')) el.style.setProperty(p, x); else el.style[p] = x; }
            else if (k === 'disabled') el.disabled = !!v;
            else if (k === 'id') el.id = v;
            else if (k.startsWith('aria-')) el.setAttribute(k, String(v));
          }
          for (const c of kids.flat()) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
          return el;
        };
        const ColorManager = { resolveColor: (c) => c };
        for (const el of [#{renders.join(",\n")}]) { const box = document.createElement('div'); box.style.margin = '8px'; box.append(el); document.body.append(box); }
      JSX
      log, st = Open3.capture2e(File.join(node_modules, '.bin/esbuild'), File.join(dir, 'app.jsx'), '--bundle', '--jsx-factory=h', '--outfile=' + File.join(dir, 'app.js'))
      raise "esbuild: #{log}" unless st.success?

      File.write(File.join(dir, 'page.html'), %(<html><head><link rel="stylesheet" href="out.css"></head><body><script src="app.js"></script></body></html>))
      reads = cases.to_h { |id, (_, _, prop)| [id, prop] }
      File.write(File.join(dir, 'read.js'), <<~JS)
        const { chromium } = require('playwright');
        (async () => {
          const browser = await chromium.launch({ executablePath: #{HeadlessChromium.path.to_json} });
          const page = await browser.newPage();
          await page.goto('file://#{File.join(dir, 'page.html')}');
          await page.waitForTimeout(300);
          const out = await page.evaluate((reads) => Object.fromEntries(Object.entries(reads).map(([id, prop]) =>
            [id, { on: getComputedStyle(document.getElementById(id + '_on'))[prop], off: getComputedStyle(document.getElementById(id + '_off'))[prop] }])), #{reads.to_json});
          console.log('AT' + JSON.stringify(out));
          await browser.close();
        })();
      JS
      log, st = Open3.capture2e({ 'NODE_PATH' => node_modules }, 'node', File.join(dir, 'read.js'), chdir: BoundEnabledDisabledColours::SUPPORT)
      raise "playwright: #{log}" unless st.success?

      JSON.parse(log[/AT(\{.*\})/, 1] || raise("no result in:\n#{log}"))
    end
  end

  it 'draws the base colour while enabled and the disabled colour once a bound enabled is false' do
    HeadlessChromium.ensure!(self)
    unless tools_ready?
      reason = 'esbuild / tailwindcss / playwright are not installed under spec/support'
      raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

      skip reason
    end

    got = draw(BoundEnabledDisabledColours::CASES)
    BoundEnabledDisabledColours::CASES.each do |id, (_, _, prop, on, off)|
      expect(got[id]).to eq({ 'on' => rgb(on), 'off' => rgb(off) }), "#{id} #{prop}: #{got[id].inspect}"
    end
  end

  it 'gives the state to aria-disabled, the colour to an aria-disabled: class (no inline colour for it)' do
    out = jsx('l', BoundEnabledDisabledColours::CONV::LabelConverter, { 'type' => 'Label', 'text' => 'x', 'disabledFontColor' => '#555555', 'enabled' => false })
    expect(out).to include('aria-disabled="true"', 'aria-disabled:text-[#555555]')
    expect(out).not_to include("color: ColorManager.resolveColor('#555555')")
    plain = jsx('p', BoundEnabledDisabledColours::CONV::LabelConverter, { 'type' => 'Label', 'text' => 'x', 'disabledFontColor' => '#555555' })
    expect(plain).not_to include('aria-disabled')
  end

  it 'the emit compiles as TypeScript', :typescript_compile do
    elements = BoundEnabledDisabledColours::CASES.map { |id, (conv, json, _)| jsx(id, conv, json, typescript: true) }
    ambient = TypeScriptCompiler::AMBIENT + <<~TS
      declare const data: Record<string, any>;
      declare const ColorManager: { resolveColor(c: unknown): string };
      declare namespace React { type CSSProperties = { [property: string]: string | number | undefined } }
    TS
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(ambient)
  end
end
