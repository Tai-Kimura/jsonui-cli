# frozen_string_literal: true

require 'compose/build_cache_manager'
require 'fileutils'
require 'json'

RSpec.describe KjuiTools::Compose::BuildCacheManager do
  let(:temp_dir) { Dir.mktmpdir('cache_test') }
  let(:layouts_dir) { File.join(temp_dir, 'assets', 'Layouts') }
  let(:cache_dir) { File.join(temp_dir, '.kjui_cache') }

  # Don't create cache_manager in let block - need to control timing
  before do
    FileUtils.mkdir_p(layouts_dir)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'creates cache directory' do
      # Create cache_manager which should create the cache directory
      described_class.new(temp_dir)
      expect(File.directory?(cache_dir)).to be true
    end
  end

  describe '#load_last_updated' do
    it 'returns empty hash when cache file does not exist' do
      cache_manager = described_class.new(temp_dir)
      expect(cache_manager.load_last_updated).to eq({})
    end

    it 'returns cached data when file exists' do
      # Create cache_manager first (creates directory), then write file
      cache_manager = described_class.new(temp_dir)
      File.write(File.join(cache_dir, 'last_updated.json'), '{"test": {"mtime": 12345}}')
      expect(cache_manager.load_last_updated).to eq({ 'test' => { 'mtime' => 12345 } })
    end

    it 'returns empty hash on parse error' do
      cache_manager = described_class.new(temp_dir)
      File.write(File.join(cache_dir, 'last_updated.json'), 'invalid json')
      expect(cache_manager.load_last_updated).to eq({})
    end
  end

  describe '#load_last_including_files' do
    it 'returns empty hash when cache file does not exist' do
      cache_manager = described_class.new(temp_dir)
      expect(cache_manager.load_last_including_files).to eq({})
    end

    it 'returns cached data when file exists' do
      cache_manager = described_class.new(temp_dir)
      File.write(File.join(cache_dir, 'including_files.json'), '{"main": ["header", "footer"]}')
      expect(cache_manager.load_last_including_files).to eq({ 'main' => ['header', 'footer'] })
    end
  end

  describe '#load_style_dependencies' do
    it 'returns empty hash when cache file does not exist' do
      cache_manager = described_class.new(temp_dir)
      expect(cache_manager.load_style_dependencies).to eq({})
    end
  end

  describe '#needs_update?' do
    let(:json_file) { File.join(layouts_dir, 'test.json') }

    before do
      File.write(json_file, '{"type": "View"}')
    end

    it 'returns true when file not in last_updated' do
      cache_manager = described_class.new(temp_dir)
      expect(cache_manager.needs_update?(json_file, {}, layouts_dir, {}, {})).to be true
    end

    it 'returns true when file modified after last update' do
      cache_manager = described_class.new(temp_dir)
      old_time = Time.now.to_i - 3600
      last_updated = { 'test' => { 'mtime' => old_time } }
      expect(cache_manager.needs_update?(json_file, last_updated, layouts_dir, {}, {})).to be true
    end

    it 'returns false when file not modified' do
      cache_manager = described_class.new(temp_dir)
      current_time = File.mtime(json_file).to_i + 1
      last_updated = { 'test' => { 'mtime' => current_time } }
      expect(cache_manager.needs_update?(json_file, last_updated, layouts_dir, {}, {})).to be false
    end
  end

  describe '#extract_includes' do
    it 'extracts include from simple component' do
      cache_manager = described_class.new(temp_dir)
      json_data = { 'include' => 'header' }
      result = cache_manager.extract_includes(json_data)
      expect(result).to include('header')
    end

    it 'extracts includes from children' do
      cache_manager = described_class.new(temp_dir)
      json_data = {
        'type' => 'View',
        'child' => [
          { 'include' => 'header' },
          { 'include' => 'footer' }
        ]
      }
      result = cache_manager.extract_includes(json_data)
      expect(result).to include('header')
      expect(result).to include('footer')
    end

    it 'handles nested children' do
      cache_manager = described_class.new(temp_dir)
      json_data = {
        'type' => 'View',
        'child' => {
          'type' => 'View',
          'child' => { 'include' => 'nested' }
        }
      }
      result = cache_manager.extract_includes(json_data)
      expect(result).to include('nested')
    end

    it 'handles arrays' do
      cache_manager = described_class.new(temp_dir)
      json_data = [{ 'include' => 'item1' }, { 'include' => 'item2' }]
      result = cache_manager.extract_includes(json_data)
      expect(result).to include('item1')
      expect(result).to include('item2')
    end
  end

  describe '#extract_styles' do
    it 'extracts style from simple component' do
      cache_manager = described_class.new(temp_dir)
      json_data = { 'style' => 'cardStyle' }
      result = cache_manager.extract_styles(json_data)
      expect(result).to include('cardStyle')
    end

    it 'extracts styles from children' do
      cache_manager = described_class.new(temp_dir)
      json_data = {
        'type' => 'View',
        'child' => [
          { 'style' => 'headerStyle' },
          { 'style' => 'buttonStyle' }
        ]
      }
      result = cache_manager.extract_styles(json_data)
      expect(result).to include('headerStyle')
      expect(result).to include('buttonStyle')
    end
  end

  describe '#save_cache' do
    it 'creates cache files' do
      cache_manager = described_class.new(temp_dir)
      File.write(File.join(layouts_dir, 'test.json'), '{"type": "View"}')

      cache_manager.save_cache({ 'test' => ['included'] }, { 'test' => ['style1'] })

      expect(File.exist?(File.join(cache_dir, 'last_updated.json'))).to be true
      expect(File.exist?(File.join(cache_dir, 'including_files.json'))).to be true
      expect(File.exist?(File.join(cache_dir, 'style_dependencies.json'))).to be true
    end
  end

  describe '#clean_cache' do
    it 'removes and recreates cache directory' do
      cache_manager = described_class.new(temp_dir)
      File.write(File.join(cache_dir, 'test_file.json'), '{}')

      cache_manager.clean_cache

      expect(File.directory?(cache_dir)).to be true
      expect(File.exist?(File.join(cache_dir, 'test_file.json'))).to be false
    end
  end
end
