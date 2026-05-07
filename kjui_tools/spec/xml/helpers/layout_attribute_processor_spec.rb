# frozen_string_literal: true

require 'xml/helpers/layout_attribute_processor'
require 'xml/helpers/attribute_mapper'

RSpec.describe XmlGenerator::LayoutAttributeProcessor do
  let(:attribute_mapper) { XmlGenerator::AttributeMapper.new }
  let(:processor) { described_class.new(attribute_mapper) }

  describe '#process_dimensions' do
    it 'returns match_parent for root elements' do
      result = processor.process_dimensions({}, true, nil)
      expect(result['android:layout_width']).to eq('match_parent')
      expect(result['android:layout_height']).to eq('match_parent')
    end

    it 'returns wrap_content for non-root elements' do
      result = processor.process_dimensions({}, false, nil)
      expect(result['android:layout_width']).to eq('wrap_content')
      expect(result['android:layout_height']).to eq('wrap_content')
    end

    it 'uses 0dp width when weight specified in horizontal layout' do
      result = processor.process_dimensions({ 'weight' => 1 }, false, 'horizontal')
      expect(result['android:layout_width']).to eq('0dp')
    end

    it 'uses 0dp height when weight specified in vertical layout' do
      result = processor.process_dimensions({ 'weight' => 1 }, false, 'vertical')
      expect(result['android:layout_height']).to eq('0dp')
    end

    it 'uses explicit width over weight' do
      result = processor.process_dimensions({ 'weight' => 1, 'width' => 100 }, false, 'horizontal')
      expect(result['android:layout_width']).to eq('100dp')
    end

    it 'uses explicit height over weight' do
      result = processor.process_dimensions({ 'weight' => 1, 'height' => 50 }, false, 'vertical')
      expect(result['android:layout_height']).to eq('50dp')
    end

    it 'passes fill to attribute mapper' do
      result = processor.process_dimensions({ 'width' => 'fill' }, false, nil)
      expect(result['android:layout_width']).not_to be_nil
    end

    it 'passes wrap to attribute mapper' do
      result = processor.process_dimensions({ 'width' => 'wrap' }, false, nil)
      expect(result['android:layout_width']).not_to be_nil
    end
  end

  describe '#process_orientation' do
    it 'sets orientation for LinearLayout' do
      result = processor.process_orientation('LinearLayout', { 'orientation' => 'horizontal' })
      expect(result['android:orientation']).to eq('horizontal')
    end

    it 'defaults to vertical for LinearLayout without orientation' do
      result = processor.process_orientation('LinearLayout', {})
      expect(result['android:orientation']).to eq('vertical')
    end

    it 'returns empty hash for non-LinearLayout' do
      result = processor.process_orientation('FrameLayout', {})
      expect(result).to be_empty
    end
  end

  describe '#process_attributes' do
    it 'skips internal keys' do
      result = processor.process_attributes(
        { 'type' => 'View', 'child' => [], 'children' => [], 'id' => 'test', 'width' => 100, 'height' => 100 },
        nil
      )
      expect(result).not_to have_key('android:type')
      expect(result).not_to have_key('android:child')
    end

    it 'processes background color' do
      result = processor.process_attributes({ 'background' => '#FF0000' }, nil)
      expect(result['android:background']).to eq('#FF0000')
    end

    it 'processes padding' do
      result = processor.process_attributes({ 'padding' => 16 }, nil)
      expect(result['android:padding']).to eq('16dp')
    end

    it 'adds default constraints in ConstraintLayout' do
      result = processor.process_attributes({ 'text' => 'Hello' }, 'ConstraintLayout')
      expect(result['app:layout_constraintStart_toStartOf']).to eq('parent')
      expect(result['app:layout_constraintTop_toTopOf']).to eq('parent')
    end

    it 'does not add default horizontal constraint when alignRight specified' do
      result = processor.process_attributes({ 'alignRight' => true }, 'ConstraintLayout')
      expect(result).not_to have_key('app:layout_constraintStart_toStartOf')
    end

    it 'does not add default vertical constraint when alignBottom specified' do
      result = processor.process_attributes({ 'alignBottom' => true }, 'ConstraintLayout')
      expect(result).not_to have_key('app:layout_constraintTop_toTopOf')
    end

    it 'handles center in parent' do
      result = processor.process_attributes({ 'alignCenterInParent' => true }, 'ConstraintLayout')
      # alignCenterInParent sets both horizontal and vertical constraints
      expect(result.keys.any? { |k| k.include?('constraint') }).to be true
    end
  end
end
