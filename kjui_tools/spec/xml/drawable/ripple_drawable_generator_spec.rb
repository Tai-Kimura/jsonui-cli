# frozen_string_literal: true

require 'xml/drawable/ripple_drawable_generator'
require 'xml/helpers/resource_resolver'

RSpec.describe DrawableGenerator::RippleDrawableGenerator do
  let(:generator) { described_class.new }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
  end

  describe '#generate' do
    it 'returns nil for nil input' do
      expect(generator.generate(nil, 'Button')).to be_nil
    end

    it 'generates XML header' do
      result = generator.generate({}, 'Button')
      expect(result).to include('<?xml version="1.0" encoding="utf-8"?>')
    end

    it 'generates ripple element' do
      result = generator.generate({}, 'Button')
      expect(result).to include('<ripple xmlns:android="http://schemas.android.com/apk/res/android"')
      expect(result).to include('</ripple>')
    end

    context 'ripple color' do
      it 'uses explicit rippleColor' do
        result = generator.generate({ 'rippleColor' => '#FF0000' }, 'Button')
        expect(result).to include('android:color=')
      end

      it 'uses tapBackground as ripple color' do
        result = generator.generate({ 'tapBackground' => '#00FF00' }, 'View')
        expect(result).to include('android:color=')
      end

      it 'uses colorControlHighlight for Button without background' do
        result = generator.generate({}, 'Button')
        expect(result).to include('?attr/colorControlHighlight')
      end

      it 'uses light ripple for dark background' do
        result = generator.generate({ 'background' => '#000000' }, 'Button')
        expect(result).to include('#40FFFFFF')
      end

      it 'uses dark ripple for light background' do
        result = generator.generate({ 'background' => '#FFFFFF' }, 'Button')
        expect(result).to include('#40000000')
      end

      it 'uses colorControlHighlight for Card' do
        result = generator.generate({}, 'Card')
        expect(result).to include('?attr/colorControlHighlight')
      end

      it 'uses colorControlHighlight for ListItem' do
        result = generator.generate({}, 'ListItem')
        expect(result).to include('?attr/colorControlHighlight')
      end

      it 'uses default ripple for other components' do
        result = generator.generate({}, 'View')
        expect(result).to include('#20000000')
      end
    end

    context 'mask content' do
      it 'generates mask for borderless ripples' do
        result = generator.generate({ 'rippleBorderless' => true }, 'Button')
        expect(result).to include('@android:id/mask')
      end

      it 'generates mask for ImageButton' do
        result = generator.generate({}, 'ImageButton')
        expect(result).to include('@android:id/mask')
      end

      it 'generates mask for Button without background' do
        result = generator.generate({}, 'Button')
        expect(result).to include('@android:id/mask')
      end

      it 'includes cornerRadius in mask' do
        result = generator.generate({ 'rippleBorderless' => true, 'cornerRadius' => 8 }, 'Button')
        expect(result).to include('@android:id/mask')
        expect(result).to include('android:radius="8dp"')
      end

      it 'uses color mask without shape' do
        result = generator.generate({ 'rippleBorderless' => true }, 'View')
        expect(result).to include('@android:color/white')
      end
    end

    context 'background content' do
      it 'generates background item for background color' do
        result = generator.generate({ 'background' => '#FFFFFF' }, 'View')
        expect(result).to include('<item>')
      end

      it 'generates shape for cornerRadius' do
        result = generator.generate({ 'background' => '#FFFFFF', 'cornerRadius' => 8 }, 'View')
        expect(result).to include('<shape android:shape="rectangle">')
        expect(result).to include('android:radius="8dp"')
      end

      it 'generates shape for borderWidth' do
        result = generator.generate({
          'background' => '#FFFFFF',
          'borderWidth' => 1,
          'borderColor' => '#000000'
        }, 'View')
        expect(result).to include('<stroke')
        expect(result).to include('android:width="1dp"')
      end

      it 'handles color reference in background' do
        result = generator.generate({ 'background' => '@color/primary' }, 'View')
        expect(result).to include('@color/primary')
      end

      it 'uses transparent for shape without background' do
        result = generator.generate({ 'cornerRadius' => 8 }, 'View')
        expect(result).to include('@android:color/transparent')
      end
    end
  end

  describe '#is_dark_color?' do
    it 'returns true for black' do
      expect(generator.send(:is_dark_color?, '#000000')).to be true
    end

    it 'returns false for white' do
      expect(generator.send(:is_dark_color?, '#FFFFFF')).to be false
    end

    it 'returns true for dark blue' do
      expect(generator.send(:is_dark_color?, '#000066')).to be true
    end

    it 'returns false for light yellow' do
      expect(generator.send(:is_dark_color?, '#FFFF00')).to be false
    end

    it 'handles 8-character hex (with alpha)' do
      expect(generator.send(:is_dark_color?, '#FF000000')).to be true
    end

    it 'handles 3-character hex' do
      expect(generator.send(:is_dark_color?, '#000')).to be true
      expect(generator.send(:is_dark_color?, '#FFF')).to be false
    end

    it 'returns false for non-hex color' do
      expect(generator.send(:is_dark_color?, nil)).to be false
      expect(generator.send(:is_dark_color?, 'red')).to be false
    end
  end

  describe '#needs_mask?' do
    it 'returns true for borderless ripple' do
      expect(generator.send(:needs_mask?, { 'rippleBorderless' => true }, 'View')).to be true
    end

    it 'returns true for ImageButton' do
      expect(generator.send(:needs_mask?, {}, 'ImageButton')).to be true
    end

    it 'returns true for Button without background' do
      expect(generator.send(:needs_mask?, {}, 'Button')).to be true
    end

    it 'returns false for Button with background' do
      expect(generator.send(:needs_mask?, { 'background' => '#FFFFFF' }, 'Button')).to be false
    end

    it 'returns false for regular view' do
      expect(generator.send(:needs_mask?, {}, 'View')).to be false
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
