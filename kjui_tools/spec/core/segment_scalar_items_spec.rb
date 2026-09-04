# frozen_string_literal: true

require 'core/attribute_validator'

# `items: [{"label":"opt_a","value":"a"}]` was stringified into the output:
# iOS shipped `Text("{\"label\"=>\"opt_a\", \"value\"=>\"a\"}")` on screen,
# Android the same string in Compose, and web a Ruby hash inside JSX, which
# does not parse (measured 2026-09-04, all three exiting 0). The SSoT
# declares the elements as static labels, and both dynamic runtimes already
# drop a non-primitive element, so the generators were the only layer that
# disagreed.
RSpec.describe 'Segment items are scalars' do
  let(:described_module) { JsonUIShared::AttributeValidatorCore }

  subject(:indices) do
    ->(type, name, value) { JsonUIShared::AttributeValidatorCore.non_scalar_item_indices(type, name, value) }
  end

  it 'names the object elements by index' do
    value = ['opt_a', { 'label' => 'opt_b', 'value' => 'b' }, 'opt_c', [1]]
    expect(indices.call('Segment', 'items', value)).to eq([1, 3])
  end

  it 'accepts the declared shapes' do
    # Labels, strings keys and numbers are all primitives; the declaration
    # is "static labels; an entry may be a strings key".
    expect(indices.call('Segment', 'items', %w[opt_a sample_opt_b])).to eq([])
    expect(indices.call('Segment', 'items', [1, 2])).to eq([])
    expect(indices.call('Segment', 'items', [])).to eq([])
  end

  it 'is scoped to the attribute the SSoT declares as labels' do
    # The control that keeps this from becoming a rule about every array:
    # Collection.items is a data source, where an object element is exactly
    # what a face may pass.
    value = [{ 'id' => 1 }]
    expect(indices.call('Collection', 'items', value)).to eq([])
    expect(indices.call('Segment', 'selectedIndex', value)).to eq([])
  end

  it 'ignores a binding string, which is not an array at all' do
    expect(indices.call('Segment', 'items', '@{options}')).to eq([])
  end

  describe 'the warning' do
    # The concrete platform validator: the shared core is abstract.
    let(:validator) { KjuiTools::Core::AttributeValidator.new }

    it 'names the layout attribute, the index and what happens' do
      validator.validate(
        { 'type' => 'Segment', 'items' => ['opt_a', { 'label' => 'opt_b' }] }, 'Segment'
      )
      warning = validator.warnings.find { |w| w.include?('items[1]') }
      expect(warning).not_to be_nil, validator.warnings.inspect
      expect(warning).to include('is an object')
      expect(warning).to include('dropped from the generated output')
    end

    it 'says nothing for a declared items array' do
      validator.validate({ 'type' => 'Segment', 'items' => %w[opt_a opt_b] }, 'Segment')
      expect(validator.warnings.grep(/items\[/)).to be_empty
    end
  end
  describe 'a binding where labels are declared' do
    # `Segment.items` is `type: "array"` with no binding, yet kjui resolved
    # `@{options}` into a forEachIndexed and sjui raised NoMethodError on
    # the same input — one face invented a feature, the other crashed, and
    # the type check said nothing because a binding string stands in for
    # any declared type. Usage across seven faces: 0.
    let(:validator) { KjuiTools::Core::AttributeValidator.new }

    it 'names it and says it is ignored' do
      validator.validate({ 'type' => 'Segment', 'items' => '@{options}' }, 'Segment')
      warning = validator.warnings.find { |w| w.include?("'items'") && w.include?('binding') }
      expect(warning).not_to be_nil, validator.warnings.inspect
      expect(warning).to include('ignored')
    end

    it 'says nothing for a declared array' do
      validator.validate({ 'type' => 'Segment', 'items' => %w[a b] }, 'Segment')
      expect(validator.warnings.grep(/is a binding/)).to be_empty
    end

    it 'is scoped to the labels-only attribute' do
      # The control: bindings are legitimate almost everywhere, including
      # on items of a data-source component.
      expect(described_module.binding_in_scalar_items?('Collection', 'items', '@{rows}')).to be(false)
      expect(described_module.binding_in_scalar_items?('Segment', 'selectedIndex', '@{i}')).to be(false)
      expect(described_module.binding_in_scalar_items?('Segment', 'items', '@{options}')).to be(true)
    end
  end

end
