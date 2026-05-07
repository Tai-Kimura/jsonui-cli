# frozen_string_literal: true

require 'compose/components/switch_component'
require 'compose/helpers/resource_resolver'

RSpec.describe KjuiTools::Compose::Components::SwitchComponent do
  let(:required_imports) { Set.new }

  before do
    # Clear data definitions before each test
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  describe '.generate' do
    it 'generates basic Switch component' do
      json_data = { 'type' => 'Switch' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Switch(')
    end

    it 'generates Switch with checked state binding' do
      json_data = { 'type' => 'Switch', 'on' => '@{isEnabled}' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('checked')
    end

    it 'generates Switch with static checked state true' do
      json_data = { 'type' => 'Switch', 'on' => true }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('checked')
    end

    it 'generates Switch with onChange handler' do
      json_data = { 'type' => 'Switch', 'onChange' => 'handleToggle' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('onCheckedChange')
    end

    it 'adds switch_colors import when onTintColor specified' do
      json_data = { 'type' => 'Switch', 'onTintColor' => '#007AFF' }
      described_class.generate(json_data, 0, required_imports)
      expect(required_imports).to include(:switch_colors)
    end
  end

  describe 'event handler invocation' do
    it 'generates invoke() without arguments when handler type is () -> Unit' do
      # Set up data definition with no-argument handler
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onToggle' => { 'name' => 'onToggle', 'class' => '(() -> Unit)?' }
      }

      json_data = {
        'type' => 'Switch',
        'id' => 'mySwitch',
        'isOn' => '@{isEnabled}',
        'onValueChange' => '@{onToggle}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      # Should call invoke() without arguments
      expect(result).to include('data.onToggle?.invoke()')
      expect(result).not_to include('invoke("mySwitch"')
    end

    it 'generates invoke(viewId, value) when handler type is (Event) -> Unit' do
      # Set up data definition with Event handler
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onToggle' => { 'name' => 'onToggle', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'Switch',
        'id' => 'mySwitch',
        'isOn' => '@{isEnabled}',
        'onValueChange' => '@{onToggle}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      # Should call invoke with viewId and value
      expect(result).to include('data.onToggle?.invoke("mySwitch", newValue)')
    end

    it 'generates invoke(viewId, value) when handler type is (String, Boolean) -> Unit' do
      # Set up data definition with tuple handler
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onToggle' => { 'name' => 'onToggle', 'class' => '((String, Boolean) -> Unit)?' }
      }

      json_data = {
        'type' => 'Switch',
        'id' => 'toggleSwitch',
        'isOn' => '@{isEnabled}',
        'onValueChange' => '@{onToggle}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      # Should call invoke with viewId and value
      expect(result).to include('data.onToggle?.invoke("toggleSwitch", newValue)')
    end

    it 'includes both viewModel.updateData and handler invocation when both binding and handler exist' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onToggle' => { 'name' => 'onToggle', 'class' => '((String, Boolean) -> Unit)?' }
      }

      json_data = {
        'type' => 'Switch',
        'id' => 'mySwitch',
        'isOn' => '@{isEnabled}',
        'onValueChange' => '@{onToggle}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      # Should include both updateData and handler invocation
      expect(result).to include('viewModel.updateData')
      expect(result).to include('data.onToggle?.invoke("mySwitch", newValue)')
    end

    it 'uses default switch id when no id specified' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onToggle' => { 'name' => 'onToggle', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'Switch',
        'onValueChange' => '@{onToggle}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      # Should use default 'switch' as viewId
      expect(result).to include('data.onToggle?.invoke("switch", newValue)')
    end
  end
end
