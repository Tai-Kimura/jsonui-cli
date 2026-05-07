# frozen_string_literal: true

require 'uikit/handlers/image_binding_handler'

RSpec.describe SjuiTools::UIKit::ImageBindingHandler do
  let(:binding_content) { [] }
  let(:reset_text_views) { {} }
  let(:reset_constraint_views) { {} }
  let(:handler) { described_class.new(binding_content, reset_text_views, reset_constraint_views) }

  describe '#handle_specific_binding' do
    it 'handles srcName' do
      result = handler.handle_specific_binding('imageView', 'srcName', 'model.imageName')

      expect(result).to be true
      expect(binding_content.join).to include('imageView?.image = ')
      expect(binding_content.join).to include('UIImage(named:')
    end

    it 'handles srcName with !! suffix' do
      result = handler.handle_specific_binding('imageView', 'srcName', 'model.imageName!!')

      expect(result).to be true
      expect(binding_content.join).to include('UIImage(named: model.imageName)')
      expect(binding_content.join).not_to include('??')
    end

    it 'handles highlightSrcName' do
      result = handler.handle_specific_binding('imageView', 'highlightSrcName', 'model.highlightImage')

      expect(result).to be true
      expect(binding_content.join).to include('imageView?.highlightedImage = ')
    end

    it 'handles highlightSrcName with !! suffix' do
      result = handler.handle_specific_binding('imageView', 'highlightSrcName', 'model.highlightImage!!')

      expect(result).to be true
      expect(binding_content.join).to include('highlightedImage = UIImage(named: model.highlightImage)')
    end

    it 'handles src' do
      result = handler.handle_specific_binding('imageView', 'src', 'imageObject')

      expect(result).to be true
      expect(binding_content.join).to include('imageView?.image = imageObject')
    end

    it 'handles highlightSrc' do
      result = handler.handle_specific_binding('imageView', 'highlightSrc', 'highlightedImageObject')

      expect(result).to be true
      expect(binding_content.join).to include('imageView?.highlightedImage = highlightedImageObject')
    end

    it 'handles contentMode' do
      result = handler.handle_specific_binding('imageView', 'contentMode', '.scaleAspectFit')

      expect(result).to be true
      expect(binding_content.join).to include('imageView?.contentMode = .scaleAspectFit')
    end

    it 'returns false for unknown key' do
      result = handler.handle_specific_binding('imageView', 'unknownKey', 'value')

      expect(result).to be false
    end
  end
end
