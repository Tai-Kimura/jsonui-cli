# frozen_string_literal: true

require 'xml/helpers/component_mapper'

RSpec.describe XmlGenerator::ComponentMapper do
  let(:mapper) { described_class.new }

  describe '#map_component' do
    it 'maps Label to KjuiTextView' do
      result = mapper.map_component('Label')
      expect(result).to eq('com.kotlinjsonui.views.KjuiTextView')
    end

    it 'maps Text to KjuiTextView' do
      result = mapper.map_component('Text')
      expect(result).to eq('com.kotlinjsonui.views.KjuiTextView')
    end

    it 'maps Button to KjuiButton' do
      result = mapper.map_component('Button')
      expect(result).to eq('com.kotlinjsonui.views.KjuiButton')
    end

    it 'maps TextField to KjuiEditText' do
      result = mapper.map_component('TextField')
      expect(result).to eq('com.kotlinjsonui.views.KjuiEditText')
    end

    it 'maps Image to ImageView' do
      result = mapper.map_component('Image')
      expect(result).to eq('ImageView')
    end

    it 'maps Switch to Switch' do
      result = mapper.map_component('Switch')
      expect(result).to eq('Switch')
    end

    it 'maps HStack to LinearLayout' do
      result = mapper.map_component('HStack')
      expect(result).to eq('LinearLayout')
    end

    it 'maps VStack to LinearLayout' do
      result = mapper.map_component('VStack')
      expect(result).to eq('LinearLayout')
    end

    it 'maps ZStack to FrameLayout' do
      result = mapper.map_component('ZStack')
      expect(result).to eq('FrameLayout')
    end

    it 'maps View with orientation to LinearLayout' do
      json = { 'orientation' => 'horizontal' }
      result = mapper.map_component('View', json)
      expect(result).to eq('LinearLayout')
    end

    it 'maps View without orientation to ConstraintLayout' do
      json = {}
      result = mapper.map_component('View', json)
      expect(result).to eq('androidx.constraintlayout.widget.ConstraintLayout')
    end

    it 'maps Collection to RecyclerView' do
      result = mapper.map_component('Collection')
      expect(result).to eq('androidx.recyclerview.widget.RecyclerView')
    end

    it 'maps Card to MaterialCardView' do
      result = mapper.map_component('Card')
      expect(result).to eq('com.google.android.material.card.MaterialCardView')
    end

    it 'maps unknown type to View' do
      result = mapper.map_component('UnknownType')
      expect(result).to eq('View')
    end

    it 'maps Custom prefixed types to include' do
      result = mapper.map_component('CustomHeader')
      expect(result).to eq('include')
    end

    it 'maps unknown type with children to FrameLayout' do
      json = { 'child' => [{ 'type' => 'Text' }] }
      result = mapper.map_component('UnknownContainer', json)
      expect(result).to eq('FrameLayout')
    end
  end

  describe '#is_container?' do
    it 'returns true for View' do
      expect(mapper.is_container?('View')).to be true
    end

    it 'returns true for HStack' do
      expect(mapper.is_container?('HStack')).to be true
    end

    it 'returns true for VStack' do
      expect(mapper.is_container?('VStack')).to be true
    end

    it 'returns true for ZStack' do
      expect(mapper.is_container?('ZStack')).to be true
    end

    it 'returns true for ScrollView' do
      expect(mapper.is_container?('ScrollView')).to be true
    end

    it 'returns true for Collection' do
      expect(mapper.is_container?('Collection')).to be true
    end

    it 'returns false for Text' do
      expect(mapper.is_container?('Text')).to be false
    end

    it 'returns false for Button' do
      expect(mapper.is_container?('Button')).to be false
    end
  end

  describe '#needs_adapter?' do
    it 'returns true for List' do
      expect(mapper.needs_adapter?('List')).to be true
    end

    it 'returns true for Table' do
      expect(mapper.needs_adapter?('Table')).to be true
    end

    it 'returns true for Collection' do
      expect(mapper.needs_adapter?('Collection')).to be true
    end

    it 'returns false for View' do
      expect(mapper.needs_adapter?('View')).to be false
    end
  end

  describe '#is_material_component?' do
    it 'returns true for material components' do
      expect(mapper.is_material_component?('com.google.android.material.card.MaterialCardView')).to be true
    end

    it 'returns false for standard components' do
      expect(mapper.is_material_component?('LinearLayout')).to be false
    end
  end

  describe '#get_layout_params_class' do
    it 'returns RelativeLayout.LayoutParams for RelativeLayout' do
      expect(mapper.get_layout_params_class('RelativeLayout')).to eq('RelativeLayout.LayoutParams')
    end

    it 'returns LinearLayout.LayoutParams for LinearLayout' do
      expect(mapper.get_layout_params_class('LinearLayout')).to eq('LinearLayout.LayoutParams')
    end

    it 'returns FrameLayout.LayoutParams for FrameLayout' do
      expect(mapper.get_layout_params_class('FrameLayout')).to eq('FrameLayout.LayoutParams')
    end

    it 'returns ConstraintLayout.LayoutParams for ConstraintLayout' do
      expect(mapper.get_layout_params_class('ConstraintLayout')).to eq('ConstraintLayout.LayoutParams')
    end
  end

  describe '#get_orientation' do
    it 'returns horizontal for HStack' do
      expect(mapper.get_orientation('HStack')).to eq('horizontal')
    end

    it 'returns vertical for VStack' do
      expect(mapper.get_orientation('VStack')).to eq('vertical')
    end

    it 'returns nil for ZStack' do
      expect(mapper.get_orientation('ZStack')).to be_nil
    end
  end
end
