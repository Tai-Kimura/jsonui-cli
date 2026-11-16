# frozen_string_literal: true

require 'uikit/handlers/select_box_binding_handler'

RSpec.describe SjuiTools::UIKit::SelectBoxBindingHandler do
  let(:binding_content) { [] }
  let(:reset_text_views) { {} }
  let(:reset_constraint_views) { {} }
  let(:handler) { described_class.new(binding_content, reset_text_views, reset_constraint_views) }

  describe '#handle_specific_binding' do
    it 'handles selectedIndex' do
      result = handler.handle_specific_binding('selectBox', 'selectedIndex', 'model.index')

      expect(result).to be true
      expect(binding_content.join).to include('if !isInitialized')
      expect(binding_content.join).to include('selectedIndex')
    end

    it 'handles selectedItem' do
      result = handler.handle_specific_binding('selectBox', 'selectedItem', 'model.item')

      expect(result).to be true
      expect(binding_content.join).to include('firstIndex(where:')
    end

    it 'handles selectedDate' do
      result = handler.handle_specific_binding('selectBox', 'selectedDate', 'model.date')

      expect(result).to be true
      expect(binding_content.join).to include('selectedDate = model.date')
    end

    it 'handles items' do
      result = handler.handle_specific_binding('selectBox', 'items', 'model.options')

      expect(result).to be true
      expect(binding_content.join).to include('selectBox?.items = model.options')
    end

    it 'handles minimumDate' do
      result = handler.handle_specific_binding('selectBox', 'minimumDate', 'model.minDate')

      expect(result).to be true
      expect(binding_content.join).to include('selectBox?.minimumDate = model.minDate')
    end

    it 'handles maximumDate' do
      result = handler.handle_specific_binding('selectBox', 'maximumDate', 'model.maxDate')

      expect(result).to be true
      expect(binding_content.join).to include('selectBox?.maximumDate = model.maxDate')
    end

    it 'returns false for unknown key' do
      result = handler.handle_specific_binding('selectBox', 'unknownKey', 'value')

      expect(result).to be false
    end
  end
end
