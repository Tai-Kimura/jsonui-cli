# frozen_string_literal: true

require 'core/resources_manager'
require 'core/config_manager'
require 'core/project_finder'

RSpec.describe KjuiTools::Core::ResourcesManager do
  let(:temp_dir) { Dir.mktmpdir }
  let(:config) do
    {
      'source_directory' => 'src/main',
      'package_name' => 'com.example.app'
    }
  end
  let(:source_path) { temp_dir }
  let(:manager) { described_class.new(config, source_path) }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)

    # Create necessary directories
    layouts_dir = File.join(temp_dir, 'src/main/assets/Layouts')
    resources_dir = File.join(layouts_dir, 'Resources')
    FileUtils.mkdir_p(resources_dir)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'sets up layouts and resources directories' do
      expect(manager.instance_variable_get(:@layouts_dir)).to include('assets/Layouts')
      expect(manager.instance_variable_get(:@resources_dir)).to include('Resources')
    end

    it 'creates string manager' do
      expect(manager.instance_variable_get(:@string_manager)).to be_a(KjuiTools::Core::Resources::StringManager)
    end

    it 'creates color manager' do
      expect(manager.instance_variable_get(:@color_manager)).to be_a(KjuiTools::Core::Resources::ColorManager)
    end
  end

  describe '#extract_resources' do
    let(:string_manager) { instance_double(KjuiTools::Core::Resources::StringManager) }
    let(:color_manager) { instance_double(KjuiTools::Core::Resources::ColorManager) }

    before do
      manager.instance_variable_set(:@string_manager, string_manager)
      manager.instance_variable_set(:@color_manager, color_manager)

      allow(string_manager).to receive(:process_strings)
      allow(string_manager).to receive(:apply_to_strings_files)
      allow(color_manager).to receive(:process_colors)
      allow(color_manager).to receive(:apply_to_color_assets)
    end

    it 'calls extract_from_json_files' do
      expect(manager).to receive(:extract_from_json_files).with([])
      manager.extract_resources([])
    end

    it 'applies extracted strings' do
      expect(string_manager).to receive(:apply_to_strings_files)
      manager.extract_resources([])
    end

    it 'applies extracted colors' do
      expect(color_manager).to receive(:apply_to_color_assets)
      manager.extract_resources([])
    end
  end

  describe '#extract_from_json_files' do
    let(:string_manager) { instance_double(KjuiTools::Core::Resources::StringManager) }
    let(:color_manager) { instance_double(KjuiTools::Core::Resources::ColorManager) }
    let(:layouts_dir) { File.join(temp_dir, 'src/main/assets/Layouts') }

    before do
      manager.instance_variable_set(:@string_manager, string_manager)
      manager.instance_variable_set(:@color_manager, color_manager)

      allow(string_manager).to receive(:process_strings)
      allow(color_manager).to receive(:process_colors)
    end

    it 'skips files in Resources directory' do
      resources_file = File.join(layouts_dir, 'Resources/strings.json')
      File.write(resources_file, '{}')

      manager.extract_from_json_files([resources_file])

      expect(string_manager).not_to have_received(:process_strings)
    end

    it 'processes non-Resources files' do
      layout_file = File.join(layouts_dir, 'main.json')
      File.write(layout_file, '{}')

      expect(string_manager).to receive(:process_strings).with([layout_file], 1, 0)
      expect(color_manager).to receive(:process_colors).with([layout_file], 1, 0, config)

      manager.extract_from_json_files([layout_file])
    end

    it 'logs info when no files to process' do
      resources_file = File.join(layouts_dir, 'Resources/strings.json')
      File.write(resources_file, '{}')

      expect(KjuiTools::Core::Logger).to receive(:info).with(/No files to process/)

      manager.extract_from_json_files([resources_file])
    end

    it 'creates Resources directory if not exists' do
      resources_dir = manager.instance_variable_get(:@resources_dir)
      FileUtils.rm_rf(resources_dir)

      layout_file = File.join(layouts_dir, 'main.json')
      File.write(layout_file, '{}')

      manager.extract_from_json_files([layout_file])

      expect(Dir.exist?(resources_dir)).to be true
    end
  end
end
