# frozen_string_literal: true

require 'compose/components/slider_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'

RSpec.describe KjuiTools::Compose::Components::SliderComponent do
  let(:required_imports) { Set.new }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
    # Clear data definitions before each test
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  describe '.generate' do
    it 'generates basic Slider component' do
      json_data = { 'type' => 'Slider' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Slider(')
      expect(result).to include('value = 0f')
    end

    it 'generates Slider with value' do
      json_data = { 'type' => 'Slider', 'value' => 50 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('value = 50f')
    end

    it 'generates Slider with value data binding' do
      json_data = { 'type' => 'Slider', 'value' => '@{sliderValue}' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('value = data.sliderValue.toFloat()')
      expect(result).to include('onValueChange = { newValue -> viewModel.updateData(mapOf("sliderValue" to newValue.toDouble()))')
    end

    it 'generates Slider with bind attribute' do
      json_data = { 'type' => 'Slider', 'bind' => '@{volume}' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('value = data.volume.toFloat()')
      expect(result).to include('updateData(mapOf("volume"')
    end

    it 'generates Slider with onValueChange handler (no data definition)' do
      json_data = { 'type' => 'Slider', 'onValueChange' => '@{handleSliderChange}' }
      result = described_class.generate(json_data, 0, required_imports)
      # When no data definition, defaults to invoke() without arguments
      expect(result).to include('data.handleSliderChange?.invoke()')
    end

    it 'generates Slider with empty onValueChange when no handler' do
      json_data = { 'type' => 'Slider' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('onValueChange = { }')
    end

    it 'generates Slider with default valueRange' do
      json_data = { 'type' => 'Slider' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('valueRange = 0f..100f')
    end

    it 'generates Slider with minimumValue and maximumValue' do
      json_data = { 'type' => 'Slider', 'minimumValue' => 10, 'maximumValue' => 200 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('valueRange = 10f..200f')
    end

    it 'generates Slider with min and max' do
      json_data = { 'type' => 'Slider', 'min' => 0, 'max' => 50 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('valueRange = 0f..50f')
    end

    it 'generates Slider with step' do
      json_data = { 'type' => 'Slider', 'min' => 0, 'max' => 100, 'step' => 10 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('steps = 9')
    end

    it 'does not add steps when step is 0' do
      json_data = { 'type' => 'Slider', 'step' => 0 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).not_to include('steps =')
    end

    it 'generates Slider with width' do
      json_data = { 'type' => 'Slider', 'width' => 200 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.width(200.dp)')
    end

    it 'generates Slider with height' do
      json_data = { 'type' => 'Slider', 'height' => 50 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.height(50.dp)')
    end

    it 'generates Slider with thumbTintColor' do
      json_data = { 'type' => 'Slider', 'thumbTintColor' => '#007AFF' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('colors = SliderDefaults.colors(')
      expect(result).to include('thumbColor =')
      expect(required_imports).to include(:slider_colors)
    end

    it 'generates Slider with minimumTrackTintColor' do
      json_data = { 'type' => 'Slider', 'minimumTrackTintColor' => '#00FF00' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('activeTrackColor =')
    end

    it 'generates Slider with maximumTrackTintColor' do
      json_data = { 'type' => 'Slider', 'maximumTrackTintColor' => '#CCCCCC' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('inactiveTrackColor =')
    end

    it 'generates Slider with all color options' do
      json_data = {
        'type' => 'Slider',
        'thumbTintColor' => '#007AFF',
        'minimumTrackTintColor' => '#00FF00',
        'maximumTrackTintColor' => '#CCCCCC'
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('thumbColor =')
      expect(result).to include('activeTrackColor =')
      expect(result).to include('inactiveTrackColor =')
    end

    it 'generates Slider with enabled true' do
      json_data = { 'type' => 'Slider', 'enabled' => true }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('enabled = true')
    end

    it 'generates Slider with enabled false' do
      json_data = { 'type' => 'Slider', 'enabled' => false }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('enabled = false')
    end

    it 'generates Slider with enabled data binding' do
      json_data = { 'type' => 'Slider', 'enabled' => '@{isEnabled}' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('enabled = data.isEnabled')
    end

    it 'generates Slider with padding' do
      json_data = { 'type' => 'Slider', 'padding' => 16 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('modifier = Modifier')
    end

    it 'generates Slider with margins' do
      json_data = { 'type' => 'Slider', 'margins' => [10, 20] }
      result = described_class.generate(json_data, 0, required_imports)
      # Slider with margins still generates
      expect(result).to include('Slider(')
    end
  end

  describe '.indent' do
    it 'returns text unchanged for level 0' do
      result = described_class.send(:indent, 'text', 0)
      expect(result).to eq('text')
    end

    it 'adds indentation for level 1' do
      result = described_class.send(:indent, 'text', 1)
      expect(result).to eq('    text')
    end

    it 'handles multi-line text' do
      result = described_class.send(:indent, "line1\nline2", 1)
      expect(result).to eq("    line1\n    line2")
    end
  end

  describe 'event handler invocation' do
    it 'generates invoke() without arguments when handler type is () -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onSliderChange' => { 'name' => 'onSliderChange', 'class' => '(() -> Unit)?' }
      }

      json_data = {
        'type' => 'Slider',
        'id' => 'volumeSlider',
        'value' => '@{volume}',
        'onValueChange' => '@{onSliderChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onSliderChange?.invoke()')
      expect(result).not_to include('invoke("volumeSlider"')
    end

    it 'generates invoke(viewId, value) when handler type is (Event) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onSliderChange' => { 'name' => 'onSliderChange', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'Slider',
        'id' => 'volumeSlider',
        'value' => '@{volume}',
        'onValueChange' => '@{onSliderChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onSliderChange?.invoke("volumeSlider", it)')
    end

    it 'generates invoke(viewId, value) when handler type is (String, Float) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onSliderChange' => { 'name' => 'onSliderChange', 'class' => '((String, Float) -> Unit)?' }
      }

      json_data = {
        'type' => 'Slider',
        'id' => 'brightnessSlider',
        'onValueChange' => '@{onSliderChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onSliderChange?.invoke("brightnessSlider", it)')
    end

    it 'includes both viewModel.updateData and handler invocation when both binding and handler exist' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onSliderChange' => { 'name' => 'onSliderChange', 'class' => '((String, Float) -> Unit)?' }
      }

      json_data = {
        'type' => 'Slider',
        'id' => 'volumeSlider',
        'value' => '@{volume}',
        'onValueChange' => '@{onSliderChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('viewModel.updateData')
      expect(result).to include('data.onSliderChange?.invoke("volumeSlider", it)')
    end

    it 'uses default slider id when no id specified' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onSliderChange' => { 'name' => 'onSliderChange', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'Slider',
        'onValueChange' => '@{onSliderChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onSliderChange?.invoke("slider", it)')
    end
  end
end
