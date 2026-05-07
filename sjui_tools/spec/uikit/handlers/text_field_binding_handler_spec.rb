# frozen_string_literal: true

require 'uikit/handlers/text_field_binding_handler'

RSpec.describe SjuiTools::UIKit::TextFieldBindingHandler do
  let(:binding_content) { [] }
  let(:reset_text_views) { {} }
  let(:reset_constraint_views) { {} }
  let(:handler) { described_class.new(binding_content, reset_text_views, reset_constraint_views) }

  describe '#handle_specific_binding' do
    it 'handles enabled' do
      result = handler.handle_specific_binding('textField', 'enabled', 'model.isEnabled')

      expect(result).to be true
      expect(binding_content.join).to include('textField?.isEnabled = model.isEnabled')
    end

    it 'handles text with initialization check' do
      result = handler.handle_specific_binding('textField', 'text', 'model.value')

      expect(result).to be true
      expect(binding_content.join).to include('if !isInitialized')
      expect(binding_content.join).to include('textField?.text = model.value')
    end

    it 'handles secure' do
      result = handler.handle_specific_binding('textField', 'secure', 'true')

      expect(result).to be true
      expect(binding_content.join).to include('textField?.isSecureTextEntry = true')
    end

    it 'handles contentType' do
      result = handler.handle_specific_binding('textField', 'contentType', '.password')

      expect(result).to be true
      expect(binding_content.join).to include('textField?.textContentType = .password')
    end

    it 'returns false for unknown key' do
      result = handler.handle_specific_binding('textField', 'unknownKey', 'value')

      expect(result).to be false
    end
  end
end
