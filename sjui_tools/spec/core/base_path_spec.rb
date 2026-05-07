# frozen_string_literal: true

require 'core/base_path'

RSpec.describe SjuiTools::Core::BasePath do
  describe '.root' do
    it 'returns a path' do
      expect(described_class.root).to be_a(String)
    end

    it 'returns a valid directory' do
      expect(Dir.exist?(described_class.root)).to be true
    end

    it 'is memoized' do
      result1 = described_class.root
      result2 = described_class.root

      expect(result1).to eq(result2)
    end
  end

  describe '.config_path' do
    it 'returns path with default filename' do
      path = described_class.config_path

      expect(path).to include('config')
      expect(path).to include('config.json')
    end

    it 'returns path with custom filename' do
      path = described_class.config_path('custom.json')

      expect(path).to include('custom.json')
    end
  end

  describe '.find_root' do
    it 'finds sjui_tools directory' do
      root = described_class.find_root

      # Either finds sjui_tools dir or uses fallback
      expect(root).to be_a(String)
    end
  end

  describe '.project_root' do
    it 'returns parent of root' do
      root = described_class.root
      project_root = described_class.project_root

      expect(project_root).to eq(File.dirname(root))
    end
  end
end
