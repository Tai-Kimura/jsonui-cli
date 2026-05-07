# frozen_string_literal: true

require 'uikit/handlers/icon_label_binding_handler'

RSpec.describe SjuiTools::UIKit::IconLabelBindingHandler do
  let(:binding_content) { [] }
  let(:reset_text_views) { {} }
  let(:reset_constraint_views) { {} }
  let(:handler) { described_class.new(binding_content, reset_text_views, reset_constraint_views) }

  describe '#handle_specific_binding' do
    it 'handles text' do
      result = handler.handle_specific_binding('iconLabel', 'text', 'model.labelText')

      expect(result).to be true
      expect(binding_content.join).to include('iconLabel.label.applyAttributedText(model.labelText)')
    end

    it 'handles selected' do
      result = handler.handle_specific_binding('iconLabel', 'selected', 'true')

      expect(result).to be true
      expect(binding_content.join).to include('iconLabel.isSelected = true')
    end

    it 'returns false for unknown key' do
      result = handler.handle_specific_binding('iconLabel', 'unknownKey', 'value')

      expect(result).to be false
    end
  end
end
