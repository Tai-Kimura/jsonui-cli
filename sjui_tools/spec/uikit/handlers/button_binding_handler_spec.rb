# frozen_string_literal: true

require 'uikit/handlers/button_binding_handler'

RSpec.describe SjuiTools::UIKit::ButtonBindingHandler do
  let(:binding_content) { [] }
  let(:reset_text_views) { {} }
  let(:reset_constraint_views) { {} }
  let(:handler) { described_class.new(binding_content, reset_text_views, reset_constraint_views) }

  describe '#handle_specific_binding' do
    it 'handles enabled' do
      result = handler.handle_specific_binding('button', 'enabled', 'model.isEnabled')

      expect(result).to be true
      expect(binding_content.join).to include('button.isEnabled = model.isEnabled')
    end

    it 'handles text' do
      result = handler.handle_specific_binding('button', 'text', 'model.title')

      expect(result).to be true
      expect(binding_content.join).to include('AttributedString(model.title)')
      expect(binding_content.join).to include('setTitle(model.title')
    end

    it 'handles fontColor' do
      result = handler.handle_specific_binding('button', 'fontColor', 'UIColor.white')

      expect(result).to be true
      expect(binding_content.join).to include('button.defaultFontColor = UIColor.white')
      expect(binding_content.join).to include('configurationUpdateHandler')
    end

    it 'handles disabledFontColor' do
      result = handler.handle_specific_binding('button', 'disabledFontColor', 'UIColor.gray')

      expect(result).to be true
      expect(binding_content.join).to include('button.disabledFontColor = UIColor.gray')
    end

    it 'handles disabledBackground' do
      result = handler.handle_specific_binding('button', 'disabledBackground', 'UIColor.lightGray')

      expect(result).to be true
      expect(binding_content.join).to include('button.disabledBackgroundColor = UIColor.lightGray')
    end

    it 'returns false for unknown key' do
      result = handler.handle_specific_binding('button', 'unknownKey', 'value')

      expect(result).to be false
    end
  end
end
