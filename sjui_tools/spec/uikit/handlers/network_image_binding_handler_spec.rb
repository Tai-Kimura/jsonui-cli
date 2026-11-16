# frozen_string_literal: true

require 'uikit/handlers/network_image_binding_handler'

RSpec.describe SjuiTools::UIKit::NetworkImageBindingHandler do
  let(:binding_content) { [] }
  let(:reset_text_views) { {} }
  let(:reset_constraint_views) { {} }
  let(:handler) { described_class.new(binding_content, reset_text_views, reset_constraint_views) }

  describe '#handle_specific_binding' do
    it 'handles url' do
      result = handler.handle_specific_binding('imageView', 'url', 'model.imageUrl')

      expect(result).to be true
      # The view accessor is optional-chained (imageView?) in generated UIKit code.
      expect(binding_content.join).to include('imageView?.setImageURL(string:')
    end

    it 'handles url with !! suffix' do
      result = handler.handle_specific_binding('imageView', 'url', 'model.imageUrl!!')

      expect(result).to be true
      expect(binding_content.join).to include('setImageURL(string: model.imageUrl')
      expect(binding_content.join).not_to include('??')
    end

    it 'handles contentMode' do
      result = handler.handle_specific_binding('imageView', 'contentMode', '.scaleAspectFill')

      expect(result).to be true
      expect(binding_content.join).to include('imageView?.contentMode = .scaleAspectFill')
    end

    it 'returns false for unknown key' do
      result = handler.handle_specific_binding('imageView', 'unknownKey', 'value')

      expect(result).to be false
    end
  end
end

RSpec.describe SjuiTools::UIKit::CircleImageBindingHandler do
  it 'is aliased to NetworkImageBindingHandler' do
    expect(described_class).to eq(SjuiTools::UIKit::NetworkImageBindingHandler)
  end
end
