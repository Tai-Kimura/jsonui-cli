# frozen_string_literal: true

require 'compose/components/container_component'
require 'compose/helpers/modifier_builder'

RSpec.describe KjuiTools::Compose::Components::ContainerComponent do
  let(:required_imports) { Set.new }

  describe '.generate' do
    it 'generates Column for vertical orientation' do
      json_data = { 'type' => 'View', 'orientation' => 'vertical' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('Column(')
      expect(result[:layout_type]).to eq('Column')
    end

    it 'generates Row for horizontal orientation' do
      json_data = { 'type' => 'View', 'orientation' => 'horizontal' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('Row(')
      expect(result[:layout_type]).to eq('Row')
    end

    it 'generates Box for no orientation' do
      json_data = { 'type' => 'View' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('Box(')
      expect(result[:layout_type]).to eq('Box')
    end

    it 'returns children for processing' do
      json_data = {
        'type' => 'View',
        'orientation' => 'vertical',
        'child' => [
          { 'type' => 'Text', 'text' => 'Child 1' },
          { 'type' => 'Text', 'text' => 'Child 2' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:children].length).to eq(2)
    end

    it 'handles single child as array' do
      json_data = {
        'type' => 'View',
        'child' => { 'type' => 'Text', 'text' => 'Single child' }
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:children].length).to eq(1)
    end

    it 'adds spacing arrangement for Column' do
      json_data = { 'type' => 'View', 'orientation' => 'vertical', 'spacing' => 8 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('verticalArrangement = Arrangement.spacedBy(8.dp)')
      expect(required_imports).to include(:arrangement)
    end

    it 'adds spacing arrangement for Row' do
      json_data = { 'type' => 'View', 'orientation' => 'horizontal', 'spacing' => 16 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('horizontalArrangement = Arrangement.spacedBy(16.dp)')
    end

    it 'adds distribution for fillEqually' do
      json_data = { 'type' => 'View', 'orientation' => 'vertical', 'distribution' => 'fillEqually' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('Arrangement.SpaceEvenly')
    end

    it 'adds distribution for fill' do
      json_data = { 'type' => 'View', 'orientation' => 'horizontal', 'distribution' => 'fill' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('Arrangement.SpaceBetween')
    end

    it 'adds distribution for equalSpacing' do
      json_data = { 'type' => 'View', 'orientation' => 'vertical', 'distribution' => 'equalSpacing' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('Arrangement.SpaceAround')
    end

    it 'reverses children for bottomToTop direction' do
      json_data = {
        'type' => 'View',
        'orientation' => 'vertical',
        'direction' => 'bottomToTop',
        'child' => [
          { 'type' => 'Text', 'text' => 'First' },
          { 'type' => 'Text', 'text' => 'Last' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:children].first['text']).to eq('Last')
    end

    it 'reverses children for rightToLeft direction in Row' do
      json_data = {
        'type' => 'View',
        'orientation' => 'horizontal',
        'direction' => 'rightToLeft',
        'child' => [
          { 'type' => 'Text', 'text' => 'Left' },
          { 'type' => 'Text', 'text' => 'Right' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:children].first['text']).to eq('Right')
    end

    it 'includes closing bracket' do
      json_data = { 'type' => 'View', 'orientation' => 'vertical' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:closing]).to include('}')
    end
  end

  describe '.add_gravity_settings' do
    it 'adds top gravity for Column' do
      json_data = { 'type' => 'View', 'orientation' => 'vertical', 'gravity' => 'top' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('verticalArrangement = Arrangement.Top')
    end

    it 'adds bottom gravity for Column' do
      json_data = { 'type' => 'View', 'orientation' => 'vertical', 'gravity' => 'bottom' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('verticalArrangement = Arrangement.Bottom')
    end

    it 'adds centerVertical gravity for Column' do
      json_data = { 'type' => 'View', 'orientation' => 'vertical', 'gravity' => 'centerVertical' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('verticalArrangement = Arrangement.Center')
    end

    it 'adds horizontal alignment for Column' do
      json_data = { 'type' => 'View', 'orientation' => 'vertical', 'gravity' => 'centerHorizontal' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('horizontalAlignment = Alignment.CenterHorizontally')
    end

    it 'adds left gravity for Row' do
      json_data = { 'type' => 'View', 'orientation' => 'horizontal', 'gravity' => 'left' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('horizontalArrangement = Arrangement.Start')
    end

    it 'adds vertical alignment for Row' do
      json_data = { 'type' => 'View', 'orientation' => 'horizontal', 'gravity' => 'centerVertical' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('verticalAlignment = Alignment.CenterVertically')
    end
  end

  describe 'IntrinsicSize injection for matchParent children' do
    it 'replaces wrapContentHeight with height(IntrinsicSize.Min) on Row when a child uses height matchParent' do
      json_data = {
        'type' => 'View',
        'orientation' => 'horizontal',
        'width' => 'matchParent',
        'height' => 'wrapContent',
        'child' => [
          { 'type' => 'View', 'width' => 4, 'height' => 'matchParent' },
          { 'type' => 'View', 'weight' => 1 }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('.height(IntrinsicSize.Min)')
      expect(result[:code]).not_to include('.wrapContentHeight()')
      expect(required_imports).to include(:intrinsic_size)
    end

    it 'replaces wrapContentWidth with width(IntrinsicSize.Min) on Column when a child uses width matchParent' do
      json_data = {
        'type' => 'View',
        'orientation' => 'vertical',
        'width' => 'wrapContent',
        'height' => 'matchParent',
        'child' => [
          { 'type' => 'View', 'width' => 'matchParent', 'height' => 4 }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('.width(IntrinsicSize.Min)')
      expect(result[:code]).not_to include('.wrapContentWidth()')
      expect(required_imports).to include(:intrinsic_size)
    end

    it 'does not inject IntrinsicSize when parent height is fixed' do
      json_data = {
        'type' => 'View',
        'orientation' => 'horizontal',
        'height' => 200,
        'child' => [
          { 'type' => 'View', 'height' => 'matchParent' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).not_to include('IntrinsicSize')
      expect(required_imports).not_to include(:intrinsic_size)
    end

    it 'does not inject IntrinsicSize when parent height is matchParent' do
      json_data = {
        'type' => 'View',
        'orientation' => 'horizontal',
        'height' => 'matchParent',
        'child' => [
          { 'type' => 'View', 'height' => 'matchParent' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).not_to include('IntrinsicSize')
    end

    it 'does not inject IntrinsicSize when no child uses matchParent on the cross axis' do
      json_data = {
        'type' => 'View',
        'orientation' => 'horizontal',
        'height' => 'wrapContent',
        'child' => [
          { 'type' => 'View', 'height' => 24 },
          { 'type' => 'View', 'height' => 'wrapContent' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).not_to include('IntrinsicSize')
    end

    it 'does not inject IntrinsicSize on Box (only Row/Column eligible)' do
      json_data = {
        'type' => 'View',
        'height' => 'wrapContent',
        'child' => [
          { 'type' => 'View', 'height' => 'matchParent' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).not_to include('IntrinsicSize')
    end

    it 'detects matchParent declared via frame.height on the child' do
      json_data = {
        'type' => 'View',
        'orientation' => 'horizontal',
        'height' => 'wrapContent',
        'child' => [
          { 'type' => 'View', 'frame' => { 'width' => 4, 'height' => 'matchParent' } }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('.height(IntrinsicSize.Min)')
    end

    it 'injects IntrinsicSize when parent height attribute is omitted (Compose default = wrapContent)' do
      json_data = {
        'type' => 'View',
        'orientation' => 'horizontal',
        'width' => 'matchParent',
        'child' => [
          { 'type' => 'View', 'height' => 'matchParent' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('.height(IntrinsicSize.Min)')
    end
  end

  describe '.has_relative_positioning?' do
    it 'detects relative positioning attributes' do
      children = [{ 'type' => 'View', 'alignTopOfView' => 'other' }]
      result = described_class.send(:has_relative_positioning?, children)
      expect(result).to be true
    end

    it 'returns false for no relative positioning' do
      children = [{ 'type' => 'Text', 'text' => 'Hello' }]
      result = described_class.send(:has_relative_positioning?, children)
      expect(result).to be false
    end

    it 'handles non-hash children' do
      children = ['string', nil]
      result = described_class.send(:has_relative_positioning?, children)
      expect(result).to be false
    end
  end

  describe '.determine_layout' do
    it 'returns Column for vertical orientation' do
      result = described_class.send(:determine_layout, 'View', 'vertical')
      expect(result).to eq('Column')
    end

    it 'returns Row for horizontal orientation' do
      result = described_class.send(:determine_layout, 'View', 'horizontal')
      expect(result).to eq('Row')
    end

    it 'returns Box for no orientation' do
      result = described_class.send(:determine_layout, 'View', nil)
      expect(result).to eq('Box')
    end

    it 'returns Box for unknown container type' do
      result = described_class.send(:determine_layout, 'Unknown', 'vertical')
      expect(result).to eq('Box')
    end
  end
end
