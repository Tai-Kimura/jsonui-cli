# frozen_string_literal: true

require 'json'
require 'open3'
require 'tmpdir'
require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require 'react/react_generator'

# A control's declared onClick is called ONCE, from the control's own
# operation, after the control's own update — one rule for the five paths
# (ticket control-onclick-is-called-differently-on-every-path): Switch /
# Toggle / CheckBox after the value, Radio after the selection, Segment after
# the tab, Slider when the change is finished, SelectBox after the selection.
# canTap gates the call; `enabled: false` stops the operation, so the call.
# Until 1.9.0 rjui called it from none of them (the handler's name did not
# appear in the emitted code).
#
# Each emitted element is evaluated by node through esbuild's JSX transform
# with a factory that keeps the tree, then OPERATED the way a browser
# dispatches that operation: the checkbox's / radio's / select's change, the
# tab button's click, the range's native `change` (its ref sets
# `el.onchange`). A disabled element is not operated — a browser dispatches
# no operation on one. Every call into `data` is recorded in order.
RSpec.describe 'a control calls its declared onClick from its own operation' do
  CONTROL_CONFIG = { 'use_tailwind' => true, 'typescript' => true }.freeze
  CONTROL_ESBUILD = File.expand_path('../../support/node_modules/esbuild', __dir__)

  # [type, own attributes, how it is operated]
  controls = [
    ['Switch', { 'isOn' => '@{on}' }, 'checkbox'],
    ['Toggle', { 'isOn' => '@{on}' }, 'checkbox'],
    ['CheckBox', { 'isOn' => '@{on}', 'label' => 'L' }, 'checkbox'],
    ['Radio', { 'group' => 'g', 'text' => 'R', 'selectedValue' => '@{sel}', 'value' => 'a' }, 'radio'],
    ['Segment', { 'items' => %w[a b], 'selectedIndex' => '@{idx}' }, 'tab'],
    ['Segment', { 'items' => %w[a b] }, 'tab'], # a static index: the segment's own seeded state
    ['Slider', { 'value' => '@{v}' }, 'range'],
    ['SelectBox', { 'items' => %w[a b], 'selectedIndex' => '@{idx}' }, 'select'],
    ['SelectBox', { 'selectItemType' => 'Date', 'selectedDate' => '@{d}' }, 'date']
  ]

  # Through a View's child dispatch, as a layout draws it: that resolves a
  # declared alias section (Toggle is `_alias_of` Switch) before it looks the
  # converter up, and the lookup holds canonical sections only.
  emit = lambda do |type, attrs|
    node = { 'type' => type, 'id' => 'c' }.merge(attrs)
    view = RjuiTools::React::Converters::ViewConverter.new({ 'type' => 'View' }, CONTROL_CONFIG.dup)
    view.send(:create_converter_for_child, node).convert
  end

  node_program = <<~JS
    const fs = require('fs');
    const esbuild = require(process.argv[2]);
    const jobs = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
    // A function component (the file's JsonUISeeded) is rendered in place.
    const h = (type, props, ...children) => (typeof type === 'function'
      ? type({ ...(props || {}), children: children.length === 1 ? children[0] : children })
      : { type, props: props || {}, children: children.flat() });
    const out = jobs.map(({ jsx, operate }) => {
      const calls = [];
      const record = (name) => (...args) => { calls.push(name); };
      const data = new Proxy({ gateOpen: true, gateShut: false, on: false, sel: '', idx: 0, v: 0, d: '' }, {
        get: (target, key) => (key in target ? target[key] : record(String(key))),
      });
      // react_generator's JsonUISeeded: the seed as the state, and its setter.
      const seeds = [];
      const JsonUISeeded = ({ seed, children }) => { seeds.push(seed); return children(seed, record('setSeeded')); };
      // A lucide icon (a tab's default icon): an element like any other.
      const Circle = (props) => ({ type: 'svg', props: props || {}, children: [] });
      try {
        const code = esbuild.transformSync(`<>${jsx}</>`, { loader: 'jsx', jsx: 'transform', jsxFactory: 'h', jsxFragment: '"frag"' })
          .code.trim().replace(/;$/, '');
        const tree = new Function('h', 'data', 'JsonUISeeded', 'Circle', `return (${code});`)(h, data, JsonUISeeded, Circle);
        const all = [];
        const walk = (n) => { if (n && typeof n === 'object' && n.props) { all.push(n); n.children.forEach(walk); } };
        walk(tree);
        const pick = {
          checkbox: (n) => n.type === 'input' && n.props.type === 'checkbox',
          radio: (n) => n.type === 'input' && n.props.type === 'radio',
          tab: (n) => n.type === 'button',
          tab2: (n) => n.type === 'button',
          range: (n) => n.type === 'input' && n.props.type === 'range',
          select: (n) => n.type === 'select',
          date: (n) => n.type === 'input' && n.props.type === 'date',
        }[operate];
        // `tab2`: a tab bar's second tab, so a switch is a change of tab.
        const target = operate === 'tab2' ? all.filter(pick)[1] : all.find(pick);
        if (!target) return { error: `no ${operate} element` };
        const outerClicks = all.filter((n) => !pick(n) && typeof n.props.onClick === 'function').length;
        // Where the element starts, before it is operated.
        const initial = {};
        ['defaultChecked', 'checked', 'defaultValue', 'value'].forEach((k) => {
          if (k in target.props) initial[k] = target.props[k];
        });
        if (!target.props.disabled) {
          const event = { target: { checked: true, value: operate === 'date' ? '2026-09-26' : '1', selectedIndex: 1 },
                          currentTarget: {} };
          if (operate === 'range') {
            const el = {};
            if (typeof target.props.ref === 'function') target.props.ref(el);
            target.props.onChange?.(event);
            el.onchange?.();
          } else if (operate === 'tab' || operate === 'tab2') {
            target.props.onClick?.(event);
          } else {
            target.props.onChange?.(event);
          }
        }
        return { calls, disabled: !!target.props.disabled, outerClicks, initial, seeds };
      } catch (e) {
        return { error: String(e.message).split('\\n')[0] };
      }
    });
    process.stdout.write(JSON.stringify(out));
  JS

  run = lambda do |jobs|
    Dir.mktmpdir('rjui_control_onclick') do |dir|
      File.write(File.join(dir, 'main.js'), node_program)
      File.write(File.join(dir, 'jobs.json'), JSON.generate(jobs))
      out, err, status = Open3.capture3('node', File.join(dir, 'main.js'), CONTROL_ESBUILD, File.join(dir, 'jobs.json'))
      raise "node failed: #{err}" unless status.success?

      JSON.parse(out)
    end
  end

  # Each control under five declarations: the call, the two gates, a bound
  # gate open and shut.
  cases = {
    'operated' => { 'onClick' => '@{onTap}' },
    'canTap: false' => { 'onClick' => '@{onTap}', 'canTap' => false },
    'enabled: false' => { 'onClick' => '@{onTap}', 'enabled' => false },
    'a bound canTap, open' => { 'onClick' => '@{onTap}', 'canTap' => '@{gateOpen}' },
    'a bound canTap, shut' => { 'onClick' => '@{onTap}', 'canTap' => '@{gateShut}' },
    'selectors on onclick' => { 'onclick' => %w[first second] }
  }

  before(:context) do
    skip 'node is not on PATH: UNMEASURED here' unless system('which node > /dev/null 2>&1') || ENV['CI']
    skip 'esbuild is not installed (npm ci --prefix rjui_tools/spec/support): UNMEASURED here' unless File.directory?(CONTROL_ESBUILD) || ENV['CI']

    @rows = controls.flat_map do |type, attrs, operate|
      cases.map { |name, extra| { type: type, attrs: attrs, operate: operate, case: name, jsx: emit.(type, attrs.merge(extra)) } }
    end
    run.(@rows.map { |r| { jsx: r[:jsx], operate: r[:operate] } }).each_with_index { |result, i| @rows[i][:result] = result }
  end

  # The measured result of one control under one declaration.
  def control_result(type, attrs, name)
    @rows.find { |r| r[:type] == type && r[:attrs] == attrs && r[:case] == name }[:result]
  end

  controls.each do |type, attrs, _|
    bound = attrs.values.any? { |v| v.is_a?(String) && v.start_with?('@{') }
    describe "#{type}#{bound ? '' : ' (static)'}" do
      result = ->(example, name) { example.control_result(type, attrs, name) }

      it 'calls the declared onClick once, after its own update, and from nothing else' do
        got = result.(self, 'operated')
        expect(got['error']).to be_nil
        expect(got['calls'].count('onTap')).to eq(1), got.inspect
        expect(got['calls'].last).to eq('onTap'), got.inspect
        # The control's own update (its write-back, or the seeded state) ran first.
        expect(got['calls'][0...-1]).not_to be_empty, got.inspect
        expect(got['outerClicks']).to eq(0), 'a plain onClick besides the operation'
      end

      it 'calls it 0 times with canTap: false' do
        expect(result.(self, 'canTap: false')['calls']).not_to include('onTap')
      end

      it 'calls it 0 times with enabled: false (the operated element is disabled)' do
        got = result.(self, 'enabled: false')
        expect(got['disabled']).to be(true)
        expect(got['calls']).to eq([])
      end

      it 'follows a bound canTap' do
        expect(result.(self, 'a bound canTap, open')['calls'].count('onTap')).to eq(1)
        expect(result.(self, 'a bound canTap, shut')['calls']).not_to include('onTap')
      end

      it 'calls onclick selectors in their order' do
        expect(result.(self, 'selectors on onclick')['calls'].last(2)).to eq(%w[first second])
      end
    end
  end

  # A control starts where it is declared, whatever handlers it also has.
  # From bae96913 a single Radio declared `checked` started unchecked once
  # it had an onClick (the handler took the place of its `defaultChecked`),
  # and with an onValueChange it already had; a regression the emit
  # measurement of the agent pack found on 1.8.121. Every control, in a
  # static and a bound form, is evaluated with no handler, an onClick and an
  # onValueChange: the operated element's state before it is operated
  # (defaultChecked / checked / defaultValue / value) and the seed a
  # seeded control starts from must not move.
  seeded = [
    ['Switch', { 'isOn' => true }, 'checkbox'], ['Switch', { 'isOn' => '@{on}' }, 'checkbox'],
    ['Toggle', { 'isOn' => true }, 'checkbox'], ['Toggle', { 'isOn' => '@{on}' }, 'checkbox'],
    ['CheckBox', { 'checked' => true, 'label' => 'L' }, 'checkbox'], ['CheckBox', { 'checked' => '@{on}', 'label' => 'L' }, 'checkbox'],
    ['Radio', { 'group' => 'g', 'text' => 'R', 'checked' => true }, 'radio'],
    ['Radio', { 'group' => 'g', 'text' => 'R', 'checked' => '@{on}' }, 'radio'],
    ['Radio', { 'items' => %w[a b], 'selectedValue' => 'a' }, 'radio'],
    ['Radio', { 'items' => %w[a b], 'selectedValue' => '@{sel}' }, 'radio'],
    ['Segment', { 'items' => %w[a b], 'selectedIndex' => 1 }, 'tab'],
    ['Slider', { 'value' => 0.5 }, 'range'], ['Slider', { 'value' => '@{v}' }, 'range'],
    ['SelectBox', { 'items' => %w[a b], 'selectedIndex' => 1 }, 'select'],
    ['SelectBox', { 'selectItemType' => 'Date', 'selectedDate' => '2026-09-26' }, 'date'],
    ['SelectBox', { 'selectItemType' => 'Date', 'selectedDate' => '@{d}' }, 'date']
  ]
  handlers = { 'no handler' => {}, 'an onClick' => { 'onClick' => '@{onTap}' }, 'an onValueChange' => { 'onValueChange' => '@{onPick}' } }

  before(:context) do
    next if @rows.nil?

    @seeded_rows = seeded.flat_map do |type, attrs, operate|
      handlers.map { |name, extra| { type: type, attrs: attrs, operate: operate, handler: name, jsx: emit.(type, attrs.merge(extra)) } }
    end
    run.(@seeded_rows.map { |r| { jsx: r[:jsx], operate: r[:operate] } }).each_with_index { |result, i| @seeded_rows[i][:result] = result }
  end

  def seeded_start(type, attrs, handler)
    got = @seeded_rows.find { |r| r[:type] == type && r[:attrs] == attrs && r[:handler] == handler }[:result]
    raise got['error'] if got['error']

    [got['initial'], got['seeds']]
  end

  describe 'a control starts where it is declared, whatever handlers it has' do
    seeded.each do |type, attrs, operate|
      it "#{type} #{attrs.inspect}" do
        starts = handlers.keys.map { |name| seeded_start(type, attrs, name) }
        expect(starts.uniq.size).to eq(1), handlers.keys.zip(starts).inspect
        # And the declared state is there to keep: a radio's `value` is its
        # identity, not its state.
        initial, seeds = starts.first
        state = operate == 'radio' ? initial.reject { |k, _| k == 'value' } : initial
        expect(state.empty? && seeds.empty?).to be(false), starts.first.inspect
      end
    end

    # The single Radio's 2 x 2 (and the onValueChange it had lost it to
    # before bae96913): declared checked starts checked, undeclared does not.
    it 'a single Radio: checked or not, with a handler or not' do
      radio = { 'group' => 'g', 'text' => 'R' }
      [{}, { 'onClick' => '@{onTap}' }, { 'onValueChange' => '@{onPick}' }].each do |extra|
        declared = run.([{ jsx: emit.('Radio', radio.merge('checked' => true).merge(extra)), operate: 'radio' }]).first
        undeclared = run.([{ jsx: emit.('Radio', radio.merge(extra)), operate: 'radio' }]).first
        expect(declared['initial']['defaultChecked']).to be(true), "#{extra.inspect}: #{declared.inspect}"
        expect(undeclared['initial']).not_to include('defaultChecked', 'checked'), "#{extra.inspect}: #{undeclared.inspect}"
      end
    end
  end

  # A TabView with `enabled: false` switches no tab (the ruling for the five
  # paths: `enabled: false` stops the operation). Until 1.9.0 web read no
  # `enabled` on a TabView, and a click on a tab switched it. The second
  # tab is operated: its button is disabled, and a browser sends no click to
  # a disabled button, so neither the seeded state nor the selection handler
  # is called. A bound `enabled` follows its value; an undeclared one is as
  # it was.
  describe 'a TabView with enabled: false' do
    tab_view = ->(extra) { emit.('TabView', { 'tabs' => [{ 'title' => 'a' }, { 'title' => 'b' }] }.merge(extra)) }
    enabled_cases = { 'enabled: false' => { 'enabled' => false }, 'a bound enabled, shut' => { 'enabled' => '@{gateShut}' },
                      'a bound enabled, open' => { 'enabled' => '@{gateOpen}' }, 'no enabled' => {} }

    it 'switches no tab, and follows a bound enabled' do
      got = enabled_cases.transform_values { |extra| run.([{ jsx: tab_view.(extra), operate: 'tab2' }]).first }
      expect(got['enabled: false']).to include('disabled' => true, 'calls' => [])
      expect(got['a bound enabled, shut']).to include('disabled' => true, 'calls' => [])
      expect(got['a bound enabled, open']['calls']).to eq(%w[setSeeded setSelectedTabIndex]), got.inspect
      expect(got['no enabled']['calls']).to eq(%w[setSeeded setSelectedTabIndex]), got.inspect
      expect(tab_view.({})).not_to include('disabled')
    end

    it 'writes TSX that compiles', :typescript_compile do
      tsx = TypeScriptCompiler.component(tab_view.({ 'enabled' => false }), tab_view.({ 'enabled' => '@{gate}' }))
      expect(tsx).to compile_as_typescript.with_ambient(<<~TS)
        declare namespace JSX {
          interface IntrinsicElements {
            button: { [attr: string]: unknown; onClick?: () => void; disabled?: boolean };
          }
        }
        declare function JsonUISeeded<T>(props: { seed: T; children: (value: T, set: (value: T) => void) => JSX.Element }): JSX.Element;
        declare const Circle: (props: { className?: string }) => JSX.Element;
        declare const data: { gate: boolean; selectedTabIndex?: number; setSelectedTabIndex?: (index: number) => void };
      TS
    end
  end

  # With no onClick the output is what it was, byte for byte: the operation
  # handler comes from operation_attr, which writes the old spelling.
  it 'leaves a control with no onClick as it was' do
    expect(emit.('Switch', { 'isOn' => '@{on}' })).to include('onChange={(e) => data.onOnChange?.(e.target.checked)}')
    expect(emit.('Slider', { 'value' => '@{v}' })).not_to include('ref=')
    expect(emit.('Toggle', {})).not_to include('onChange')
  end

  it 'writes TSX that compiles', :typescript_compile do
    elements = controls.map { |type, attrs, _| emit.(type, attrs.merge('onClick' => '@{onTap}', 'canTap' => '@{gate}')) }
    tsx = "export const Emitted = (): JSX.Element => (\n  <>\n#{elements.join("\n")}\n  </>\n);\n"
    # The elements are typed as far as the handlers need, so the arrow
    # parameters are contextually typed by lib.dom (a misspelt member fails);
    # the rest of each element's attributes are open.
    ambient = <<~TS
      declare namespace JSX {
        interface Element {}
        interface ElementChildrenAttribute { children: {} }
        interface IntrinsicElements {
          input: { [attr: string]: unknown; onChange?: (e: { target: HTMLInputElement }) => void;
                   onClick?: (e: { currentTarget: HTMLInputElement }) => void;
                   ref?: (el: HTMLInputElement | null) => void };
          select: { [attr: string]: unknown; onChange?: (e: { target: HTMLSelectElement }) => void };
          button: { [attr: string]: unknown; onClick?: () => void };
          label: { [attr: string]: unknown }; span: { [attr: string]: unknown };
          div: { [attr: string]: unknown }; option: { [attr: string]: unknown };
        }
      }
      declare const React: any;
      declare function JsonUISeeded<T>(props: { seed: T; children: (value: T, set: (value: T) => void) => JSX.Element }): JSX.Element;
      declare const data: {
        on: boolean; sel: string; idx: number; v: number; d: string; gate: boolean;
        onTap?: () => void; onOnChange?: (value: boolean) => void; setSel?: (value: string) => void;
        setIdx?: (value: number) => void; onIdxChange?: (value: number) => void;
        onVChange?: (value: number) => void; onDChange?: (value: string) => void;
      };
    TS
    expect(tsx).to compile_as_typescript.with_ambient(ambient)
  end
end
