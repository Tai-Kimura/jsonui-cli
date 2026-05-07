# frozen_string_literal: true

require 'uikit/handlers/text_view_binding_handler'

RSpec.describe SjuiTools::UIKit::TextViewBindingHandler do
  let(:binding_content) { [] }
  let(:reset_text_views) { {} }
  let(:reset_constraint_views) { {} }
  let(:handler) { described_class.new(binding_content, reset_text_views, reset_constraint_views) }

  describe '#handle_specific_binding' do
    it 'handles enabled' do
      result = handler.handle_specific_binding('textView', 'enabled', 'model.isEditable')

      expect(result).to be true
      expect(binding_content.join).to include('textView?.isEditable = model.isEditable')
    end

    it 'handles text with initialization check' do
      result = handler.handle_specific_binding('textView', 'text', 'model.content')

      expect(result).to be true
      expect(binding_content.join).to include('if !isInitialized')
      expect(binding_content.join).to include('textView?.text = model.content')
    end

    it 'returns false for unknown key' do
      result = handler.handle_specific_binding('textView', 'unknownKey', 'value')

      expect(result).to be false
    end
  end
end
