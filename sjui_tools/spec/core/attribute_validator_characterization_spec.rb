# frozen_string_literal: true

require 'core/attribute_validator'

# Characterization of AttributeValidator paths not covered by
# attribute_validator_spec: the type-synonym mapping tail, platform-scoped
# attribute info, value-type edges, and the weight/dimension advisories.
# Fixes current behavior ahead of the validator consolidation (W3-2).
RSpec.describe SjuiTools::Core::AttributeValidator do
  subject(:validator) { described_class.new(:swiftui) }

  describe '#map_type_to_definition synonym tail' do
    {
      'Textarea' => 'TextView',
      'Img' => 'Image',
      'AsyncImage' => 'NetworkImage',
      'TabLayout' => 'Segment',
      'ProgressBar' => 'Progress',
      'Loading' => 'Indicator',
      'SafeAreaView' => 'SafeAreaView',
      'Scroll' => 'ScrollView',
      'ListView' => 'Collection',
      'Gradient' => 'GradientView',
      'BlurView' => 'Blur',
      'Iframe' => 'Web'
    }.each do |synonym, canonical|
      it "maps #{synonym} to #{canonical}" do
        expect(validator.send(:map_type_to_definition, synonym)).to eq(canonical)
      end
    end
  end

  describe 'platform-scoped attributes surface as info, not warnings' do
    it 'reports a UIKit-only attribute as informational in SwiftUI mode' do
      validator.validate({ 'type' => 'View', 'widthWeight' => 1 })
      expect(validator.has_infos?).to be(true)
      expect(validator.infos).to include(
        a_string_matching(/Attribute 'widthWeight' in 'View' is for Uikit mode \(current: Swiftui\)/)
      )
    end

    it 'prints infos with the SJUI Info prefix' do
      validator.validate({ 'type' => 'View', 'widthWeight' => 1 })
      expect { validator.print_infos }.to output(/\[SJUI Info\].*widthWeight/).to_stdout
    end
  end

  describe 'Collection cell identity advisory (SwiftUI/Compose)' do
    it 'suggests cellIdProperty when missing' do
      warnings = validator.validate({ 'type' => 'Collection' })
      expect(warnings).to include(
        a_string_matching(/Collection should have 'cellIdProperty' for unique cell identity/)
      )
    end
  end

  describe 'data-only child definitions' do
    it 'does not flag child arrays that only carry data declarations' do
      warnings = validator.validate(
        { 'type' => 'Label', 'child' => [{ 'data' => [{ 'name' => 'x' }] }] }
      )
      expect(warnings).not_to include(a_string_matching(/Unknown attribute 'child'/))
    end
  end

  describe 'numeric range validation' do
    it 'warns when a value undercuts the declared minimum' do
      warnings = validator.validate({ 'type' => 'View', 'alpha' => -5 })
      expect(warnings).to include(
        a_string_matching(/Attribute 'alpha' in 'View' value -5 is less than minimum 0/)
      )
    end
  end

  describe 'array item validation' do
    it 'checks simple-typed array items against the item definition' do
      warnings = validator.validate({ 'type' => 'View', 'safeAreaInsetPositions' => ['top', 5] })
      expect(warnings).to include(
        a_string_matching(/safeAreaInsetPositions\[1\] in 'View' expects string, got number/)
      )
    end

    it 'rejects non-object items where the item definition has properties' do
      warnings = validator.validate({ 'type' => 'Label', 'partialAttributes' => [123] })
      expect(warnings).to include(
        a_string_matching(/partialAttributes\[0\] in 'Label' expects object, got number/)
      )
    end
  end

  describe 'value-type classification edges' do
    it 'classifies nil as null and unhandled classes as unknown' do
      expect(validator.send(:get_value_type, nil)).to eq('null')
      expect(validator.send(:get_value_type, :symbol)).to eq('unknown')
    end
  end

  describe 'type matching edges' do
    it 'accepts anything for the any type' do
      expect(validator.send(:type_matches?, 'string', ['any'], 'x')).to be(true)
    end

    it 'checks every array element against an enum definition' do
      expect(validator.send(:type_matches?, 'array', [{ 'enum' => %w[a b] }], %w[a b])).to be(true)
      expect(validator.send(:type_matches?, 'array', [{ 'enum' => %w[a] }], %w[a z])).to be(false)
    end

    it 'rejects non-string/array actuals against enum definitions' do
      expect(validator.send(:type_matches?, 'number', [{ 'enum' => %w[a] }], 5)).to be(false)
    end

    it 'rejects hash definitions without enum' do
      expect(validator.send(:type_matches?, 'string', [{ 'foo' => 1 }], 'x')).to be(false)
    end

    it 'falls back to exact equality for plain expected types' do
      expect(validator.send(:type_matches?, 'number', ['number'], 5)).to be(true)
    end
  end

  describe 'weight/dimension advisories' do
    it 'warns that weight is inert without a parent orientation (ZStack)' do
      validator.send(:check_weight_dimension_conflict, { 'weight' => 1 }, 'View', 'zstack')
      expect(validator.warnings).to include(
        a_string_matching(/has 'weight' but parent has no orientation \(ZStack\)/)
      )
    end

    it 'treats height as weight-substitutable under the default (vertical) orientation' do
      expect(
        validator.send(:skip_dimension_required?, 'height', { 'weight' => 1 }, 'zstack-ish')
      ).to be(true)
    end
  end
end
