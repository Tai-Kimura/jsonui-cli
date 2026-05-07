# frozen_string_literal: true

require 'swiftui/views/slider_converter'

RSpec.describe SjuiTools::SwiftUI::Views::SliderConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'with basic slider' do
      let(:component) do
        {
          'type' => 'Slider',
          'minimumValue' => 0,
          'maximumValue' => 100,
          'value' => 50
        }
      end

      it 'generates Slider' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Slider(')
        expect(code).to include('in: 0...100')
      end
    end

    context 'with binding value' do
      let(:component) do
        {
          'type' => 'Slider',
          'minimumValue' => 0,
          'maximumValue' => 1,
          'value' => '@{volume}'
        }
      end

      it 'uses viewModel.data binding' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('$data.volume')
      end
    end

    context 'with range array' do
      let(:component) do
        {
          'type' => 'Slider',
          'range' => [10, 200]
        }
      end

      it 'uses range array values' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('in: 10...200')
      end
    end

    context 'with tintColor' do
      let(:component) do
        {
          'type' => 'Slider',
          'tintColor' => '#34C759'
        }
      end

      it 'adds accentColor modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.accentColor(')
      end
    end

    context 'with disabled state' do
      let(:component) do
        {
          'type' => 'Slider',
          'enabled' => false
        }
      end

      it 'adds disabled modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.disabled(true)')
      end
    end

    context 'with default values' do
      let(:component) do
        {
          'type' => 'Slider'
        }
      end

      it 'uses default 0...1 range' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('in: 0...1')
      end
    end

    context 'with id' do
      let(:component) do
        {
          'type' => 'Slider',
          'id' => 'volumeSlider'
        }
      end

      it 'creates state variable with sanitized id' do
        converter = described_class.new(component)
        converter.convert

        expect(converter.state_variables).not_to be_empty
        expect(converter.state_variables.first).to include('sliderValuevolumeSlider')
      end
    end
  end

  describe 'event handler invocation' do
    before do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {}
    end

    it 'generates onValueChange handler with onChange modifier' do
      component = {
        'type' => 'Slider',
        'id' => 'volumeSlider',
        'value' => '@{volume}',
        'onValueChange' => '@{onVolumeChange}'
      }

      converter = described_class.new(component)
      code = converter.convert

      expect(code).to include('.onChange(of: data.volume)')
      expect(code).to include('data.onVolumeChange?()')
    end

    it 'generates invoke(viewId, value) when handler type is (String, Double) -> Void' do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
        'onVolumeChange' => { 'name' => 'onVolumeChange', 'class' => '((String, Double) -> Void)?' }
      }

      component = {
        'type' => 'Slider',
        'id' => 'volumeSlider',
        'value' => '@{volume}',
        'onValueChange' => '@{onVolumeChange}'
      }

      converter = described_class.new(component)
      code = converter.convert

      expect(code).to include('data.onVolumeChange?("volumeSlider", newValue)')
    end

    it 'supports legacy onValueChanged attribute' do
      component = {
        'type' => 'Slider',
        'id' => 'slider',
        'value' => '@{sliderValue}',
        'onValueChanged' => '@{onSliderChange}'
      }

      converter = described_class.new(component)
      code = converter.convert

      expect(code).to include('.onChange(of: data.sliderValue)')
      expect(code).to include('data.onSliderChange?()')
    end
  end
end
