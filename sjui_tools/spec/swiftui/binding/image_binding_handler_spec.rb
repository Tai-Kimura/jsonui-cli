# frozen_string_literal: true

require 'swiftui/binding/handlers/image_binding_handler'

RSpec.describe SjuiTools::SwiftUI::Binding::ImageBindingHandler do
  let(:handler) { described_class.new }

  describe '#handle_specific_binding' do
    it 'returns nil for srcName binding' do
      component = { 'type' => 'Image', 'srcName' => '@{imageName}' }
      result = handler.handle_specific_binding(component, 'srcName', '@{imageName}')

      expect(result).to be_nil
    end

    it 'returns nil for src binding' do
      component = { 'type' => 'Image', 'src' => '@{imageSrc}' }
      result = handler.handle_specific_binding(component, 'src', '@{imageSrc}')

      expect(result).to be_nil
    end

    it 'leaves contentMode to the converter (library seam owns the bound form)' do
      component = { 'type' => 'Image', 'contentMode' => '@{mode}' }
      result = handler.handle_specific_binding(component, 'contentMode', '@{mode}')

      # The ternary that lived here collapsed fifteen declared values to two
      # and read canonical fill (stretch = ABSENCE of aspectRatio) as
      # SwiftUI's aspect-fill crop (run 5, Image_contentMode__binding d=29).
      expect(result).to be_nil
    end

    it 'returns nil for unknown key' do
      component = { 'type' => 'Image' }
      result = handler.handle_specific_binding(component, 'unknown', '@{value}')

      expect(result).to be_nil
    end
  end

  describe '#get_image_source' do
    it 'returns binding for srcName binding' do
      component = { 'srcName' => '@{dynamicImage}' }
      result = handler.get_image_source(component)

      expect(result).to include('dynamicImage')
    end

    it 'returns binding for src binding' do
      component = { 'src' => '@{imageSource}' }
      result = handler.get_image_source(component)

      expect(result).to include('imageSource')
    end

    it 'returns quoted string for static srcName' do
      component = { 'srcName' => 'my_image' }
      result = handler.get_image_source(component)

      expect(result).to eq('"my_image"')
    end

    it 'prefers srcName over src' do
      component = { 'srcName' => 'preferred', 'src' => 'fallback' }
      result = handler.get_image_source(component)

      expect(result).to eq('"preferred"')
    end

    it 'returns placeholder for no source' do
      component = {}
      result = handler.get_image_source(component)

      expect(result).to eq('"placeholder"')
    end
  end

  describe '#is_system_image?' do
    it 'returns true for systemImage true' do
      component = { 'systemImage' => true }
      expect(handler.is_system_image?(component)).to be true
    end

    it 'returns true for isSystemImage true' do
      component = { 'isSystemImage' => true }
      expect(handler.is_system_image?(component)).to be true
    end

    it 'returns false for systemImage false' do
      component = { 'systemImage' => false }
      expect(handler.is_system_image?(component)).to be false
    end

    it 'returns false for no system image flag' do
      component = {}
      expect(handler.is_system_image?(component)).to be false
    end
  end
end
