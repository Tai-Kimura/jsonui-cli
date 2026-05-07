# frozen_string_literal: true

require 'compose/components/image_component'
require 'compose/helpers/modifier_builder'

RSpec.describe KjuiTools::Compose::Components::ImageComponent do
  let(:required_imports) { Set.new }

  describe '.generate' do
    it 'generates basic Image component' do
      json_data = { 'type' => 'Image', 'src' => 'icon_home' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Image(')
      expect(result).to include('painterResource')
      expect(result).to include('icon_home')
    end

    it 'generates Image with size' do
      json_data = { 'type' => 'Image', 'src' => 'icon_home', 'size' => 48 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.size(48.dp)')
    end

    it 'generates Image with width and height' do
      json_data = { 'type' => 'Image', 'src' => 'icon_home', 'width' => 100, 'height' => 50 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.size(100.dp, 50.dp)')
    end

    it 'generates Image with contentMode aspectFill' do
      json_data = { 'type' => 'Image', 'src' => 'icon_home', 'contentMode' => 'aspectFill' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('contentScale = ContentScale.Crop')
      expect(required_imports).to include(:content_scale)
    end

    it 'generates Image with contentMode aspectFit' do
      json_data = { 'type' => 'Image', 'src' => 'icon_home', 'contentMode' => 'aspectFit' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('contentScale = ContentScale.Fit')
    end

    it 'generates Image with contentMode center' do
      json_data = { 'type' => 'Image', 'src' => 'icon_home', 'contentMode' => 'center' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('contentScale = ContentScale.None')
    end

    it 'generates Image with contentDescription' do
      json_data = { 'type' => 'Image', 'src' => 'icon_home', 'contentDescription' => 'Home icon' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('contentDescription = "Home icon"')
    end

    it 'adds required imports' do
      json_data = { 'type' => 'Image', 'src' => 'icon_home' }
      described_class.generate(json_data, 0, required_imports)
      expect(required_imports).to include(:image)
      expect(required_imports).to include(:painter_resource)
      expect(required_imports).to include(:r_class)
    end

    it 'uses placeholder when no src provided' do
      json_data = { 'type' => 'Image' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('placeholder')
    end
  end
end
