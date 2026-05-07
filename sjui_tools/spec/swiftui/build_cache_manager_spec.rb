# frozen_string_literal: true

require 'swiftui/build_cache_manager'
require 'fileutils'
require 'tmpdir'

RSpec.describe SjuiTools::SwiftUI::BuildCacheManager do
  let(:temp_dir) { Dir.mktmpdir('build_cache_test') }
  let(:cache_manager) { described_class.new(temp_dir) }

  before do
    allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths)
    allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'creates cache directory' do
      described_class.new(temp_dir)
      expect(Dir.exist?(File.join(temp_dir, '.sjui_cache'))).to be true
    end
  end

  describe '#clean_cache' do
    before do
      cache_dir = File.join(temp_dir, '.sjui_cache')
      FileUtils.mkdir_p(cache_dir)
      File.write(File.join(cache_dir, 'swiftui_last_updated.txt'), Time.now.to_s)
      File.write(File.join(cache_dir, 'swiftui_including.json'), '{}')
      File.write(File.join(cache_dir, 'swiftui_style_deps.json'), '{}')
    end

    it 'deletes all cache files' do
      cache_manager.clean_cache

      cache_dir = File.join(temp_dir, '.sjui_cache')
      expect(File.exist?(File.join(cache_dir, 'swiftui_last_updated.txt'))).to be false
      expect(File.exist?(File.join(cache_dir, 'swiftui_including.json'))).to be false
      expect(File.exist?(File.join(cache_dir, 'swiftui_style_deps.json'))).to be false
    end
  end

  describe '#load_last_updated' do
    context 'when file does not exist' do
      it 'returns nil' do
        expect(cache_manager.load_last_updated).to be_nil
      end
    end

    context 'when file exists with valid time' do
      it 'returns parsed time' do
        cache_dir = File.join(temp_dir, '.sjui_cache')
        FileUtils.mkdir_p(cache_dir)
        time = Time.now
        File.write(File.join(cache_dir, 'swiftui_last_updated.txt'), time.to_s)

        result = cache_manager.load_last_updated
        expect(result).to be_a(Time)
      end
    end

    context 'when file has invalid content' do
      it 'returns nil' do
        cache_dir = File.join(temp_dir, '.sjui_cache')
        FileUtils.mkdir_p(cache_dir)
        File.write(File.join(cache_dir, 'swiftui_last_updated.txt'), 'invalid')

        expect(cache_manager.load_last_updated).to be_nil
      end
    end
  end

  describe '#load_last_including_files' do
    context 'when file does not exist' do
      it 'returns empty hash' do
        expect(cache_manager.load_last_including_files).to eq({})
      end
    end

    context 'when file exists' do
      it 'returns parsed JSON' do
        cache_dir = File.join(temp_dir, '.sjui_cache')
        FileUtils.mkdir_p(cache_dir)
        File.write(File.join(cache_dir, 'swiftui_including.json'), '{"main": ["header"]}')

        expect(cache_manager.load_last_including_files).to eq({ 'main' => ['header'] })
      end
    end

    context 'when file has invalid JSON' do
      it 'returns empty hash' do
        cache_dir = File.join(temp_dir, '.sjui_cache')
        FileUtils.mkdir_p(cache_dir)
        File.write(File.join(cache_dir, 'swiftui_including.json'), 'invalid')

        expect(cache_manager.load_last_including_files).to eq({})
      end
    end
  end

  describe '#load_style_dependencies' do
    context 'when file does not exist' do
      it 'returns empty hash' do
        expect(cache_manager.load_style_dependencies).to eq({})
      end
    end

    context 'when file exists' do
      it 'returns parsed JSON' do
        cache_dir = File.join(temp_dir, '.sjui_cache')
        FileUtils.mkdir_p(cache_dir)
        File.write(File.join(cache_dir, 'swiftui_style_deps.json'), '{"main": ["base"]}')

        expect(cache_manager.load_style_dependencies).to eq({ 'main' => ['base'] })
      end
    end
  end

  describe '#needs_update?' do
    let(:layout_path) { File.join(temp_dir, 'Layouts') }

    before do
      FileUtils.mkdir_p(layout_path)
    end

    context 'when last_updated is nil' do
      it 'returns true' do
        file_path = File.join(layout_path, 'test.json')
        File.write(file_path, '{}')

        expect(cache_manager.needs_update?(file_path, nil, layout_path, {})).to be true
      end
    end

    context 'when file is newer than last_updated' do
      it 'returns true' do
        file_path = File.join(layout_path, 'test.json')
        File.write(file_path, '{}')
        last_updated = Time.now - 3600

        expect(cache_manager.needs_update?(file_path, last_updated, layout_path, {})).to be true
      end
    end

    context 'when file is older than last_updated' do
      it 'returns false' do
        file_path = File.join(layout_path, 'test.json')
        File.write(file_path, '{}')
        sleep(0.1) # Ensure time difference
        last_updated = Time.now + 3600

        expect(cache_manager.needs_update?(file_path, last_updated, layout_path, {})).to be false
      end
    end

    context 'when included file is newer' do
      it 'returns true' do
        file_path = File.join(layout_path, 'test.json')
        File.write(file_path, '{}')

        included_path = File.join(layout_path, '_header.json')
        File.write(included_path, '{}')

        last_updated = Time.now - 3600
        last_including_files = { 'test' => ['header'] }

        expect(cache_manager.needs_update?(file_path, last_updated, layout_path, last_including_files)).to be true
      end
    end
  end

  describe '#extract_includes' do
    it 'extracts include from component' do
      json_data = { 'include' => 'header' }
      expect(cache_manager.extract_includes(json_data)).to eq(['header'])
    end

    it 'extracts from children' do
      json_data = {
        'child' => [
          { 'include' => 'item1' },
          { 'include' => 'item2' }
        ]
      }
      expect(cache_manager.extract_includes(json_data)).to eq(['item1', 'item2'])
    end

    it 'extracts from nested children' do
      json_data = {
        'child' => {
          'include' => 'nested'
        }
      }
      expect(cache_manager.extract_includes(json_data)).to eq(['nested'])
    end

    it 'handles children key' do
      json_data = {
        'children' => [
          { 'include' => 'child1' }
        ]
      }
      expect(cache_manager.extract_includes(json_data)).to eq(['child1'])
    end

    it 'returns empty for non-hash' do
      expect(cache_manager.extract_includes('string')).to eq([])
      expect(cache_manager.extract_includes(nil)).to eq([])
    end
  end

  describe '#extract_styles' do
    it 'extracts style from component' do
      json_data = { 'style' => 'primary' }
      expect(cache_manager.extract_styles(json_data)).to eq(['primary'])
    end

    it 'extracts from children' do
      json_data = {
        'child' => [
          { 'style' => 'style1' },
          { 'style' => 'style2' }
        ]
      }
      expect(cache_manager.extract_styles(json_data)).to eq(['style1', 'style2'])
    end

    it 'returns unique styles' do
      json_data = {
        'style' => 'base',
        'child' => [
          { 'style' => 'base' },
          { 'style' => 'other' }
        ]
      }
      expect(cache_manager.extract_styles(json_data)).to eq(['base', 'other'])
    end

    it 'returns empty for non-hash' do
      expect(cache_manager.extract_styles('string')).to eq([])
    end
  end

  describe '#save_cache' do
    it 'saves all cache files' do
      cache_manager.save_cache({ 'main' => ['header'] }, { 'main' => ['base'] })

      cache_dir = File.join(temp_dir, '.sjui_cache')
      expect(File.exist?(File.join(cache_dir, 'swiftui_including.json'))).to be true
      expect(File.exist?(File.join(cache_dir, 'swiftui_style_deps.json'))).to be true
      expect(File.exist?(File.join(cache_dir, 'swiftui_last_updated.txt'))).to be true

      including = JSON.parse(File.read(File.join(cache_dir, 'swiftui_including.json')))
      expect(including).to eq({ 'main' => ['header'] })
    end
  end

  describe '#clear_cache' do
    before do
      cache_dir = File.join(temp_dir, '.sjui_cache')
      FileUtils.mkdir_p(cache_dir)
      File.write(File.join(cache_dir, 'swiftui_last_updated.txt'), Time.now.to_s)
      File.write(File.join(cache_dir, 'swiftui_including.json'), '{}')
      File.write(File.join(cache_dir, 'swiftui_style_deps.json'), '{}')
    end

    it 'removes cache files' do
      cache_manager.clear_cache

      cache_dir = File.join(temp_dir, '.sjui_cache')
      expect(File.exist?(File.join(cache_dir, 'swiftui_last_updated.txt'))).to be false
      expect(File.exist?(File.join(cache_dir, 'swiftui_including.json'))).to be false
      expect(File.exist?(File.join(cache_dir, 'swiftui_style_deps.json'))).to be false
    end
  end
end
