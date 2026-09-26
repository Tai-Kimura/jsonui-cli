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
# Until 1.8.121 rjui called it from none of them (the handler's name did not
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

  emit = lambda do |type, attrs|
    node = { 'type' => type, 'id' => 'c' }.merge(attrs)
    view = RjuiTools::React::Converters::ViewConverter.new({ 'type' => 'View' }, CONTROL_CONFIG.dup)
    view.send(:get_converter_class, type).new(node, CONTROL_CONFIG.dup).convert
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
      const JsonUISeeded = ({ seed, children }) => children(seed, record('setSeeded'));
      try {
        const code = esbuild.transformSync(`<>${jsx}</>`, { loader: 'jsx', jsx: 'transform', jsxFactory: 'h', jsxFragment: '"frag"' })
          .code.trim().replace(/;$/, '');
        const tree = new Function('h', 'data', 'JsonUISeeded', `return (${code});`)(h, data, JsonUISeeded);
        const all = [];
        const walk = (n) => { if (n && typeof n === 'object' && n.props) { all.push(n); n.children.forEach(walk); } };
        walk(tree);
        const pick = {
          checkbox: (n) => n.type === 'input' && n.props.type === 'checkbox',
          radio: (n) => n.type === 'input' && n.props.type === 'radio',
          tab: (n) => n.type === 'button',
          range: (n) => n.type === 'input' && n.props.type === 'range',
          select: (n) => n.type === 'select',
          date: (n) => n.type === 'input' && n.props.type === 'date',
        }[operate];
        const target = all.find(pick);
        if (!target) return { error: `no ${operate} element` };
        const outerClicks = all.filter((n) => !pick(n) && typeof n.props.onClick === 'function').length;
        if (!target.props.disabled) {
          const event = { target: { checked: true, value: operate === 'date' ? '2026-09-26' : '1', selectedIndex: 1 },
                          currentTarget: {} };
          if (operate === 'range') {
            const el = {};
            if (typeof target.props.ref === 'function') target.props.ref(el);
            target.props.onChange?.(event);
            el.onchange?.();
          } else if (operate === 'tab') {
            target.props.onClick?.(event);
          } else {
            target.props.onChange?.(event);
          }
        }
        return { calls, disabled: !!target.props.disabled, outerClicks };
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
