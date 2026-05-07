# frozen_string_literal: true

require 'core/config_manager'

RSpec.describe KjuiTools::Core::ConfigManager do
  let(:temp_dir) { Dir.mktmpdir('config_test') }
  let(:original_dir) { Dir.pwd }

  before do
    @original_dir = Dir.pwd
    Dir.chdir(temp_dir)
  end

  after do
    Dir.chdir(@original_dir)
    FileUtils.rm_rf(temp_dir)
  end

  describe '.load_config' do
    context 'when config file exists' do
      before do
        config = {
          'mode' => 'compose',
          'package_name' => 'com.test.app',
          'source_directory' => 'src/main'
        }
        File.write(File.join(temp_dir, 'kjui.config.json'), JSON.pretty_generate(config))
      end

      it 'loads and merges with default config' do
        config = described_class.load_config
        expect(config['mode']).to eq('compose')
        expect(config['package_name']).to eq('com.test.app')
        # Check default values are preserved
        expect(config['layouts_directory']).to eq('assets/Layouts')
      end

      it 'stores config directory' do
        config = described_class.load_config
        # _config_dir is set to '.' when config is found in current directory
        expect(config).to have_key('_config_dir')
      end
    end

    context 'when config file does not exist' do
      it 'returns default config' do
        config = described_class.load_config
        expect(config['mode']).to eq('compose')
        expect(config['package_name']).to eq('com.example.app')
      end
    end

    context 'when config file is invalid JSON' do
      before do
        File.write(File.join(temp_dir, 'kjui.config.json'), 'invalid json {')
      end

      it 'returns default config and prints error' do
        expect { described_class.load_config }.to output(/Error parsing config file/).to_stdout
      end
    end
  end

  describe '.find_config_file' do
    context 'when config exists in current directory' do
      before do
        File.write(File.join(temp_dir, 'kjui.config.json'), '{}')
      end

      it 'returns the config file path' do
        result = described_class.find_config_file
        expect(result).to eq('kjui.config.json')
      end
    end

    context 'when config exists in subdirectory' do
      before do
        sub_dir = File.join(temp_dir, 'app')
        FileUtils.mkdir_p(sub_dir)
        File.write(File.join(sub_dir, 'kjui.config.json'), '{}')
      end

      it 'finds the config file in subdirectory' do
        result = described_class.find_config_file
        expect(result).to include('kjui.config.json')
      end
    end

    context 'when no config file exists' do
      it 'returns nil' do
        result = described_class.find_config_file
        expect(result).to be_nil
      end
    end
  end

  describe '.save_config' do
    it 'saves config to file' do
      config = { 'mode' => 'xml', 'test' => 'value' }
      described_class.save_config(config)

      expect(File.exist?(File.join(temp_dir, 'kjui.config.json'))).to be true
      saved_content = JSON.parse(File.read(File.join(temp_dir, 'kjui.config.json')))
      expect(saved_content['mode']).to eq('xml')
      expect(saved_content['test']).to eq('value')
    end
  end

  describe '.deep_merge' do
    it 'merges nested hashes' do
      hash1 = { 'a' => 1, 'nested' => { 'x' => 1, 'y' => 2 } }
      hash2 = { 'b' => 2, 'nested' => { 'y' => 3, 'z' => 4 } }

      result = described_class.deep_merge(hash1, hash2)

      expect(result['a']).to eq(1)
      expect(result['b']).to eq(2)
      expect(result['nested']['x']).to eq(1)
      expect(result['nested']['y']).to eq(3)
      expect(result['nested']['z']).to eq(4)
    end

    it 'replaces non-hash values' do
      hash1 = { 'key' => 'old' }
      hash2 = { 'key' => 'new' }

      result = described_class.deep_merge(hash1, hash2)
      expect(result['key']).to eq('new')
    end
  end

  describe '.config_exists?' do
    it 'returns true when config file exists' do
      File.write(File.join(temp_dir, 'kjui.config.json'), '{}')
      expect(described_class.config_exists?).to be true
    end

    it 'returns false when config file does not exist' do
      expect(described_class.config_exists?).to be false
    end
  end

  describe '.get' do
    before do
      config = {
        'mode' => 'compose',
        'nested' => { 'key' => 'value' }
      }
      File.write(File.join(temp_dir, 'kjui.config.json'), JSON.pretty_generate(config))
    end

    it 'gets top-level value' do
      expect(described_class.get('mode')).to eq('compose')
    end

    it 'gets nested value with dot notation' do
      expect(described_class.get('nested.key')).to eq('value')
    end

    it 'returns default when key not found' do
      expect(described_class.get('nonexistent', 'default')).to eq('default')
    end
  end

  describe '.set' do
    before do
      File.write(File.join(temp_dir, 'kjui.config.json'), '{}')
    end

    it 'sets top-level value' do
      described_class.set('mode', 'xml')
      config = JSON.parse(File.read(File.join(temp_dir, 'kjui.config.json')))
      expect(config['mode']).to eq('xml')
    end

    it 'sets nested value with dot notation' do
      described_class.set('nested.key', 'value')
      config = JSON.parse(File.read(File.join(temp_dir, 'kjui.config.json')))
      expect(config['nested']['key']).to eq('value')
    end
  end

  describe '.detect_mode' do
    context 'with Compose project' do
      before do
        File.write(File.join(temp_dir, 'build.gradle'), "implementation 'androidx.compose.ui:ui:1.0.0'")
      end

      it 'returns compose' do
        expect(described_class.detect_mode).to eq('compose')
      end
    end

    context 'with XML project' do
      before do
        File.write(File.join(temp_dir, 'build.gradle'), "implementation 'com.android.support:appcompat-v7:28.0.0'")
      end

      it 'returns xml' do
        expect(described_class.detect_mode).to eq('xml')
      end
    end

    context 'with non-Android project' do
      it 'returns all' do
        expect(described_class.detect_mode).to eq('all')
      end
    end
  end

  describe '.project_type' do
    before do
      config = { 'mode' => mode }
      File.write(File.join(temp_dir, 'kjui.config.json'), JSON.pretty_generate(config))
    end

    context 'when mode is compose' do
      let(:mode) { 'compose' }

      it 'returns Jetpack Compose' do
        expect(described_class.project_type).to eq('Jetpack Compose')
      end
    end

    context 'when mode is xml' do
      let(:mode) { 'xml' }

      it 'returns Android XML' do
        expect(described_class.project_type).to eq('Android XML')
      end
    end

    context 'when mode is all' do
      let(:mode) { 'all' }

      it 'returns Android (XML + Compose)' do
        expect(described_class.project_type).to eq('Android (XML + Compose)')
      end
    end

    context 'when mode is unknown' do
      let(:mode) { 'unknown' }

      it 'returns Unknown' do
        expect(described_class.project_type).to eq('Unknown')
      end
    end
  end

  describe 'path methods' do
    before do
      config = {
        'source_directory' => 'app/src/main',
        'layouts_directory' => 'assets/Layouts',
        'styles_directory' => 'assets/Styles',
        'view_directory' => 'kotlin/views',
        'data_directory' => 'kotlin/data',
        'viewmodel_directory' => 'kotlin/viewmodels',
        'mode' => 'compose',
        'compose' => { 'output_directory' => 'kotlin/generated' }
      }
      File.write(File.join(temp_dir, 'kjui.config.json'), JSON.pretty_generate(config))
    end

    it 'returns correct source_path' do
      expect(described_class.source_path).to eq('app/src/main')
    end

    it 'returns correct layouts_path' do
      expect(described_class.layouts_path.to_s).to include('assets/Layouts')
    end

    it 'returns correct styles_path' do
      expect(described_class.styles_path.to_s).to include('assets/Styles')
    end

    it 'returns correct view_path' do
      expect(described_class.view_path.to_s).to include('kotlin/views')
    end

    it 'returns correct data_path' do
      expect(described_class.data_path.to_s).to include('kotlin/data')
    end

    it 'returns correct viewmodel_path' do
      expect(described_class.viewmodel_path.to_s).to include('kotlin/viewmodels')
    end

    it 'returns correct generated_path for compose mode' do
      expect(described_class.generated_path.to_s).to include('kotlin/generated')
    end
  end
end
