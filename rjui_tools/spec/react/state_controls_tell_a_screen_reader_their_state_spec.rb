# frozen_string_literal: true

require_relative '../spec_helper'
require 'json'
require 'open3'
require 'tmpdir'
require_relative '../support/headless_chromium'
require_relative '../support/configuration_runtime'
require_relative '../support/typescript_compiler'
require 'react/converters/segment_converter'
require 'react/converters/tab_view_converter'
require 'react/converters/switch_converter'

# The web's Segment, TabView and Switch tell a screen reader which item is selected and whether the switch is on
# (ticket rjui-segment-tabview-switch-state-not-exposed), as iOS's Picker / TabView / Toggle and Android's
# Tab(selected=) / NavigationBarItem(selected=) / Switch already do: the selected segment is a pressed button, the
# tabs are a tablist of tabs with one selected, the switch is a switch whose checked is its state.
#
# Drawn for real: the converters' JSX in headless Chromium (Playwright), and the elements found by their role and
# state the way an assistive technology reads them (getByRole with pressed / selected / checked).
module StateControlsTellTheirState
  CONV = RjuiTools::React::Converters
  SUPPORT = File.expand_path('../support', __dir__)
  OPTS = { 'use_tailwind' => true, 'typescript' => false }.freeze

  def self.jsx
    [CONV::SegmentConverter.new({ 'type' => 'Segment', 'id' => 'seg', 'items' => %w[Apple Banana Cherry],
                                  'selectedIndex' => '@{sel}' }, OPTS).convert,
     CONV::TabViewConverter.new({ 'type' => 'TabView', 'id' => 'tabs', 'selectedIndex' => '@{sel}',
                                  'tabs' => [{ 'title' => 'Home', 'view' => 'one' }, { 'title' => 'Search', 'view' => 'two' },
                                             { 'title' => 'Me', 'view' => 'three' }] }, OPTS).convert,
     CONV::SwitchConverter.new({ 'type' => 'Switch', 'id' => 'on', 'isOn' => '@{on}', 'accessibilityLabel' => 'Wifi' }, OPTS).convert,
     CONV::SwitchConverter.new({ 'type' => 'Switch', 'id' => 'off', 'isOn' => '@{off}', 'accessibilityLabel' => 'Bluetooth' }, OPTS).convert]
      .map(&:strip)
  end
end

RSpec.describe 'rjui: a Segment, a TabView and a Switch tell a screen reader their state (in a browser)' do
  def node_modules = File.join(StateControlsTellTheirState::SUPPORT, 'node_modules')

  def tools_ready?
    %w[.bin/esbuild playwright].all? { |p| File.exist?(File.join(node_modules, p)) }
  end

  it 'writes the roles and the states' do
    seg, tabs, on, = StateControlsTellTheirState.jsx
    expect(seg).to include('aria-pressed={data.sel === 1}')
    expect(tabs).to include('<nav role="tablist"')
    expect(tabs).to include('role="tab" aria-selected={(data.sel ?? 0) === 1}')
    expect(on).to include('type="checkbox" role="switch"')
  end

  it 'the emit compiles as TypeScript', :typescript_compile do
    ts = StateControlsTellTheirState::OPTS.merge('typescript' => true)
    conv = StateControlsTellTheirState::CONV
    elements = [
      conv::SegmentConverter.new({ 'type' => 'Segment', 'id' => 'seg', 'items' => %w[Apple Banana Cherry],
                                   'selectedIndex' => '@{sel}' }, ts).convert,
      conv::TabViewConverter.new({ 'type' => 'TabView', 'id' => 'tabs', 'selectedIndex' => '@{sel}',
                                   'tabs' => [{ 'title' => 'Home', 'view' => 'one' }, { 'title' => 'Search', 'view' => 'two' }] }, ts).convert,
      conv::SwitchConverter.new({ 'type' => 'Switch', 'id' => 'on', 'isOn' => '@{on}', 'accessibilityLabel' => 'Wifi' }, ts).convert
    ]
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(<<~TS)
      declare namespace React { type CSSProperties = { [property: string]: string | number | undefined } }
      declare const data: { sel?: number; on: boolean; onOnChange?: (value: boolean) => void; [key: string]: any };
      // React types an <input>'s onChange event; the minimal ambient types no element (as converter_table_spec).
      declare namespace JSX { interface IntrinsicElements { input: { onChange?: (e: { target: { checked: boolean } }) => void; [attr: string]: unknown } } }
      declare const One: any; declare const Two: any; declare const Circle: any;
    TS
  end

  it 'a static selected index and a seeded segment say which button is pressed' do
    conv = StateControlsTellTheirState::CONV::SegmentConverter
    seeded = conv.new({ 'type' => 'Segment', 'id' => 's', 'items' => %w[a b], 'selectedIndex' => 1 }, StateControlsTellTheirState::OPTS).convert
    expect(seeded).to include('aria-pressed={seeded === 0}', 'aria-pressed={seeded === 1}')
  end

  it 'is read by role and state: one pressed segment, one selected tab, a switch on and one off' do
    HeadlessChromium.ensure!(self)
    unless tools_ready?
      reason = 'esbuild / playwright are not installed under spec/support'
      raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

      skip reason
    end

    Dir.mktmpdir('rjui_state_aria') do |dir|
      File.write(File.join(dir, 'app.jsx'), <<~JSX)
        // Every text component's emit reads Configuration.Font.resolve (P1): the template's own.
        #{ConfigurationRuntime.global_js}
        // Every prop the JSX writes lands as the attribute a browser builds from it; `checked` is the property.
        const h = (tag, props, ...kids) => {
          if (typeof tag === 'function') return tag(props || {});
          const el = document.createElement(tag);
          for (const [k, v] of Object.entries(props || {})) {
            if (k === 'className') el.className = v;
            else if (k === 'checked') el.checked = !!v;
            else if (k === 'key' || k.startsWith('on') || k === 'style' || typeof v === 'function') continue;
            else if (v != null && v !== false || k.startsWith('aria-')) el.setAttribute(k, String(v));
          }
          for (const c of kids.flat()) if (c != null && c !== false && c !== true) el.append(c.nodeType ? c : String(c));
          return el;
        };
        const Stub = () => document.createElement('span');
        const One = Stub, Two = Stub, Three = Stub, Circle = Stub;
        const data = { sel: 1, on: true, off: false };
        for (const el of [#{StateControlsTellTheirState.jsx.join(",\n")}]) document.body.append(el);
      JSX
      log, st = Open3.capture2e(File.join(node_modules, '.bin/esbuild'), File.join(dir, 'app.jsx'), '--bundle',
                                '--jsx-factory=h', '--loader:.jsx=tsx', '--outfile=' + File.join(dir, 'app.js'))
      raise "esbuild: #{log}" unless st.success?

      File.write(File.join(dir, 'page.html'), %(<html><body><script src="app.js"></script></body></html>))
      File.write(File.join(dir, 'read.js'), <<~JS)
        const { chromium } = require('playwright');
        (async () => {
          const browser = await chromium.launch({ executablePath: #{HeadlessChromium.path.to_json} });
          const page = await browser.newPage();
          await page.goto('file://#{File.join(dir, 'page.html')}');
          const names = async (loc) => (await loc.allTextContents()).map((t) => t.trim());
          const out = {
            pressed: await names(page.getByRole('button', { pressed: true })),
            notPressed: await names(page.getByRole('button', { pressed: false })),
            tablists: await page.getByRole('tablist').count(),
            selectedTab: await names(page.getByRole('tab', { selected: true })),
            tabs: await page.getByRole('tab').count(),
            switchesOn: await page.getByRole('switch', { checked: true }).evaluateAll((els) => els.map((e) => e.getAttribute('aria-label'))),
            switchesOff: await page.getByRole('switch', { checked: false }).evaluateAll((els) => els.map((e) => e.getAttribute('aria-label'))),
          };
          console.log('AT' + JSON.stringify(out));
          await browser.close();
        })();
      JS
      log, st = Open3.capture2e({ 'NODE_PATH' => node_modules }, 'node', File.join(dir, 'read.js'), chdir: StateControlsTellTheirState::SUPPORT)
      raise "playwright: #{log}" unless st.success?

      got = JSON.parse(log[/AT(\{.*\})/, 1] || raise("no result in:\n#{log}"))
      expect(got['pressed']).to eq(['Banana'])
      expect(got['notPressed']).to eq(%w[Apple Cherry])
      expect(got['tablists']).to eq(1)
      expect(got['tabs']).to eq(3)
      expect(got['selectedTab']).to eq(['Search'])
      expect(got['switchesOn']).to eq(['Wifi'])
      expect(got['switchesOff']).to eq(['Bluetooth'])
    end
  end
end
