# frozen_string_literal: true

require_relative '../spec_helper'
require 'json'
require 'open3'
require 'stringio'
require 'tmpdir'
require_relative '../support/headless_chromium'
require_relative '../support/typescript_compiler'
require 'react/converters/converter_table'
require 'react/tailwind_mapper'

# A bound colour is never read as a colour name (ticket
# rjui-selectbox-bound-border-color). A converter that handed its own colour
# attribute to TailwindMapper.map_color without asking whether it was bound
# wrote `border-@{x}` as a class, and `jui build` warned "Color '@{x}' is not
# defined": SelectBox borderColor, Indicator color / tintColor. Others wrote
# the `@{…}` text into an inline style (CircleView's border, Blur's
# background) or wrote the binding inline over the base's custom property
# (CircleView's background). A text input's bound border went inline as
# borderColor, which beat the control's own state border (SelectBox's
# focus:border-*), the shape bound_colors_keep_state_colors_spec fixed for
# background and fontColor; TextView then wrote it inline once more.
#
# The family, measured: every converter, every colour attribute its
# declaration lets be bound, with `@{x}`. Each must neither warn nor leak the
# `@{…}` text, and the seven that did now ride a custom property read by a
# class — drawn for real in headless Chromium with Tailwind 4.2.1's CSS.
module BoundColourFamily
  CONV = RjuiTools::React::Converters
  SUPPORT = File.expand_path('../support', __dir__)
  DEFS = JSON.parse(File.read(File.expand_path('../../lib/core/attribute_definitions.json', __dir__)))
  # what a node needs for the attribute to be drawn at all
  BASE = { 'Label' => { 'text' => 't' }, 'Button' => { 'text' => 't', 'onClick' => '@{go}' },
           'TextField' => { 'text' => '@{s}' }, 'TextView' => { 'text' => '@{s}' },
           'SelectBox' => { 'items' => %w[a b] }, 'Segment' => { 'items' => %w[a b] },
           'TabView' => { 'tabs' => [{ 'title' => 'a' }] }, 'IconLabel' => { 'text' => 't' },
           'Switch' => { 'isOn' => '@{on}' }, 'CheckBox' => { 'isOn' => '@{on}' },
           'Slider' => { 'value' => '@{v}' }, 'Radio' => { 'items' => ['a'] }, 'Progress' => { 'progress' => 0.5 } }.freeze

  def self.colour?(name) = name.match?(/(?:[cC]olor|[bB]ackground|[tT]int)$/)
  def self.bindable?(spec) = spec.is_a?(Hash) && Array(spec['type']).include?('binding')

  # [type, attribute] for every bindable colour attribute of every converter
  def self.pairs
    CONV::ConverterTable.table.keys.reject { |t| %w[Include Embed].include?(t) }.flat_map do |type|
      section = DEFS[type] || {}
      (section.keys + DEFS['common'].keys).uniq
                                          .select { |k| colour?(k) && bindable?(section[k] || DEFS['common'][k]) }
                                          .map { |k| [type, k] }
    end
  end

  def self.node(type, attribute, value = '@{x}')
    node = { 'type' => type, 'id' => 'n', 'width' => 100, 'height' => 40 }.merge(BASE[type] || {}).merge(attribute => value)
    node['enabled'] = '@{on}' if attribute.start_with?('disabled')
    node['borderWidth'] = 1 if attribute.start_with?('border')
    node['onClick'] ||= '@{go}' if attribute.start_with?('tap')
    node['highlighted'] = '@{h}' if attribute.start_with?('highlight')
    node
  end
end

RSpec.describe 'rjui bound colours reach a custom property, never a colour name (in a browser)' do
  def jsx(node, typescript: false)
    BoundColourFamily::CONV::ConverterTable.table.fetch(node['type'])
                                           .new(node, { 'use_tailwind' => true, 'typescript' => typescript }).convert.strip
  end

  # The emit and what it logged, with the palette configured as `jui build`
  # configures it (so an unknown name warns), restored afterwards.
  def emit_logged(node)
    mapper = RjuiTools::React::TailwindMapper
    saved = %i[@theme_safe_colors @color_fallbacks @warned_colors].to_h { |v| [v, mapper.instance_variable_get(v)] }
    mapper.configure_palette(theme_safe: ['primary'], fallbacks: {})
    mapper.instance_variable_set(:@warned_colors, {})
    out = StringIO.new
    old = $stdout
    $stdout = out
    [jsx(node), out.string]
  ensure
    $stdout = old
    saved&.each { |v, value| mapper.instance_variable_set(v, value) }
  end

  it 'no converter warns about, or writes, the `@{…}` text of a bound colour' do
    pairs = BoundColourFamily.pairs
    expect(pairs.size).to be >= 180 # the table is the family, not a sample
    expect(pairs).to include(%w[SelectBox borderColor], %w[Indicator color], %w[CircleView borderColor], %w[Blur background])
    bad = pairs.filter_map do |type, attribute|
      code, log = emit_logged(BoundColourFamily.node(type, attribute))
      "#{type}.#{attribute}: #{log.include?("Color '@{x}'") ? 'warns' : 'writes @{x}'}" if log.include?("Color '@{x}'") || code.include?('@{x')
    end
    expect(bad).to be_empty, bad.join("\n")
  end

  it 'the seven that did ride a custom property read by a class' do
    {
      ['SelectBox', 'borderColor'] => ["'--jui-border-color': ColorManager.resolveColor(data.x)", 'border-[color:var(--jui-border-color)]'],
      ['TextField', 'borderColor'] => ["'--jui-border-color': ColorManager.resolveColor(data.x)", 'border-[color:var(--jui-border-color)]'],
      ['TextView', 'borderColor'] => ["'--jui-border-color': ColorManager.resolveColor(data.x)", 'border-[color:var(--jui-border-color)]'],
      ['Indicator', 'color'] => ["'--jui-indicator-color': ColorManager.resolveColor(data.x)", 'border-t-[color:var(--jui-indicator-color)]'],
      ['Indicator', 'tintColor'] => ["'--jui-indicator-color': ColorManager.resolveColor(data.x)", 'border-t-[color:var(--jui-indicator-color)]'],
      ['CircleView', 'borderColor'] => ["'--jui-border-color': ColorManager.resolveColor(data.x)", 'after:border-[color:var(--jui-border-color)]'],
      ['CircleView', 'background'] => ["'--jui-bg': ColorManager.resolveColor(data.x)", 'bg-[var(--jui-bg)]'],
      ['Blur', 'background'] => ["'--jui-bg': ColorManager.resolveColor(data.x)", 'bg-[var(--jui-bg)]']
    }.each do |(type, attribute), wants|
      code = jsx(BoundColourFamily.node(type, attribute))
      expect(code).to include(*wants), "#{type}.#{attribute}: #{code}"
      expect(code).not_to match(/(?:borderColor|backgroundColor|border): (?:data\.x|'[^']*@\{|ColorManager\.resolveColor\(data\.x\))/),
                          "#{type}.#{attribute}: #{code}"
    end
    # TextView wrote its border inline after the base: a bound width came out as `'@{w}px'`
    code = jsx(BoundColourFamily.node('TextView', 'borderColor').merge('borderWidth' => '@{w}'))
    expect(code).to include('borderWidth: `${data.w}px`')
    expect(code).not_to include('@{w')
  end

  def node_modules = File.join(BoundColourFamily::SUPPORT, 'node_modules')

  def tools_ready?
    %w[.bin/esbuild .bin/tailwindcss playwright].all? { |p| File.exist?(File.join(node_modules, p)) }
  end

  def rgb(hex) = "rgb(#{hex.delete('#').scan(/../).map { |h| h.to_i(16) }.join(', ')})"

  # {id => {read => value}}; each read is [selector-in-the-element, CSS property, focus first?]
  def draw(elements, reads)
    Dir.mktmpdir('rjui_bound_colours') do |dir|
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
            else if (k === 'id') el.id = v;
            else if (k === 'value') el.value = v;
          }
          for (const c of kids.flat()) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
          return el;
        };
        const React = { Fragment: 'div' };
        const ColorManager = { resolveColor: (c) => c };
        const data = { x: '#ff0000', s: '', w: 2, on: true, go: () => {} };
        const tfRef = null, tvRef = null;
        for (const el of [#{elements.join(",\n")}]) { const box = document.createElement('div'); box.style.margin = '12px'; box.append(el); document.body.append(box); }
      JSX
      log, st = Open3.capture2e(File.join(node_modules, '.bin/esbuild'), File.join(dir, 'app.jsx'), '--bundle', '--jsx-factory=h', '--outfile=' + File.join(dir, 'app.js'))
      raise "esbuild: #{log}" unless st.success?

      File.write(File.join(dir, 'page.html'), %(<html><head><link rel="stylesheet" href="out.css"></head><body><script src="app.js"></script></body></html>))
      File.write(File.join(dir, 'read.js'), <<~JS)
        const { chromium } = require('playwright');
        (async () => {
          const browser = await chromium.launch({ executablePath: #{HeadlessChromium.path.to_json} });
          const page = await browser.newPage();
          page.on('pageerror', (e) => { console.log('PAGEERROR ' + e.message); process.exit(3); });
          await page.goto('file://#{File.join(dir, 'page.html')}');
          const reads = #{reads.to_json}, out = {};
          for (const [name, [id, inner, pseudo, prop, focus]] of Object.entries(reads)) {
            if (focus) await page.focus('#' + id);
            await page.waitForTimeout(250); // transition-colors
            out[name] = await page.evaluate(([id, inner, pseudo, prop]) => {
              const el = inner ? document.getElementById(id).querySelector(inner) : document.getElementById(id);
              return getComputedStyle(el, pseudo || null)[prop];
            }, [id, inner, pseudo, prop]);
            if (focus) await page.evaluate(() => document.activeElement.blur());
          }
          console.log('AT' + JSON.stringify(out));
          await browser.close();
        })();
      JS
      log, st = Open3.capture2e({ 'NODE_PATH' => node_modules }, 'node', File.join(dir, 'read.js'), chdir: BoundColourFamily::SUPPORT)
      raise "playwright: #{log}" unless st.success?

      JSON.parse(log[/AT(\{.*\})/, 1] || raise("no result in:\n#{log}"))
    end
  end

  it 'draws the bound colour, and a control state colour still shows over it' do
    HeadlessChromium.ensure!(self)
    unless tools_ready?
      reason = 'esbuild / tailwindcss / playwright are not installed under spec/support'
      raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

      skip reason
    end

    node = ->(id, type, attribute, value = '@{x}') { BoundColourFamily.node(type, attribute, value).merge('id' => id) }
    elements = [
      node.('sb', 'SelectBox', 'borderColor'), node.('sbFixed', 'SelectBox', 'borderColor', '#ff0000'),
      node.('tf', 'TextField', 'borderColor'), node.('tv', 'TextView', 'borderColor'),
      node.('ind', 'Indicator', 'color'), node.('cv', 'CircleView', 'background'),
      node.('cvb', 'CircleView', 'borderColor'), node.('blur', 'Blur', 'background')
    ].map { |n| jsx(n) }
    got = draw(elements, {
                 'sb' => ['sb', nil, nil, 'borderTopColor', false], 'sbFocus' => ['sb', nil, nil, 'borderTopColor', true],
                 'sbFixedFocus' => ['sbFixed', nil, nil, 'borderTopColor', true],
                 'tf' => ['tf', nil, nil, 'borderTopColor', false],
                 'tv' => ['tv', nil, nil, 'borderTopColor', false],
                 'ind' => ['ind', 'div', nil, 'borderTopColor', false],
                 'cv' => ['cv', nil, nil, 'backgroundColor', false],
                 'cvb' => ['cvb', nil, '::after', 'borderTopColor', false],
                 'blur' => ['blur', nil, nil, 'backgroundColor', false]
               })
    red = rgb('#ff0000')
    expect(got.slice('sb', 'tf', 'tv', 'ind', 'cv', 'cvb', 'blur')).to eq(%w[sb tf tv ind cv cvb blur].to_h { |k| [k, red] }), got.inspect
    # focus:border-blue-500 shows over the bound border as over the fixed one
    expect(got['sbFocus']).not_to eq(red), got.inspect
    expect(got['sbFocus']).to eq(got['sbFixedFocus']), got.inspect
  end

  it 'the emit compiles as TypeScript', :typescript_compile do
    # (TextField's onChange takes its event untyped against this ambient; its
    # border is the same css_border_classes as SelectBox's)
    elements = [%w[SelectBox borderColor], %w[Indicator color], %w[CircleView borderColor],
                %w[CircleView background], %w[Blur background]].map { |t, a| jsx(BoundColourFamily.node(t, a), typescript: true) }
    ambient = TypeScriptCompiler::AMBIENT + <<~TS
      declare const data: Record<string, any>;
      declare const ColorManager: { resolveColor(c: unknown): string };
      declare namespace React { type CSSProperties = { [property: string]: string | number | undefined } }
    TS
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(ambient)
  end
end
