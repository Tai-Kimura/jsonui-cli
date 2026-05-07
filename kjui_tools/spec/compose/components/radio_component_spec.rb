# frozen_string_literal: true

require 'compose/components/radio_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'

RSpec.describe KjuiTools::Compose::Components::RadioComponent do
  let(:required_imports) { Set.new }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
    # Clear data definitions before each test
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  describe '.generate' do
    context 'with items array' do
      it 'generates radio group with items' do
        json_data = {
          'type' => 'Radio',
          'items' => ['Option 1', 'Option 2', 'Option 3'],
          'selectedValue' => '@{selectedOption}'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('Column(')
        expect(result).to include('RadioButton(')
        expect(result).to include('Option 1')
        expect(result).to include('Option 2')
        expect(required_imports).to include(:clickable)
      end

      it 'generates radio group with label' do
        json_data = {
          'type' => 'Radio',
          'text' => 'Choose an option',
          'items' => ['A', 'B'],
          'selectedValue' => '@{choice}'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('Choose an option')
      end

      it 'handles fontColor for text' do
        json_data = {
          'type' => 'Radio',
          'items' => ['A', 'B'],
          'selectedValue' => '@{choice}',
          'fontColor' => '#FF0000'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('color =')
      end
    end

    context 'with individual radio item' do
      it 'generates radio item with group' do
        json_data = {
          'type' => 'Radio',
          'group' => 'myGroup',
          'id' => 'option1',
          'text' => 'Option 1'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('Row(')
        expect(result).to include('RadioButton(')
        expect(result).to include('Option 1')
      end

      it 'generates radio item with text only' do
        json_data = {
          'type' => 'Radio',
          'text' => 'Radio Label'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('RadioButton(')
        expect(result).to include('Radio Label')
      end

      it 'generates radio with square icon (checkbox)' do
        json_data = {
          'type' => 'Radio',
          'text' => 'Check this',
          'icon' => 'square',
          'selectedIcon' => 'checkmark.square.fill'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('Checkbox(')
      end

      it 'generates radio with custom icons' do
        json_data = {
          'type' => 'Radio',
          'text' => 'Star this',
          'icon' => 'star',
          'selectedIcon' => 'star.fill'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('IconButton(')
        expect(required_imports).to include(:icon_button)
        expect(required_imports).to include(:icons)
      end

      it 'handles selectedColor for custom icons' do
        json_data = {
          'type' => 'Radio',
          'text' => 'Custom',
          'icon' => 'heart',
          'selectedIcon' => 'heart.fill',
          'selectedColor' => '#FF0000'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('tint =')
      end

      it 'handles fontColor for text' do
        json_data = {
          'type' => 'Radio',
          'text' => 'Colored',
          'fontColor' => '#333333'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('color =')
      end
    end

    context 'with options array' do
      it 'generates radio with static options' do
        json_data = {
          'type' => 'Radio',
          'options' => ['Red', 'Green', 'Blue'],
          'bind' => '@{color}'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('Column(')
        expect(result).to include('RadioButton(')
        expect(result).to include('Red')
        expect(result).to include('Green')
        expect(result).to include('Blue')
      end

      it 'generates radio with hash options' do
        json_data = {
          'type' => 'Radio',
          'options' => [
            { 'value' => '1', 'label' => 'First' },
            { 'value' => '2', 'label' => 'Second' }
          ],
          'bind' => '@{selected}'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('First')
        expect(result).to include('Second')
      end

      it 'generates radio with dynamic options binding' do
        json_data = {
          'type' => 'Radio',
          'options' => '@{availableOptions}',
          'bind' => '@{selectedOption}'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('data.availableOptions.forEach')
      end

      it 'handles onValueChange callback' do
        json_data = {
          'type' => 'Radio',
          'options' => ['A', 'B'],
          'onValueChange' => '@{handleChange}'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('data.handleChange?.invoke()')
      end

      it 'handles selectedColor and unselectedColor' do
        json_data = {
          'type' => 'Radio',
          'options' => ['Yes', 'No'],
          'bind' => '@{answer}',
          'selectedColor' => '#007AFF',
          'unselectedColor' => '#CCCCCC'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('RadioButtonDefaults.colors')
        expect(result).to include('selectedColor')
        expect(result).to include('unselectedColor')
        expect(required_imports).to include(:radio_colors)
      end
    end
  end

  describe '.map_icon_name' do
    it 'maps circle to PanoramaFishEye' do
      result = described_class.send(:map_icon_name, 'circle')
      expect(result).to include('PanoramaFishEye')
    end

    it 'maps checkmark.circle.fill to CheckCircle' do
      result = described_class.send(:map_icon_name, 'checkmark.circle.fill')
      expect(result).to include('CheckCircle')
    end

    it 'maps star to Star' do
      result = described_class.send(:map_icon_name, 'star')
      expect(result).to include('Star')
    end

    it 'maps heart to Favorite' do
      result = described_class.send(:map_icon_name, 'heart')
      expect(result).to include('Favorite')
    end

    it 'returns default for unknown icon' do
      result = described_class.send(:map_icon_name, 'unknown')
      expect(result).to include('Star')
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
  end

  describe 'event handler invocation' do
    it 'generates invoke() without arguments when handler type is () -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onRadioChange' => { 'name' => 'onRadioChange', 'class' => '(() -> Unit)?' }
      }

      json_data = {
        'type' => 'Radio',
        'id' => 'genderRadio',
        'options' => ['Male', 'Female'],
        'bind' => '@{gender}',
        'onValueChange' => '@{onRadioChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onRadioChange?.invoke()')
      expect(result).not_to include('invoke("genderRadio"')
    end

    it 'generates invoke(viewId, value) when handler type is (Event) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onRadioChange' => { 'name' => 'onRadioChange', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'Radio',
        'id' => 'genderRadio',
        'options' => ['Male', 'Female'],
        'bind' => '@{gender}',
        'onValueChange' => '@{onRadioChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onRadioChange?.invoke("genderRadio", "Male")')
      expect(result).to include('data.onRadioChange?.invoke("genderRadio", "Female")')
    end

    it 'generates invoke(viewId, value) when handler type is (String, String) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onRadioChange' => { 'name' => 'onRadioChange', 'class' => '((String, String) -> Unit)?' }
      }

      json_data = {
        'type' => 'Radio',
        'id' => 'sizeRadio',
        'options' => ['Small', 'Large'],
        'onValueChange' => '@{onRadioChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onRadioChange?.invoke("sizeRadio", "Small")')
      expect(result).to include('data.onRadioChange?.invoke("sizeRadio", "Large")')
    end

    it 'includes both viewModel.updateData and handler invocation when both binding and handler exist' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onRadioChange' => { 'name' => 'onRadioChange', 'class' => '((String, String) -> Unit)?' }
      }

      json_data = {
        'type' => 'Radio',
        'id' => 'genderRadio',
        'options' => ['Male', 'Female'],
        'bind' => '@{gender}',
        'onValueChange' => '@{onRadioChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('viewModel.updateData')
      expect(result).to include('data.onRadioChange?.invoke("genderRadio", "Male")')
    end

    it 'uses default radio id when no id specified' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onRadioChange' => { 'name' => 'onRadioChange', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'Radio',
        'options' => ['Yes', 'No'],
        'onValueChange' => '@{onRadioChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onRadioChange?.invoke("radio", "Yes")')
    end
  end
end
