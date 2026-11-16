# frozen_string_literal: true

require 'swiftui/binding/handlers/toggle_binding_handler'

RSpec.describe SjuiTools::SwiftUI::Binding::ToggleBindingHandler do
  let(:handler) { described_class.new }

  describe '#handle_specific_binding' do
    it 'returns nil for on binding' do
      component = { 'type' => 'Toggle', 'on' => '@{isOn}' }
      result = handler.handle_specific_binding(component, 'on', '@{isOn}')

      expect(result).to be_nil
    end

    it 'returns nil for checked binding' do
      component = { 'type' => 'Toggle', 'checked' => '@{isChecked}' }
      result = handler.handle_specific_binding(component, 'checked', '@{isChecked}')

      expect(result).to be_nil
    end

    it 'handles enabled binding' do
      component = { 'type' => 'Toggle', 'enabled' => '@{isEnabled}' }
      result = handler.handle_specific_binding(component, 'enabled', '@{isEnabled}')

      expect(result).to include('.disabled(!')
    end

    it 'returns nil for unknown key' do
      component = { 'type' => 'Toggle' }
      result = handler.handle_specific_binding(component, 'unknown', '@{value}')

      expect(result).to be_nil
    end
  end

  describe '#get_state_binding' do
    it 'returns binding for on property' do
      component = { 'on' => '@{isOn}' }
      result = handler.get_state_binding(component)

      expect(result).to include('isOn')
    end

    it 'returns binding for checked property' do
      component = { 'checked' => '@{isChecked}' }
      result = handler.get_state_binding(component)

      expect(result).to include('isChecked')
    end

    it 'returns constant binding for static true' do
      component = { 'on' => true }
      result = handler.get_state_binding(component)

      expect(result).to eq('.constant(true)')
    end

    it 'returns constant binding for static false' do
      component = { 'on' => false }
      result = handler.get_state_binding(component)

      expect(result).to eq('.constant(false)')
    end

    it 'returns constant false for nil state' do
      component = {}
      result = handler.get_state_binding(component)

      expect(result).to eq('.constant(false)')
    end
  end

  describe '#get_label' do
    it 'returns binding for label property' do
      component = { 'label' => '@{labelText}' }
      result = handler.get_label(component)

      expect(result).to include('labelText')
    end

    it 'returns binding for text property' do
      component = { 'text' => '@{toggleText}' }
      result = handler.get_label(component)

      expect(result).to include('toggleText')
    end

    it 'returns quoted string for static label' do
      component = { 'label' => 'Enable feature' }
      result = handler.get_label(component)

      expect(result).to eq('"Enable feature"')
    end

    it 'returns empty string for no label' do
      component = {}
      result = handler.get_label(component)

      expect(result).to eq('""')
    end

    it 'prefers label over text' do
      component = { 'label' => 'Label text', 'text' => 'Text content' }
      result = handler.get_label(component)

      expect(result).to eq('"Label text"')
    end
  end
end
