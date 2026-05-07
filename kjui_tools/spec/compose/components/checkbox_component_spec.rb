# frozen_string_literal: true

require 'compose/components/checkbox_component'
require 'compose/helpers/resource_resolver'

RSpec.describe KjuiTools::Compose::Components::CheckboxComponent do
  let(:required_imports) { Set.new }

  before do
    # Clear data definitions before each test
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  describe '.generate' do
    it 'generates basic Checkbox component' do
      json_data = { 'type' => 'Checkbox' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Checkbox(')
    end

    it 'generates Checkbox with checked state' do
      json_data = { 'type' => 'Checkbox', 'checked' => true }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('checked')
    end

    it 'generates Checkbox with binding' do
      json_data = { 'type' => 'Checkbox', 'checked' => '@{isSelected}' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('checked')
    end

    it 'generates Checkbox with onChange handler' do
      json_data = { 'type' => 'Checkbox', 'onChange' => 'handleCheck' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('onCheckedChange')
    end

    it 'adds checkbox_colors import when checkColor specified' do
      json_data = { 'type' => 'Checkbox', 'checkColor' => '#007AFF' }
      described_class.generate(json_data, 0, required_imports)
      expect(required_imports).to include(:checkbox_colors)
    end
  end

  describe 'event handler invocation' do
    it 'generates invoke() without arguments when handler type is () -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onCheck' => { 'name' => 'onCheck', 'class' => '(() -> Unit)?' }
      }

      json_data = {
        'type' => 'Checkbox',
        'id' => 'myCheckbox',
        'checked' => '@{isSelected}',
        'onValueChange' => '@{onCheck}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onCheck?.invoke()')
      expect(result).not_to include('invoke("myCheckbox"')
    end

    it 'generates invoke(viewId, value) when handler type is (Event) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onCheck' => { 'name' => 'onCheck', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'Checkbox',
        'id' => 'myCheckbox',
        'checked' => '@{isSelected}',
        'onValueChange' => '@{onCheck}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onCheck?.invoke("myCheckbox", it)')
    end

    it 'generates invoke(viewId, value) when handler type is (String, Boolean) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onCheck' => { 'name' => 'onCheck', 'class' => '((String, Boolean) -> Unit)?' }
      }

      json_data = {
        'type' => 'Checkbox',
        'id' => 'termsCheckbox',
        'onValueChange' => '@{onCheck}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onCheck?.invoke("termsCheckbox", it)')
    end

    it 'includes both viewModel.updateData and handler invocation when both binding and handler exist' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onCheck' => { 'name' => 'onCheck', 'class' => '((String, Boolean) -> Unit)?' }
      }

      json_data = {
        'type' => 'Checkbox',
        'id' => 'myCheckbox',
        'checked' => '@{isSelected}',
        'onValueChange' => '@{onCheck}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('viewModel.updateData')
      expect(result).to include('data.onCheck?.invoke("myCheckbox", it)')
    end

    it 'uses default checkbox id when no id specified' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onCheck' => { 'name' => 'onCheck', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'Checkbox',
        'onValueChange' => '@{onCheck}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onCheck?.invoke("checkbox", it)')
    end
  end
end
