# frozen_string_literal: true

require 'xml/drawable/shape_drawable_generator'
require 'xml/helpers/resource_resolver'

RSpec.describe DrawableGenerator::ShapeDrawableGenerator do
  let(:generator) { described_class.new }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
  end

  describe '#generate' do
    it 'returns nil for nil input' do
      expect(generator.generate(nil)).to be_nil
    end

    it 'generates XML header' do
      result = generator.generate({})
      expect(result).to include('<?xml version="1.0" encoding="utf-8"?>')
    end

    it 'generates shape element' do
      result = generator.generate({})
      expect(result).to include('<shape xmlns:android="http://schemas.android.com/apk/res/android"')
      expect(result).to include('android:shape="rectangle"')
      expect(result).to include('</shape>')
    end

    context 'with corner radius' do
      it 'adds corners element' do
        result = generator.generate({ 'cornerRadius' => 8 })
        expect(result).to include('<corners android:radius="8dp" />')
      end

      it 'handles radius with dp unit' do
        result = generator.generate({ 'cornerRadius' => '12dp' })
        expect(result).to include('<corners android:radius="12dp" />')
      end
    end

    context 'with background color' do
      it 'adds solid element' do
        result = generator.generate({ 'background' => '#FF0000' })
        expect(result).to include('<solid android:color=')
      end
    end

    context 'with border' do
      it 'adds stroke element for border' do
        result = generator.generate({ 'borderWidth' => 2, 'borderColor' => '#000000' })
        expect(result).to include('<stroke')
        expect(result).to include('android:width="2dp"')
        expect(result).to include('android:color=')
      end

      it 'does not add stroke without borderColor' do
        result = generator.generate({ 'borderWidth' => 2 })
        expect(result).not_to include('<stroke')
      end
    end

    context 'with padding' do
      it 'adds padding element for single value' do
        result = generator.generate({ 'padding' => 16 })
        expect(result).to include('<padding')
        expect(result).to include('android:left="16dp"')
        expect(result).to include('android:top="16dp"')
        expect(result).to include('android:right="16dp"')
        expect(result).to include('android:bottom="16dp"')
      end

      it 'adds padding for individual values' do
        result = generator.generate({
          'paddingLeft' => 8,
          'paddingTop' => 12,
          'paddingRight' => 16,
          'paddingBottom' => 20
        })
        expect(result).to include('android:left="8dp"')
        expect(result).to include('android:top="12dp"')
        expect(result).to include('android:right="16dp"')
        expect(result).to include('android:bottom="20dp"')
      end

      it 'defaults to 0dp for missing individual paddings' do
        result = generator.generate({ 'paddingLeft' => 8 })
        expect(result).to include('android:left="8dp"')
        expect(result).to include('android:top="0dp"')
      end
    end

    context 'with gradient' do
      it 'generates linear gradient' do
        result = generator.generate({
          'gradient' => {
            'type' => 'linear',
            'startColor' => '#FF0000',
            'endColor' => '#0000FF'
          }
        })
        expect(result).to include('<gradient')
        expect(result).to include('android:type="linear"')
        expect(result).to include('android:startColor=')
        expect(result).to include('android:endColor=')
      end

      it 'generates radial gradient' do
        result = generator.generate({
          'gradient' => {
            'type' => 'radial',
            'startColor' => '#FF0000',
            'endColor' => '#0000FF',
            'radius' => 100
          }
        })
        expect(result).to include('android:type="radial"')
        expect(result).to include('android:gradientRadius=')
        expect(result).to include('android:centerX=')
        expect(result).to include('android:centerY=')
      end

      it 'generates sweep gradient' do
        result = generator.generate({
          'gradient' => { 'type' => 'sweep' }
        })
        expect(result).to include('android:type="sweep"')
      end

      it 'includes center color when provided' do
        result = generator.generate({
          'gradient' => {
            'type' => 'linear',
            'startColor' => '#FF0000',
            'centerColor' => '#00FF00',
            'endColor' => '#0000FF'
          }
        })
        expect(result).to include('android:centerColor=')
      end

      it 'uses angle for linear gradient' do
        result = generator.generate({
          'gradient' => { 'type' => 'linear', 'angle' => 45 }
        })
        expect(result).to include('android:angle="45"')
      end
    end

    context 'with gradient and border (layered shape)' do
      it 'generates layer-list' do
        result = generator.generate({
          'gradient' => { 'type' => 'linear', 'startColor' => '#FF0000', 'endColor' => '#0000FF' },
          'borderWidth' => 2,
          'borderColor' => '#000000'
        })
        expect(result).to include('<layer-list xmlns:android=')
        expect(result).to include('</layer-list>')
        expect(result).to include('<item>')
      end

      it 'includes corner radius in both layers' do
        result = generator.generate({
          'gradient' => { 'type' => 'linear' },
          'borderWidth' => 1,
          'borderColor' => '#000000',
          'cornerRadius' => 8
        })
        expect(result.scan(/android:radius="8dp"/).count).to eq(2)
      end
    end
  end

  describe '#parse_dimension' do
    it 'returns 0dp for nil' do
      expect(generator.send(:parse_dimension, nil)).to eq('0dp')
    end

    it 'returns value as-is if already has unit' do
      expect(generator.send(:parse_dimension, '16dp')).to eq('16dp')
      expect(generator.send(:parse_dimension, '14sp')).to eq('14sp')
      expect(generator.send(:parse_dimension, '10px')).to eq('10px')
    end

    it 'adds dp to numeric values' do
      expect(generator.send(:parse_dimension, 16)).to eq('16dp')
      expect(generator.send(:parse_dimension, '24')).to eq('24dp')
    end
  end

  describe '#parse_color' do
    it 'returns #000000 for nil' do
      expect(generator.send(:parse_color, nil)).to eq('#000000')
    end

    it 'returns color references as-is' do
      expect(generator.send(:parse_color, '@color/primary')).to eq('@color/primary')
    end

    it 'returns transparent for transparent' do
      expect(generator.send(:parse_color, 'transparent')).to eq('#00000000')
    end
  end
end
