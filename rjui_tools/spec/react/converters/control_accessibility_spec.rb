# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/react_generator'
require_relative '../../support/typescript_compiler'

# A control's screen-reader name and a node read out when it changes
# (shared/core/control_accessibility.rb): `accessibilityLabel` (alias
# `contentDescription`) is aria-label on the element that takes focus, and
# `accessibilityLiveRegion` is aria-live with role status / alert. Until
# jsonui-cli 2.3.38 neither was declared on these types, and nothing was
# emitted for them.
RSpec.describe 'web control accessibility' do
  def convert(node)
    node = JsonUIShared::ComponentAliases.resolve(JsonUIShared::TapAccessibility.annotate!(JSON.parse(JSON.generate(node))))
    RjuiTools::React::ReactGenerator::CONVERTERS.fetch(node['type']).new(node, { 'use_tailwind' => true }).convert_node(2)
  end

  describe 'accessibilityLabel' do
    {
      'Button' => [{ 'type' => 'Button', 'text' => 'Open', 'onClick' => '@{open}' }, /<button.*? aria-label="Name".*?>Open<\/button>/],
      'TextField' => [{ 'type' => 'TextField', 'id' => 'f', 'text' => '@{q}' }, /<input id="f".*? aria-label="Name"/],
      'Slider' => [{ 'type' => 'Slider', 'id' => 's', 'value' => '@{v}' }, /<input id="s" type="range".*? aria-label="Name"/],
      'SelectBox' => [{ 'type' => 'SelectBox', 'id' => 'b', 'items' => %w[a b] }, /<select id="b".*? aria-label="Name"/],
      'CheckBox' => [{ 'type' => 'CheckBox', 'id' => 'c', 'checked' => '@{on}' }, /<input id="c" type="checkbox" aria-label="Name"/],
      'CheckBox with a label' => [{ 'type' => 'CheckBox', 'label' => 'Wine', 'checked' => '@{on}' }, /<label.*?>\s*<input type="checkbox" aria-label="Name"/],
      'Check (the alias section)' => [{ 'type' => 'Check', 'checked' => '@{on}' }, /<input type="checkbox" aria-label="Name"/],
      'Switch' => [{ 'type' => 'Switch', 'isOn' => '@{on}' }, /<input type="checkbox" aria-label="Name" className="sr-only peer"/],
      'Radio' => [{ 'type' => 'Radio', 'id' => 'r', 'text' => 'A' }, /<input type="radio" aria-label="Name" name="r"/],
      'a Radio group' => [{ 'type' => 'Radio', 'id' => 'g', 'items' => %w[a b], 'selectedValue' => '@{v}' }, /<div id="g".*? role="radiogroup" aria-label="Name">/],
      'Segment' => [{ 'type' => 'Segment', 'id' => 'sg', 'items' => %w[a b] }, /<div id="sg".*? role="group" aria-label="Name">/],
      'a View that is one button' => [{ 'type' => 'View', 'onClick' => '@{open}', 'child' => [{ 'type' => 'Label', 'text' => 'Card' }] }, /<div.*? aria-label="Name".*? role="button"/]
    }.each do |what, (node, shape)|
      it "names #{what} on the element that takes focus" do
        code = convert(node.merge('accessibilityLabel' => 'Name'))
        expect(code).to match(shape)
        expect(code.scan('aria-label=').size).to eq(1)
      end
    end

    it 'reads the contentDescription spelling the same' do
      expect(convert({ 'type' => 'Button', 'text' => 'Open', 'contentDescription' => 'Name' })).to include('aria-label="Name"')
    end

    it 'takes a binding' do
      expect(convert({ 'type' => 'Button', 'text' => 'Open', 'accessibilityLabel' => '@{name}' })).to include('aria-label={`${data.name ?? ""}`}')
    end

    it 'escapes a quote in the text' do
      expect(convert({ 'type' => 'Button', 'text' => 'Open', 'accessibilityLabel' => 'the "second" one' })).to include('aria-label={"the \"second\" one"}')
    end

    it 'names nothing on a View that taps nothing (no element to name)' do
      code = convert({ 'type' => 'View', 'accessibilityLabel' => 'Name', 'child' => [{ 'type' => 'Label', 'text' => 'x' }] })
      expect(code).not_to include('aria-label')
    end

    it 'names nothing when it is empty' do
      expect(convert({ 'type' => 'Button', 'text' => 'Open', 'accessibilityLabel' => '' })).not_to include('aria-label')
    end
  end

  # What it adds reaches a compiler, typed as React types them: aria-label a
  # string, aria-live one of its three values.
  it 'emits attributes that type-check' do
    elements = [
      convert({ 'type' => 'Button', 'text' => 'Open', 'onClick' => '@{open}', 'accessibilityLabel' => '@{name}' }),
      convert({ 'type' => 'Button', 'text' => 'Open', 'accessibilityLabel' => 'the "second" one' }),
      convert({ 'type' => 'CheckBox', 'label' => 'Wine', 'checked' => '@{on}', 'accessibilityLabel' => 'Name' }),
      convert({ 'type' => 'Radio', 'id' => 'g', 'items' => %w[a b], 'selectedValue' => '@{v}', 'accessibilityLabel' => 'Name' }),
      convert({ 'type' => 'Label', 'text' => '@{status}', 'accessibilityLiveRegion' => 'assertive' }),
      convert({ 'type' => 'View', 'onClick' => '@{go}', 'accessibilityLiveRegion' => 'polite', 'child' => [{ 'type' => 'Label', 'text' => '@{s}' }] })
    ]
    ambient = TypeScriptCompiler::AMBIENT.sub('interface IntrinsicElements { [name: string]: any }', <<~TS.chomp)
      interface IntrinsicElements { button: P; input: P; label: P; span: P; div: P }
    TS
    ambient += <<~TS
      type P = {
        'aria-label'?: string; 'aria-live'?: 'polite' | 'assertive' | 'off'; role?: string;
        onChange?: (e: { target: { checked: boolean; value: string } }) => void;
        onKeyDown?: (e: { key: string; preventDefault(): void; currentTarget: { click(): void } }) => void;
        [attr: string]: any
      };
    TS
    ambient += "declare const data: Record<string, any>;\n"
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(ambient)
  end

  describe 'accessibilityLiveRegion' do
    it 'reads a Label out politely' do
      expect(convert({ 'type' => 'Label', 'text' => '@{status}', 'accessibilityLiveRegion' => 'polite' }))
        .to match(/<span.*? role="status" aria-live="polite">/)
    end

    it 'reads a Label out at once when assertive' do
      expect(convert({ 'type' => 'Label', 'text' => '@{error}', 'accessibilityLiveRegion' => 'assertive' }))
        .to match(/<span.*? role="alert" aria-live="assertive">/)
    end

    it 'reads a View out' do
      expect(convert({ 'type' => 'View', 'accessibilityLiveRegion' => 'polite', 'child' => [{ 'type' => 'Label', 'text' => '@{s}' }] }))
        .to match(/<div.*? role="status" aria-live="polite">/)
    end

    it 'keeps the button role of a tappable View, with aria-live alone' do
      code = convert({ 'type' => 'View', 'onClick' => '@{go}', 'accessibilityLiveRegion' => 'polite', 'child' => [{ 'type' => 'Label', 'text' => '@{s}' }] })
      expect(code.scan(' role=').size).to eq(1)
      expect(code).to include('role="button"')
      expect(code).to include('aria-live="polite"')
    end

    it 'reads nothing out when off' do
      code = convert({ 'type' => 'Label', 'text' => '@{s}', 'accessibilityLiveRegion' => 'off' })
      expect(code).not_to include('aria-live')
      expect(code).not_to include('role=')
    end
  end
end
