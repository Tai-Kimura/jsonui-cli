# frozen_string_literal: true

require 'compose/components/circleimage_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'

RSpec.describe KjuiTools::Compose::Components::CircleImageComponent do
  let(:required_imports) { Set.new }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
  end

  describe '.generate' do
    context 'local images' do
      it 'generates Image for local source' do
        json_data = { 'type' => 'CircleImage', 'source' => 'profile.png' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('Image(')
        expect(result).to include('painterResource(id = R.drawable.profile)')
      end

      it 'generates Image with src attribute' do
        json_data = { 'type' => 'CircleImage', 'src' => 'avatar.png' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('R.drawable.avatar')
      end

      it 'removes file extensions' do
        json_data = { 'type' => 'CircleImage', 'source' => 'icon.jpg' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('R.drawable.icon)')
        expect(result).not_to include('.jpg')
      end

      it 'converts dashes to underscores' do
        json_data = { 'type' => 'CircleImage', 'source' => 'user-avatar.png' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('R.drawable.user_avatar')
      end

      it 'uses placeholder for missing source' do
        json_data = { 'type' => 'CircleImage' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('R.drawable.placeholder')
      end
    end

    context 'network images' do
      it 'generates AsyncImage for network url' do
        json_data = { 'type' => 'CircleImage', 'url' => 'https://example.com/image.png' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('AsyncImage(')
        expect(result).to include('model =')
        expect(required_imports).to include(:async_image)
      end

      it 'generates AsyncImage for http source' do
        json_data = { 'type' => 'CircleImage', 'source' => 'https://example.com/avatar.jpg' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('AsyncImage(')
      end

      it 'handles url data binding' do
        json_data = { 'type' => 'CircleImage', 'url' => '@{user.avatarUrl}' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('model = data.user.avatarUrl')
      end

      it 'includes errorImage for network images' do
        json_data = {
          'type' => 'CircleImage',
          'url' => 'https://example.com/image.png',
          'errorImage' => 'error_placeholder.png'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('error = painterResource(R.drawable.error_placeholder)')
      end
    end

    context 'content description' do
      it 'uses default contentDescription' do
        json_data = { 'type' => 'CircleImage' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('contentDescription = "Profile Image"')
      end

      it 'uses custom contentDescription' do
        json_data = { 'type' => 'CircleImage', 'contentDescription' => 'User Avatar' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('contentDescription = "User Avatar"')
      end
    end

    context 'content scale' do
      it 'uses ContentScale.Crop' do
        json_data = { 'type' => 'CircleImage' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('contentScale = ContentScale.Crop')
        expect(required_imports).to include(:content_scale)
      end
    end

    context 'size and shape' do
      it 'uses default size of 48dp' do
        json_data = { 'type' => 'CircleImage' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.size(48.dp)')
      end

      it 'uses custom size' do
        json_data = { 'type' => 'CircleImage', 'size' => 64 }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.size(64.dp)')
      end

      it 'clips to CircleShape' do
        json_data = { 'type' => 'CircleImage' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.clip(CircleShape)')
        expect(required_imports).to include(:shape)
      end
    end

    context 'border' do
      it 'adds border when borderWidth and borderColor provided' do
        json_data = {
          'type' => 'CircleImage',
          'borderWidth' => 2,
          'borderColor' => '#007AFF'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.border(')
        expect(result).to include('2.dp')
        expect(required_imports).to include(:border)
      end

      it 'does not add border without both width and color' do
        json_data = { 'type' => 'CircleImage', 'borderWidth' => 2 }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).not_to include('.border(')
      end
    end

    context 'background' do
      it 'adds background color' do
        json_data = { 'type' => 'CircleImage', 'background' => '#CCCCCC' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.background(')
        expect(required_imports).to include(:background)
      end
    end

    context 'padding and margins' do
      it 'includes padding' do
        json_data = { 'type' => 'CircleImage', 'padding' => 8 }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('modifier = Modifier')
      end

      it 'includes margins' do
        json_data = { 'type' => 'CircleImage', 'margins' => [4, 8] }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('modifier = Modifier')
      end
    end
  end

  describe '.process_data_binding' do
    it 'quotes non-binding text' do
      result = described_class.send(:process_data_binding, 'https://example.com')
      expect(result).to eq('"https://example.com"')
    end

    it 'converts binding to data accessor' do
      result = described_class.send(:process_data_binding, '@{imageUrl}')
      expect(result).to eq('data.imageUrl')
    end

    it 'handles empty string' do
      result = described_class.send(:process_data_binding, '')
      expect(result).to eq('""')
    end
  end

  describe '.quote' do
    it 'quotes text' do
      result = described_class.send(:quote, 'Hello')
      expect(result).to eq('"Hello"')
    end

    it 'escapes quotes' do
      result = described_class.send(:quote, 'Hello "World"')
      expect(result).to eq('"Hello \\"World\\""')
    end
  end

  describe '.indent' do
    it 'returns text unchanged for level 0' do
      result = described_class.send(:indent, 'text', 0)
      expect(result).to eq('text')
    end

    it 'adds indentation for level 1' do
      result = described_class.send(:indent, 'text', 1)
      expect(result).to eq('    text')
    end
  end
end
