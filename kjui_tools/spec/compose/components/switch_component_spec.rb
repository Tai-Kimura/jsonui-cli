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

  # labelPosition was read by nobody in the Compose codegen while the Dynamic
  # runtime honoured it, so the label was always leading.
  describe 'labelPosition' do
    def emit(extra)
      described_class.generate(
        { 'type' => 'Switch', 'labelAttributes' => { 'text' => 'Wifi' }, 'isOn' => true }.merge(extra),
        0, nil, nil
      )
    end

    it 'puts the label before the Switch by default' do
      code = emit({})
      expect(code.index('Text(')).to be < code.index('Switch(')
    end

    it 'puts the label after the Switch for trailing' do
      code = emit('labelPosition' => 'trailing')
      expect(code.index('Switch(')).to be < code.index('Text(')
    end

    it 'treats an unknown value as leading rather than dropping the label' do
      code = emit('labelPosition' => 'sideways')
      expect(code).to include('Text(')
      expect(code.index('Text(')).to be < code.index('Switch(')
    end
  end

  # `label` is the canonical row on Switch, with `text` as its declared alias,
  # and `fontColor` / `fontSize` are declared flat too (51-E). Only the
  # `labelAttributes` bag was ever read, so a Switch declaring a plain `label`
  # drew the control and dropped the text.
  describe 'the flat label spellings' do
    def plain(extra)
      described_class.generate({ 'type' => 'Switch' }.merge(extra), 0, Set.new, nil)
    end

    it 'draws a label declared with the canonical spelling' do
      expect(plain('label' => 'Wi-Fi')).to include('text = "Wi-Fi"')
    end

    it 'draws a label declared with the text alias' do
      expect(plain('text' => 'Wi-Fi')).to include('text = "Wi-Fi"')
    end

    # ["string", "binding"] — the old string literal put `@{...}` on screen.
    it 'resolves a bound label instead of printing the expression' do
      out = plain('label' => '@{name}')
      expect(out).to include('${data.name')
      expect(out).not_to include('@{')
    end

    it 'styles the flat label with the flat fontColor and fontSize' do
      out = plain('label' => 'Wi-Fi', 'fontColor' => '#FF0000', 'fontSize' => 18)
      expect(out).to include('#FF0000')
      expect(out).to include('fontSize = 18.sp')
    end

    # The nested bag outranks the flat spelling, the precedence the dynamic
    # path settled on (KotlinJsonUI 8ed8a16).
    it 'lets the bag outrank the flat spellings' do
      out = plain('label' => 'Flat', 'fontColor' => '#FF0000',
                  'labelAttributes' => { 'text' => 'Bag', 'fontColor' => '#00FF00' })
      expect(out).to include('text = "Bag"')
      expect(out).to include('#00FF00')
      expect(out).not_to include('#FF0000')
    end

    it 'still draws no label when none is declared' do
      expect(plain({})).not_to include('Text(')
    end
  end
  end
end
