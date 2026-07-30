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

# renderingMode: `template` means "take the tint, ignore the asset's own
# colours" — a ColorFilter here, `.renderingMode(.template)` on iOS.
RSpec.describe KjuiTools::Compose::Components::ImageComponent, 'renderingMode' do
  let(:required_imports) { Set.new }

  def image(extra)
    described_class.generate({ 'type' => 'Image', 'src' => 'logo' }.merge(extra), 0, required_imports)
  end

  # Compose's stand-in for "the current foreground colour", which is what a
  # template image takes on iOS.
  it 'tints with the content colour when no tint is given' do
    expect(image('renderingMode' => 'template'))
      .to include('colorFilter = ColorFilter.tint(LocalContentColor.current)')
    expect(required_imports).to include(:color_filter, :local_content_color)
  end

  it 'tints with the given colour' do
    expect(image('renderingMode' => 'template', 'tintColor' => '#FF0000'))
      .to match(/colorFilter = ColorFilter\.tint\(Color\(.*FF0000/)
  end

  # `original` says the opposite, so it suppresses a tint that would otherwise
  # apply.
  it 'suppresses a tint for original' do
    expect(image('renderingMode' => 'original', 'tintColor' => '#FF0000')).not_to include('colorFilter')
  end

  it 'still tints without a renderingMode' do
    expect(image('tintColor' => '#FF0000')).to include('ColorFilter.tint(')
  end

  it 'emits nothing when neither is set' do
    expect(image({})).not_to include('colorFilter')
  end
end
