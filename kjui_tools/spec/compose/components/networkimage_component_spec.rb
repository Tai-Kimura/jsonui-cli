# frozen_string_literal: true

require 'compose/components/networkimage_component'
require 'compose/helpers/modifier_builder'

RSpec.describe KjuiTools::Compose::Components::NetworkImageComponent do
  let(:required_imports) { Set.new }

  describe '.generate' do
    it 'generates network image component' do
      json_data = { 'type' => 'NetworkImage', 'url' => 'https://example.com/image.jpg' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result.to_s).to match(/AsyncImage|Image/)
    end

    it 'handles url binding' do
      json_data = { 'type' => 'NetworkImage', 'url' => '@{imageUrl}' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('data.imageUrl')
    end

    it 'generates with placeholder' do
      json_data = { 'type' => 'NetworkImage', 'url' => 'https://example.com/image.jpg', 'placeholder' => 'loading' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).not_to be_nil
    end

    it 'generates with size' do
      json_data = { 'type' => 'NetworkImage', 'url' => 'https://example.com/image.jpg', 'width' => 100, 'height' => 100 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Modifier')
    end
  end

  # Each Coil slot carries ONLY the images the ruling puts in its own state
  # (attribute_semantics.json#networkImage; plan 49 #19). `fallback` is the
  # no-src slot and takes defaultImage alone — it used to end in
  # `|| errorImage || placeholder`, which made a state image appear outside
  # its state. Every NetworkImage conformance fixture is no-src, so that tail
  # was what the whole family actually rendered.
  describe 'state images' do
    def generate(attrs)
      described_class.generate({ 'type' => 'NetworkImage' }.merge(attrs), 0, Set.new)
    end

    it 'gives the no-src slot defaultImage and nothing else' do
      result = generate('defaultImage' => 'fallback_asset')
      expect(result).to include('fallback = painterResource(R.drawable.fallback_asset)')
    end

    it 'summons no image at all when only errorImage is declared' do
      result = generate('errorImage' => 'error_asset')
      expect(result).not_to include('fallback = ')
      expect(result).to include('error = painterResource(R.drawable.error_asset)')
    end

    it 'summons no image at all when only loadingImage is declared' do
      result = generate('loadingImage' => 'loading_asset')
      expect(result).not_to include('fallback = ')
      expect(result).not_to include('error = ')
      expect(result).to include('placeholder = painterResource(R.drawable.loading_asset)')
    end

    it 'summons no image at all when only placeholder is declared' do
      result = generate('placeholder' => 'loading_asset')
      expect(result).not_to include('fallback = ')
      expect(result).not_to include('error = ')
    end

    it 'falls the error slot back to defaultImage, never to the loading image' do
      result = generate('placeholder' => 'loading_asset', 'defaultImage' => 'fallback_asset')
      expect(result).to include('error = painterResource(R.drawable.fallback_asset)')
      expect(result).to include('fallback = painterResource(R.drawable.fallback_asset)')
    end

    it 'keeps errorImage ahead of defaultImage in the error slot' do
      result = generate('errorImage' => 'error_asset', 'defaultImage' => 'fallback_asset')
      expect(result).to include('error = painterResource(R.drawable.error_asset)')
      expect(result).to include('fallback = painterResource(R.drawable.fallback_asset)')
    end

    it 'emits no state slot, and no painter imports, when none is declared' do
      imports = Set.new
      result = described_class.generate({ 'type' => 'NetworkImage' }, 0, imports)
      expect(result).not_to include('fallback = ')
      expect(result).not_to include('error = ')
      expect(imports).not_to include(:painter_resource)
    end
  end
end

# `headers` is declared `platform: kotlin, mode: compose` — a plain String model
# has nowhere to put them, so the URL becomes a built ImageRequest.
RSpec.describe KjuiTools::Compose::Components::NetworkImageComponent, 'headers' do
  let(:required_imports) { Set.new }

  before { KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {} }

  def image(extra)
    described_class.generate(
      { 'type' => 'NetworkImage', 'url' => '@{imageUrl}' }.merge(extra), 0, required_imports
    )
  end

  # Coil 3 moved these off the request builder: `addHeader` was Coil 2, and the
  # current API is `httpHeaders(NetworkHeaders)`.
  it 'builds an ImageRequest with the headers' do
    result = image('headers' => { 'Authorization' => 'Bearer x', 'X-Env' => 'prod' })
    expect(result).to include('ImageRequest.Builder(LocalContext.current)')
    expect(result).to include('.httpHeaders(NetworkHeaders.Builder()')
    expect(result).to include('.add("Authorization", "Bearer x")')
    expect(result).to include('.add("X-Env", "prod")')
    expect(required_imports).to include(:image_request, :network_headers, :local_context)
  end

  it 'leaves the model a plain URL without headers' do
    result = image({})
    expect(result).to include('model = data.imageUrl,')
    expect(result).not_to include('ImageRequest')
  end

  it 'ignores an empty header map' do
    expect(image('headers' => {})).not_to include('ImageRequest')
  end

  # A header value with a $ would otherwise open a Kotlin string template.
  it 'escapes the header values' do
    expect(image('headers' => { 'X-Token' => 'a$b"c' }))
      .to include(%q{.add("X-Token", "a\$b\"c")})
  end
end
