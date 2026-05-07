# frozen_string_literal: true

require 'core/resources_manager'
require 'json'
require 'fileutils'

RSpec.describe SjuiTools::Core::ResourcesManager do
  let(:temp_dir) { File.realpath(Dir.mktmpdir('resources_manager_test')) }
  let(:layouts_dir) { File.join(temp_dir, 'Layouts') }
  let(:resources_dir) { File.join(layouts_dir, 'Resources') }

  before do
    FileUtils.mkdir_p(layouts_dir)
    FileUtils.mkdir_p(resources_dir)
    allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
    allow(SjuiTools::Core::Logger).to receive(:info)
    allow(SjuiTools::Core::Logger).to receive(:debug)
    allow(SjuiTools::Core::Logger).to receive(:warn)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'creates manager with config' do
      manager = described_class.new
      expect(manager.instance_variable_get(:@config)).to eq({})
      expect(manager.instance_variable_get(:@source_path)).to eq(temp_dir)
    end

    it 'initializes string and color managers' do
      manager = described_class.new
      expect(manager.instance_variable_get(:@string_manager)).to be_a(SjuiTools::Core::Resources::StringManager)
      expect(manager.instance_variable_get(:@color_manager)).to be_a(SjuiTools::Core::Resources::ColorManager)
    end
  end

  describe '#process_resources' do
    let(:manager) { described_class.new }

    before do
      allow(manager).to receive(:process_resource_extraction)
      allow(manager).to receive(:apply_extracted_strings)
      allow(manager).to receive(:apply_extracted_colors)
    end

    it 'calls all processing methods' do
      expect(manager).to receive(:process_resource_extraction)
      expect(manager).to receive(:apply_extracted_strings)
      expect(manager).to receive(:apply_extracted_colors)

      manager.process_resources(layouts_dir)
    end

    it 'passes last_updated to extraction' do
      last_updated = { 'test.json' => 12345 }
      expect(manager).to receive(:process_resource_extraction).with(layouts_dir, last_updated)

      manager.process_resources(layouts_dir, last_updated)
    end
  end

  describe '#process_resource_extraction' do
    let(:manager) { described_class.new }

    before do
      # Create test JSON files
      File.write(File.join(layouts_dir, 'test.json'), '{"type": "View"}')
      File.write(File.join(resources_dir, 'strings.json'), '{}')
      
      # Mock the managers
      string_manager = instance_double(SjuiTools::Core::Resources::StringManager)
      color_manager = instance_double(SjuiTools::Core::Resources::ColorManager)
      allow(string_manager).to receive(:process_strings)
      allow(color_manager).to receive(:process_colors)
      manager.instance_variable_set(:@string_manager, string_manager)
      manager.instance_variable_set(:@color_manager, color_manager)
    end

    it 'excludes files in Resources directory' do
      string_manager = manager.instance_variable_get(:@string_manager)
      
      expect(string_manager).to receive(:process_strings) do |files, _, _, _|
        expect(files.any? { |f| f.include?('Resources') }).to be false
      end

      manager.process_resource_extraction(layouts_dir)
    end

    it 'processes JSON files' do
      string_manager = manager.instance_variable_get(:@string_manager)
      
      expect(string_manager).to receive(:process_strings).with(
        array_including(match(/test\.json$/)),
        anything,
        anything,
        anything
      )

      manager.process_resource_extraction(layouts_dir)
    end

    it 'skips unchanged files' do
      last_updated = { 'test.json' => Time.now.to_i + 1000 }
      string_manager = manager.instance_variable_get(:@string_manager)
      
      expect(string_manager).to receive(:process_strings).with(
        [],
        0,
        1,
        anything
      )

      manager.process_resource_extraction(layouts_dir, last_updated)
    end

    it 'calls color manager with processed files' do
      color_manager = manager.instance_variable_get(:@color_manager)
      
      expect(color_manager).to receive(:process_colors).with(
        array_including(match(/test\.json$/)),
        anything,
        anything,
        anything
      )

      manager.process_resource_extraction(layouts_dir)
    end
  end

  describe '#apply_extracted_strings (private)' do
    let(:manager) { described_class.new }

    it 'calls string_manager apply method' do
      string_manager = instance_double(SjuiTools::Core::Resources::StringManager)
      expect(string_manager).to receive(:apply_to_strings_files)
      manager.instance_variable_set(:@string_manager, string_manager)

      manager.send(:apply_extracted_strings)
    end
  end

  describe '#apply_extracted_colors (private)' do
    let(:manager) { described_class.new }

    it 'calls color_manager apply method' do
      color_manager = instance_double(SjuiTools::Core::Resources::ColorManager)
      expect(color_manager).to receive(:apply_to_color_assets)
      manager.instance_variable_set(:@color_manager, color_manager)

      manager.send(:apply_extracted_colors)
    end
  end
end
