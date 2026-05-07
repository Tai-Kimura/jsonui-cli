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
end
