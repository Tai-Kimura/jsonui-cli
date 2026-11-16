# frozen_string_literal: true

require 'core/attribute_validator'
require 'core/layout_validator'

# `items: [{"label":"opt_a","value":"a"}]` was stringified into the output:
# iOS shipped `Text("{\"label\"=>\"opt_a\", \"value\"=>\"a\"}")` on screen,
# Android the same string in Compose, and web a Ruby hash inside JSX, which
# does not parse (measured 2026-09-04, all three exiting 0). The SSoT
# declares the elements as static labels, and both dynamic runtimes already
# drop a non-primitive element, so the generators were the only layer that
# disagreed.
RSpec.describe 'Segment items are scalars' do
  let(:described_module) { JsonUIShared::AttributeValidatorCore }
  let(:described_validator) { SjuiTools::Core::AttributeValidator }

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
    let(:validator) { SjuiTools::Core::AttributeValidator.new }

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
    # RULED 2026-09-05: refused, not warned-and-ignored.
    #
    # This used to add a warning saying the binding was "ignored, and no
    # items are generated" — and the build then exited 0 having written a
    # Segment with no items into the app. A declaration violation reported
    # at a level that stops nothing is the shape of green-with-a-hole this
    # release spent the night removing, so `Segment.items` is now refused
    # by the same rule as every other `type: array` attribute that declares
    # no binding.
    let(:validator) { SjuiTools::Core::AttributeValidator.new }

    def findings(node)
      JsonUIShared::LayoutValidator.validate_layout(node, source_path: 'spec.json')
    end

    it 'is refused at :error, which stops the build' do
      w = findings('type' => 'Segment', 'id' => 's', 'items' => '@{options}')
      expect(w.size).to eq(1)
      expect(w.first[:level]).to eq(:error)
      expect(w.first[:message]).to include("'items'")
      expect(w.first[:message]).to include('type: array')
      expect(JsonUIShared::LayoutValidator.blocking?(w)).to be true
    end

    it 'is refused ONCE — the old warning must not still fire beside it' do
      # Both rules matched the same value for a while: the error refused the
      # layout while the warning on the next line said the binding was
      # ignored and generation continued. Two rulings printed together is
      # how a reader learns to believe neither.
      validator.validate({ 'type' => 'Segment', 'items' => '@{options}' }, 'Segment')
      expect(validator.warnings.grep(/is a binding/)).to be_empty
      expect(validator.warnings.grep(/ignored, and no items are generated/)).to be_empty
    end

    it 'says nothing for a declared array' do
      expect(findings('type' => 'Segment', 'id' => 's', 'items' => %w[a b])).to be_empty
      validator.validate({ 'type' => 'Segment', 'items' => %w[a b] }, 'Segment')
      expect(validator.warnings.grep(/is a binding/)).to be_empty
    end

    it 'is scoped to the labels-only attribute' do
      # The control: bindings are legitimate almost everywhere, including
      # on items of a data-source component, which declares
      # `type: ["array", "binding"]`.
      expect(findings('type' => 'Collection', 'id' => 'c', 'items' => '@{rows}')).to be_empty
      expect(findings('type' => 'Segment', 'id' => 's', 'selectedIndex' => '@{i}')).to be_empty
    end
  end

  describe 'a null element' do
    # It passed a rule that named only Hash and Array, and web emitted an
    # empty <button> with a real id — so every later s_tab_n sat one index
    # off the runtimes, which drop it (rjui lane, 2026-09-04). Android
    # tests isJsonPrimitive, and Gson's JsonNull is not one; iOS casts to
    # String/NSNumber, and NSNull is neither.
    it 'is named by its kind, not called an object' do
      validator = described_validator.new
      validator.validate({ 'type' => 'Segment', 'items' => ['opt_a', nil] }, 'Segment')
      warning = validator.warnings.find { |w| w.include?('items[1]') }
      expect(warning).not_to be_nil, validator.warnings.inspect
      expect(warning).to include('is null')
      expect(warning).not_to include('is an object')
    end

    it 'is dropped by the same predicate the converters use' do
      expect(described_module.non_scalar_item_indices('Segment', 'items', ['a', nil, 'b'])).to eq([1])
    end
  end

  describe 'a boolean element' do
    # Kept on purpose. BOTH runtimes render it — Android through
    # isJsonPrimitive, iOS because a Bool bridges to NSNumber — so
    # dropping it here would show fewer tabs than the running screen,
    # which is the divergence this rule exists to close. That it renders
    # "true" on web and Android and "1" on iOS is a real defect, and it
    # belongs to the declaration and the runtimes.
    it 'is not dropped' do
      expect(described_module.non_scalar_item_indices('Segment', 'items', ['a', true, false])).to eq([])
      expect(described_module.scalar_item?(true)).to be(true)
    end
  end

  describe 'what counts as a scalar' do
    it 'matches what the runtimes keep' do
      [['text', true], [1, true], [1.5, true], [true, true], [false, true],
       [nil, false], [{}, false], [[], false]].each do |item, expected|
        expect(described_module.scalar_item?(item)).to be(expected), item.inspect
      end
    end
  end

end
