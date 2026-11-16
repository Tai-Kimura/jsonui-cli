# frozen_string_literal: true

require 'uikit/handlers/switch_binding_handler'

RSpec.describe SjuiTools::UIKit::SwitchBindingHandler do
  let(:binding_content) { [] }
  let(:reset_text_views) { {} }
  let(:reset_constraint_views) { {} }
  let(:handler) { described_class.new(binding_content, reset_text_views, reset_constraint_views) }

  describe '#handle_specific_binding' do
    it 'handles on' do
      result = handler.handle_specific_binding('switchView', 'on', 'model.isOn')

      expect(result).to be true
      expect(binding_content.join).to include('switchView?.isOn = model.isOn')
    end

    it 'handles enabled' do
      result = handler.handle_specific_binding('switchView', 'enabled', 'model.isEnabled')

      expect(result).to be true
      expect(binding_content.join).to include('switchView?.isEnabled = model.isEnabled')
    end

    it 'returns false for unknown key' do
      result = handler.handle_specific_binding('switchView', 'unknownKey', 'value')

      expect(result).to be false
    end
  end
end
