# frozen_string_literal: true

require 'json'
require_relative '../../lib/core/binding_validator'

# A bare handler name (`"onValueChange": "onTab"`) on an attribute that takes
# one is a use of the data it names. Measured on jsonui-cli 1.9.5 (kjui):
# every bare handler name — View.onclick, Collection.onItemAppear,
# TabView.onValueChange, TextField.onTextChange — warned "Data property 'h'
# is defined but never used". The use count sat behind
# report_undeclared_selectors?, which no face turns on, and the attributes it
# looked at were a hand-kept list of 14 names. Which attributes take a bare
# name is now read from the SSoT (build_handler_attrs): an on<Upper> key
# whose type takes a string, with its aliases, and the UIKit selector keys.
# This file is the same on sjui, kjui and rjui (shared/core).
RSpec.describe RjuiTools::Core::BindingValidator, '(a bare handler name is a use of its data)' do
  subject(:validator) { described_class.new }

  # The list this replaced, kept to print what moved.
  HAND_KEPT = %w[onclick onClick onLongPress onPan onPinch onDragStart onDrop onDragEnter onDragLeave onDragOver
                 valueChange onTextChange onChange onItemAppear].freeze

  let(:defs) { validator.instance_variable_get(:@attribute_definitions) }
  let(:by_type) { validator.instance_variable_get(:@handler_attrs_by_type) }
  let(:derived) { by_type.values.reduce(Set.new, :|) }

  def never_used(warnings, name)
    warnings.select { |w| w.include?("Data property '#{name}'") && w.include?('never used') }
  end

  def layout(type, attr, value, declared: true)
    data = declared ? [{ 'name' => value, 'class' => 'Function' }] : [{ 'name' => 'other', 'class' => 'String' }]
    { 'type' => 'View', 'id' => 'root', 'data' => data,
      'child' => [{ 'type' => type, 'id' => 'x', attr => value }, { 'type' => 'Label', 'id' => 'l', 'text' => '@{other}' }] }
  end

  it 'reads the handler attributes from the SSoT, and prints what moved from the hand-kept list' do
    added = (derived - HAND_KEPT).sort
    removed = (HAND_KEPT - derived.to_a).sort
    puts "\n  handler attribute names: #{derived.size} (hand-kept #{HAND_KEPT.size})"
    puts "  added:   #{added.join(' ')}"
    puts "  removed: #{removed.join(' ')}"
    # Binding-only events take `@{name}` only; `onChange` is declared nowhere.
    expect(removed).to eq(%w[onChange onClick onDragEnter onDragLeave onDragOver onDragStart onDrop onLongPress onPan onPinch])
    expect(added).to include('onValueChange', 'onPageChanged', 'onValueChanged', 'onAppear', 'onSubmit')
  end

  it 'classifies by what the SSoT says the key is' do
    # Every on<Upper> key that takes a string is a handler by its own
    # description, but the declared exceptions; the exceptions exist and are
    # not; the selector keys exist. A new string key that is no handler
    # turns this red instead of being counted as one.
    described = %r{handler|callback|selector|event}i
    string_on_keys = defs.flat_map do |type, attrs|
      next [] unless attrs.is_a?(Hash)

      attrs.select { |k, d| k.match?(/\Aon[A-Z]/) && d.is_a?(Hash) && Array(d['type']).include?('string') }
           .map { |k, d| [type, k, d['description'].to_s] }
    end
    expect(string_on_keys).not_to be_empty
    string_on_keys.each do |type, key, description|
      if described_class::NOT_HANDLER_KEYS.include?(key)
        expect(description).not_to match(described), "#{type}.#{key}: #{description}"
      else
        expect(description).to match(described), "#{type}.#{key} takes a string and names no handler: #{description}"
      end
    end
    described_class::NOT_HANDLER_KEYS.each { |key| expect(string_on_keys.map { |_, k, _| k }).to include(key) }
    described_class::LEGACY_SELECTOR_KEYS.each do |key|
      expect(defs.any? { |_, attrs| attrs.is_a?(Hash) && attrs.key?(key) }).to be(true), key
    end
  end

  it 'counts a bare name on every handler attribute as a use' do
    cases = by_type.flat_map { |type, names| names.map { |n| [type, n] } }.reject { |type, _| type == 'common' }
    cases += by_type.fetch('common', []).map { |n| ['View', n] }
    puts "\n  (type, attribute) pairs: #{cases.size}"
    cases.each do |type, attr|
      warnings = validator.validate(layout(type, attr, 'handleIt'), 'a.json')
      expect(never_used(warnings, 'handleIt')).to be_empty, "#{type}.#{attr}: #{warnings.join("\n")}"
    end
  end

  it 'counts the measured case: a TabView and a pager given a bare onValueChange' do
    %w[TabView Collection].each do |type|
      warnings = validator.validate(layout(type, 'onValueChange', 'onTab'), 'a.json')
      expect(never_used(warnings, 'onTab')).to be_empty, "#{type}: #{warnings.join("\n")}"
    end
  end

  it 'leaves a bare name on a binding-only event, and on a colour, unused (controls)' do
    [%w[Button onClick], %w[Switch onValueChange], %w[Switch onTintColor]].each do |type, attr|
      warnings = validator.validate(layout(type, attr, 'handleIt'), 'a.json')
      expect(never_used(warnings, 'handleIt').size).to eq(1), "#{type}.#{attr}: #{warnings.join("\n")}"
    end
  end

  it 'reads every name some type handles on a type the SSoT does not declare' do
    warnings = validator.validate(layout('MyWidget', 'onItemAppear', 'handleIt'), 'a.json')
    expect(never_used(warnings, 'handleIt')).to be_empty, warnings.join("\n")
  end

  context 'with undeclared selectors reported' do
    subject(:validator) do
      Class.new(described_class) { def report_undeclared_selectors? = true }.new
    end

    it 'names an undeclared bare handler on a handler attribute' do
      warnings = validator.validate(layout('TabView', 'onValueChange', 'onTab', declared: false), 'a.json')
      expect(warnings.grep(/Handler 'onTab' in 'TabView.onValueChange' is not defined in data/)).not_to be_empty, warnings.join("\n")
    end
  end
end
