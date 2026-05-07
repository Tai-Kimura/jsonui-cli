# frozen_string_literal: true

require 'compose/components/selectbox_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'

RSpec.describe KjuiTools::Compose::Components::SelectBoxComponent do
  let(:required_imports) { Set.new }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
    # Clear data definitions before each test
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  describe '.generate' do
    context 'standard SelectBox' do
      it 'generates basic SelectBox component' do
        json_data = { 'type' => 'SelectBox' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('SelectBox(')
        expect(required_imports).to include(:selectbox_component)
      end

      it 'generates SelectBox with static options array' do
        json_data = {
          'type' => 'SelectBox',
          'options' => ['Option 1', 'Option 2', 'Option 3']
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('options = listOf(')
        expect(result).to include('Option 1')
        expect(result).to include('Option 2')
      end

      it 'generates SelectBox with items array' do
        json_data = {
          'type' => 'SelectBox',
          'items' => ['A', 'B', 'C']
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('options = listOf(')
      end

      it 'generates SelectBox with hash options' do
        json_data = {
          'type' => 'SelectBox',
          'options' => [
            { 'value' => '1', 'label' => 'First' },
            { 'value' => '2', 'label' => 'Second' }
          ]
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('First')
        expect(result).to include('Second')
      end

      it 'generates SelectBox with dynamic options binding' do
        json_data = {
          'type' => 'SelectBox',
          'options' => '@{availableOptions}'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('options = data.availableOptions')
      end

      it 'generates SelectBox with selectedItem binding' do
        json_data = {
          'type' => 'SelectBox',
          'selectedItem' => '@{selectedValue}',
          'options' => ['A', 'B']
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('value = data.selectedValue')
        expect(result).to include('onValueChange')
      end

      it 'generates SelectBox with bind attribute' do
        json_data = {
          'type' => 'SelectBox',
          'bind' => '@{choice}',
          'options' => ['A', 'B']
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('value = data.choice')
      end

      it 'generates SelectBox with hint' do
        json_data = {
          'type' => 'SelectBox',
          'hint' => 'Select an option'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('placeholder = "Select an option"')
      end

      it 'generates SelectBox with placeholder' do
        json_data = {
          'type' => 'SelectBox',
          'placeholder' => 'Choose one'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('placeholder = "Choose one"')
      end

      it 'generates disabled SelectBox' do
        json_data = {
          'type' => 'SelectBox',
          'disabled' => true
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('enabled = false')
      end

      it 'generates SelectBox with enabled false' do
        json_data = {
          'type' => 'SelectBox',
          'enabled' => false
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('enabled = false')
      end

      it 'generates SelectBox with background color' do
        json_data = {
          'type' => 'SelectBox',
          'background' => '#FFFFFF'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('backgroundColor')
      end

      it 'generates SelectBox with borderColor' do
        json_data = {
          'type' => 'SelectBox',
          'borderColor' => '#000000'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('borderColor')
      end

      it 'generates SelectBox with fontColor' do
        json_data = {
          'type' => 'SelectBox',
          'fontColor' => '#333333'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('textColor')
      end

      it 'generates SelectBox with hintColor' do
        json_data = {
          'type' => 'SelectBox',
          'hintColor' => '#999999'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('hintColor')
      end

      it 'generates SelectBox with cornerRadius' do
        json_data = {
          'type' => 'SelectBox',
          'cornerRadius' => 8
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('cornerRadius = 8')
      end

      it 'generates SelectBox with cancelButtonBackgroundColor' do
        json_data = {
          'type' => 'SelectBox',
          'cancelButtonBackgroundColor' => '#FF0000'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('cancelButtonBackgroundColor')
      end

      it 'generates SelectBox with cancelButtonTextColor' do
        json_data = {
          'type' => 'SelectBox',
          'cancelButtonTextColor' => '#FFFFFF'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('cancelButtonTextColor')
      end
    end

    context 'DateSelectBox' do
      it 'generates DateSelectBox for date type' do
        json_data = {
          'type' => 'SelectBox',
          'selectItemType' => 'Date'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('DateSelectBox(')
        expect(required_imports).to include(:date_selectbox_component)
      end

      it 'generates DateSelectBox with datePickerMode' do
        json_data = {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'datePickerMode' => 'date'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('datePickerMode = "date"')
      end

      it 'generates DateSelectBox with datePickerStyle' do
        json_data = {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'datePickerStyle' => 'wheels'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('datePickerStyle = "wheels"')
      end

      it 'generates DateSelectBox with dateFormat' do
        json_data = {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'dateFormat' => 'yyyy-MM-dd'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('dateFormat = "yyyy-MM-dd"')
      end

      it 'generates DateSelectBox with dateStringFormat' do
        json_data = {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'dateStringFormat' => 'MM/dd/yyyy'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('dateFormat = "MM/dd/yyyy"')
      end

      it 'generates DateSelectBox with minuteInterval' do
        json_data = {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'minuteInterval' => 15
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('minuteInterval = 15')
      end

      it 'generates DateSelectBox with minimumDate' do
        json_data = {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'minimumDate' => '2020-01-01'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('minimumDate = "2020-01-01"')
      end

      it 'generates DateSelectBox with maximumDate' do
        json_data = {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'maximumDate' => '2030-12-31'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('maximumDate = "2030-12-31"')
      end

      it 'adds fillMaxWidth for date picker by default' do
        json_data = {
          'type' => 'SelectBox',
          'selectItemType' => 'Date'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.fillMaxWidth()')
      end
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
        'onSelectionChange' => { 'name' => 'onSelectionChange', 'class' => '(() -> Unit)?' }
      }

      json_data = {
        'type' => 'SelectBox',
        'id' => 'countrySelect',
        'selectedItem' => '@{country}',
        'options' => ['USA', 'Japan', 'UK'],
        'onValueChange' => '@{onSelectionChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onSelectionChange?.invoke()')
      expect(result).not_to include('invoke("countrySelect"')
    end

    it 'generates invoke(viewId, value) when handler type is (Event) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onSelectionChange' => { 'name' => 'onSelectionChange', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'SelectBox',
        'id' => 'countrySelect',
        'selectedItem' => '@{country}',
        'options' => ['USA', 'Japan', 'UK'],
        'onValueChange' => '@{onSelectionChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onSelectionChange?.invoke("countrySelect", newValue)')
    end

    it 'generates invoke(viewId, value) when handler type is (String, String) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onSelectionChange' => { 'name' => 'onSelectionChange', 'class' => '((String, String) -> Unit)?' }
      }

      json_data = {
        'type' => 'SelectBox',
        'id' => 'languageSelect',
        'options' => ['English', 'Japanese'],
        'onValueChange' => '@{onSelectionChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onSelectionChange?.invoke("languageSelect", newValue)')
    end

    it 'includes both viewModel.updateData and handler invocation when both binding and handler exist' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onSelectionChange' => { 'name' => 'onSelectionChange', 'class' => '((String, String) -> Unit)?' }
      }

      json_data = {
        'type' => 'SelectBox',
        'id' => 'countrySelect',
        'selectedItem' => '@{country}',
        'options' => ['USA', 'Japan', 'UK'],
        'onValueChange' => '@{onSelectionChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('viewModel.updateData')
      expect(result).to include('data.onSelectionChange?.invoke("countrySelect", newValue)')
    end

    it 'uses default selectbox id when no id specified' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onSelectionChange' => { 'name' => 'onSelectionChange', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'SelectBox',
        'options' => ['A', 'B'],
        'onValueChange' => '@{onSelectionChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onSelectionChange?.invoke("selectbox", newValue)')
    end
  end
end
