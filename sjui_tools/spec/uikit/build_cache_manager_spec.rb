# frozen_string_literal: true

require 'uikit/build_cache_manager'
require 'fileutils'
require 'tmpdir'

RSpec.describe SjuiTools::UIKit::BuildCacheManager do
  let(:temp_dir) { Dir.mktmpdir('uikit_cache_test') }
  let(:cache_manager) { described_class.new(temp_dir) }

  before do
    allow(SjuiTools::Core::BasePath).to receive(:root).and_return(temp_dir)
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
        File.write(File.join(cache_dir, 'last_updated.txt'), time.to_s)

        result = cache_manager.load_last_updated
        expect(result).to be_a(Time)
      end
    end

    context 'when file has invalid content' do
      it 'returns nil' do
        cache_dir = File.join(temp_dir, '.sjui_cache')
        FileUtils.mkdir_p(cache_dir)
        File.write(File.join(cache_dir, 'last_updated.txt'), 'invalid')

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
        File.write(File.join(cache_dir, 'including.json'), '{"main": ["header"]}')

        expect(cache_manager.load_last_including_files).to eq({ 'main' => ['header'] })
      end
    end

    context 'when file has invalid JSON' do
      it 'returns empty hash' do
        cache_dir = File.join(temp_dir, '.sjui_cache')
        FileUtils.mkdir_p(cache_dir)
        File.write(File.join(cache_dir, 'including.json'), 'invalid')

        expect(cache_manager.load_last_including_files).to eq({})
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
      it 'returns true when no including files info' do
        file_path = File.join(layout_path, 'test.json')
        File.write(file_path, '{}')
        sleep(0.1)
        last_updated = Time.now + 3600

        # Returns true because including_files[file_name] is nil
        expect(cache_manager.needs_update?(file_path, last_updated, layout_path, {})).to be true
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

    context 'when included file with subdirectory' do
      it 'finds partial file with underscore prefix' do
        file_path = File.join(layout_path, 'test.json')
        File.write(file_path, '{}')

        sub_dir = File.join(layout_path, 'components')
        FileUtils.mkdir_p(sub_dir)
        included_path = File.join(sub_dir, '_button.json')
        File.write(included_path, '{}')

        last_updated = Time.now - 3600
        last_including_files = { 'test' => ['components/button'] }

        expect(cache_manager.needs_update?(file_path, last_updated, layout_path, last_including_files)).to be true
      end
    end

    context 'when included file without underscore' do
      it 'finds regular file' do
        file_path = File.join(layout_path, 'test.json')
        File.write(file_path, '{}')

        included_path = File.join(layout_path, 'common.json')
        File.write(included_path, '{}')

        last_updated = Time.now - 3600
        last_including_files = { 'test' => ['common'] }

        expect(cache_manager.needs_update?(file_path, last_updated, layout_path, last_including_files)).to be true
      end
    end
  end

  describe '#save_cache' do
    it 'saves including files and timestamp' do
      cache_manager.save_cache({ 'main' => ['header', 'footer'] })

      cache_dir = File.join(temp_dir, '.sjui_cache')
      expect(File.exist?(File.join(cache_dir, 'including.json'))).to be true
      expect(File.exist?(File.join(cache_dir, 'last_updated.txt'))).to be true

      including = JSON.parse(File.read(File.join(cache_dir, 'including.json')))
      expect(including).to eq({ 'main' => ['header', 'footer'] })
    end
  end
end
