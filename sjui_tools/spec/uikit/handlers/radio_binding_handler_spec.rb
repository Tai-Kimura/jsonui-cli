# frozen_string_literal: true

require 'uikit/handlers/radio_binding_handler'

RSpec.describe SjuiTools::UIKit::RadioBindingHandler do
  let(:binding_content) { [] }
  let(:reset_text_views) { {} }
  let(:reset_constraint_views) { {} }
  let(:handler) { described_class.new(binding_content, reset_text_views, reset_constraint_views) }

  describe '#handle_specific_binding' do
    it 'handles check' do
      result = handler.handle_specific_binding('radioButton', 'check', 'true')

      expect(result).to be true
      expect(binding_content.join).to include('radioButton?.onCheck()')
    end

    it 'returns false for unknown key' do
      result = handler.handle_specific_binding('radioButton', 'unknownKey', 'value')

      expect(result).to be false
    end
  end
end
