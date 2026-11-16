# frozen_string_literal: true

require 'uikit/handlers/scroll_binding_handler'

RSpec.describe SjuiTools::UIKit::ScrollBindingHandler do
  let(:binding_content) { [] }
  let(:reset_text_views) { {} }
  let(:reset_constraint_views) { {} }
  let(:handler) { described_class.new(binding_content, reset_text_views, reset_constraint_views) }

  describe '#handle_specific_binding' do
    it 'handles scrollEnabled' do
      result = handler.handle_specific_binding('scrollView', 'scrollEnabled', 'model.canScroll')

      expect(result).to be true
      expect(binding_content.join).to include('scrollView?.isScrollEnabled = model.canScroll')
    end

    it 'handles maxZoom' do
      result = handler.handle_specific_binding('scrollView', 'maxZoom', '3.0')

      expect(result).to be true
      expect(binding_content.join).to include('scrollView?.maximumZoomScale = 3.0')
    end

    it 'handles minZoom' do
      result = handler.handle_specific_binding('scrollView', 'minZoom', '0.5')

      expect(result).to be true
      expect(binding_content.join).to include('scrollView?.minimumZoomScale = 0.5')
    end

    it 'returns false for unknown key' do
      result = handler.handle_specific_binding('scrollView', 'unknownKey', 'value')

      expect(result).to be false
    end
  end
end
