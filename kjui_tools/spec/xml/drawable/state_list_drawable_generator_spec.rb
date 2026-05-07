# frozen_string_literal: true

require 'xml/drawable/state_list_drawable_generator'
require 'xml/helpers/resource_resolver'

RSpec.describe DrawableGenerator::StateListDrawableGenerator do
  let(:generator) { described_class.new }
  let(:parent_generator) { double('ParentGenerator') }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
  end

  describe '#generate' do
    it 'returns nil for nil input' do
      expect(generator.generate(nil, parent_generator)).to be_nil
    end

    it 'generates XML header' do
      result = generator.generate({}, parent_generator)
      expect(result).to include('<?xml version="1.0" encoding="utf-8"?>')
    end

    it 'generates selector element' do
      result = generator.generate({}, parent_generator)
      expect(result).to include('<selector xmlns:android="http://schemas.android.com/apk/res/android">')
      expect(result).to include('</selector>')
    end

    it 'always includes default state item' do
      result = generator.generate({}, parent_generator)
      expect(result).to include('<item>')
    end

    context 'disabled state' do
      it 'generates disabled state item' do
        result = generator.generate({ 'disabledBackground' => '#CCCCCC' }, parent_generator)
        expect(result).to include('android:state_enabled="false"')
      end

      it 'handles disabledColor' do
        result = generator.generate({ 'disabledColor' => '#888888' }, parent_generator)
        expect(result).to include('android:state_enabled="false"')
      end
    end

    context 'pressed state' do
      it 'generates pressed state with tapBackground' do
        result = generator.generate({ 'tapBackground' => '#0066FF' }, parent_generator)
        expect(result).to include('android:state_pressed="true"')
      end

      it 'generates pressed state with pressedBackground' do
        result = generator.generate({ 'pressedBackground' => '#0066FF' }, parent_generator)
        expect(result).to include('android:state_pressed="true"')
      end

      it 'handles tapColor' do
        result = generator.generate({ 'tapColor' => '#FFFFFF' }, parent_generator)
        expect(result).to include('android:state_pressed="true"')
      end
    end

    context 'selected state' do
      it 'generates selected state' do
        result = generator.generate({ 'selectedBackground' => '#00FF00' }, parent_generator)
        expect(result).to include('android:state_selected="true"')
      end

      it 'handles selectedColor' do
        result = generator.generate({ 'selectedColor' => '#00FF00' }, parent_generator)
        expect(result).to include('android:state_selected="true"')
      end
    end

    context 'focused state' do
      it 'generates focused state' do
        result = generator.generate({ 'focusedBackground' => '#007AFF' }, parent_generator)
        expect(result).to include('android:state_focused="true"')
      end

      it 'handles focusedColor' do
        result = generator.generate({ 'focusedColor' => '#007AFF' }, parent_generator)
        expect(result).to include('android:state_focused="true"')
      end
    end

    context 'checked state' do
      it 'generates checked state' do
        result = generator.generate({ 'checkedBackground' => '#00FF00' }, parent_generator)
        expect(result).to include('android:state_checked="true"')
      end

      it 'handles checkedColor' do
        result = generator.generate({ 'checkedColor' => '#00FF00' }, parent_generator)
        expect(result).to include('android:state_checked="true"')
      end
    end

    context 'with shape properties' do
      it 'generates shape for corner radius' do
        result = generator.generate({
          'background' => '#FFFFFF',
          'cornerRadius' => 8
        }, parent_generator)
        expect(result).to include('<shape android:shape="rectangle">')
        expect(result).to include('android:radius="8dp"')
      end

      it 'generates shape for border' do
        result = generator.generate({
          'background' => '#FFFFFF',
          'borderWidth' => 2,
          'borderColor' => '#000000'
        }, parent_generator)
        expect(result).to include('<stroke')
        expect(result).to include('android:width="2dp"')
      end
    end

    context 'default state' do
      it 'uses transparent for empty data' do
        result = generator.generate({}, parent_generator)
        expect(result).to include('@android:color/transparent')
      end

      it 'uses background color when provided' do
        result = generator.generate({ 'background' => '#FFFFFF' }, parent_generator)
        expect(result).not_to include('@android:color/transparent')
      end
    end
  end

  describe '#build_state_attributes' do
    it 'returns disabled state attribute' do
      expect(generator.send(:build_state_attributes, 'disabled')).to eq('android:state_enabled="false"')
    end

    it 'returns pressed state attribute' do
      expect(generator.send(:build_state_attributes, 'pressed')).to eq('android:state_pressed="true"')
    end

    it 'returns selected state attribute' do
      expect(generator.send(:build_state_attributes, 'selected')).to eq('android:state_selected="true"')
    end

    it 'returns focused state attribute' do
      expect(generator.send(:build_state_attributes, 'focused')).to eq('android:state_focused="true"')
    end

    it 'returns checked state attribute' do
      expect(generator.send(:build_state_attributes, 'checked')).to eq('android:state_checked="true"')
    end

    it 'returns activated state attribute' do
      expect(generator.send(:build_state_attributes, 'activated')).to eq('android:state_activated="true"')
    end

    it 'returns empty string for unknown state' do
      expect(generator.send(:build_state_attributes, 'unknown')).to eq('')
    end
  end

  describe '#needs_shape?' do
    it 'returns true when cornerRadius is present' do
      expect(generator.send(:needs_shape?, '#FFFFFF', { 'cornerRadius' => 8 })).to be true
    end

    it 'returns true when borderWidth is present' do
      expect(generator.send(:needs_shape?, '#FFFFFF', { 'borderWidth' => 2 })).to be true
    end

    it 'returns true for gradient background' do
      expect(generator.send(:needs_shape?, { 'gradient' => {} }, {})).to be true
    end

    it 'returns false for simple color' do
      expect(generator.send(:needs_shape?, '#FFFFFF', {})).to be false
    end
  end

  describe '#parse_dimension' do
    it 'returns 0dp for nil' do
      expect(generator.send(:parse_dimension, nil)).to eq('0dp')
    end

    it 'returns value as-is if already has unit' do
      expect(generator.send(:parse_dimension, '16dp')).to eq('16dp')
    end

    it 'adds dp to numeric values' do
      expect(generator.send(:parse_dimension, 16)).to eq('16dp')
    end
  end

  describe '#parse_color' do
    it 'returns #000000 for nil' do
      expect(generator.send(:parse_color, nil)).to eq('#000000')
    end

    it 'returns color references as-is' do
      expect(generator.send(:parse_color, '@color/primary')).to eq('@color/primary')
    end

    it 'returns attr references as-is' do
      expect(generator.send(:parse_color, '?attr/colorPrimary')).to eq('?attr/colorPrimary')
    end

    it 'returns transparent for transparent' do
      expect(generator.send(:parse_color, 'transparent')).to eq('#00000000')
    end
  end
end
