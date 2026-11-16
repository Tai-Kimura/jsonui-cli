# frozen_string_literal: true

require 'swiftui/binding/handlers/button_binding_handler'

RSpec.describe SjuiTools::SwiftUI::Binding::ButtonBindingHandler do
  let(:handler) { described_class.new }

  describe '#handle_specific_binding' do
    it 'returns nil for text binding' do
      component = { 'type' => 'Button', 'text' => '@{buttonText}' }
      result = handler.handle_specific_binding(component, 'text', '@{buttonText}')

      expect(result).to be_nil
    end

    it 'handles enabled binding' do
      component = { 'type' => 'Button', 'enabled' => '@{isEnabled}' }
      result = handler.handle_specific_binding(component, 'enabled', '@{isEnabled}')

      expect(result).to include('.disabled(!')
      expect(result).to include('isEnabled')
    end

    it 'handles fontColor binding' do
      component = { 'type' => 'Button', 'fontColor' => '@{textColor}' }
      result = handler.handle_specific_binding(component, 'fontColor', '@{textColor}')

      expect(result).to include('.foregroundColor(')
      expect(result).to include('textColor')
    end

    it 'returns nil for non-binding enabled' do
      component = { 'type' => 'Button', 'enabled' => true }
      result = handler.handle_specific_binding(component, 'enabled', true)

      expect(result).to be_nil
    end

    it 'returns nil for unknown key' do
      component = { 'type' => 'Button', 'unknown' => '@{value}' }
      result = handler.handle_specific_binding(component, 'unknown', '@{value}')

      expect(result).to be_nil
    end
  end

  describe '#get_button_text' do
    it 'returns binding expression for binding text' do
      component = { 'text' => '@{buttonLabel}' }
      result = handler.get_button_text(component)

      expect(result).to include('buttonLabel')
    end

    it 'returns quoted string for static text' do
      component = { 'text' => 'Click me' }
      result = handler.get_button_text(component)

      expect(result).to eq('"Click me"')
    end

    it 'returns empty string for nil text' do
      component = {}
      result = handler.get_button_text(component)

      expect(result).to eq('""')
    end
  end

  describe '#get_action' do
    it 'returns viewModel action call for onclick' do
      component = { 'onClick' => 'handleTap' }
      result = handler.get_action(component)

      expect(result).to eq('data.handleTap?()')
    end

    it 'returns empty closure for no onclick' do
      component = {}
      result = handler.get_action(component)

      expect(result).to eq('{}')
    end
  end
end
