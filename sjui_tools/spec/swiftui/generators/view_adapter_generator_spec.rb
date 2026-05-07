# frozen_string_literal: true

require 'swiftui/generators/view_adapter_generator'
require 'fileutils'
require 'tmpdir'

RSpec.describe SjuiTools::SwiftUI::Generators::ViewAdapterGenerator do
  let(:temp_dir) { Dir.mktmpdir('view_adapter_generator_test') }
  let(:source_path) { File.join(temp_dir, 'MyApp') }
  let(:adapter_dir) { File.join(source_path, 'Extensions', 'Adapters') }

  before do
    FileUtils.mkdir_p(source_path)
    allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(source_path)
    allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
      'extension_directory' => 'Extensions'
    })
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'creates generator with name' do
      generator = described_class.new('Home')
      expect(generator).to be_a(described_class)
    end

    it 'sets view_name with View suffix' do
      generator = described_class.new('Home')
      expect(generator.instance_variable_get(:@view_name)).to eq('HomeView')
    end

    it 'sets adapter_class_name with ViewAdapter suffix' do
      generator = described_class.new('Home')
      expect(generator.instance_variable_get(:@adapter_class_name)).to eq('HomeViewAdapter')
    end
  end

  describe '#generate' do
    context 'with no adapter or extension directory configured' do
      before do
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
      end

      it 'outputs warning and returns false' do
        generator = described_class.new('Home')
        expect { generator.generate }.to output(/No adapter_directory configured/).to_stdout
        expect(generator.generate).to be false
      end
    end

    context 'with extension_directory configured' do
      it 'creates adapter directory in Extensions/Adapters' do
        generator = described_class.new('Home')
        generator.generate
        expect(Dir.exist?(adapter_dir)).to be true
      end

      it 'creates adapter Swift file' do
        generator = described_class.new('Home')
        generator.generate
        adapter_file = File.join(adapter_dir, 'HomeViewAdapter.swift')
        expect(File.exist?(adapter_file)).to be true
      end

      it 'creates CustomComponentRegistration.swift' do
        generator = described_class.new('Home')
        generator.generate
        registration_file = File.join(adapter_dir, 'CustomComponentRegistration.swift')
        expect(File.exist?(registration_file)).to be true
      end

      it 'returns true on success' do
        generator = described_class.new('Home')
        result = generator.generate
        expect(result).to be true
      end
    end

    context 'with adapter_directory configured' do
      before do
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
          'adapter_directory' => 'Adapters'
        })
      end

      it 'creates adapter in configured directory' do
        generator = described_class.new('Profile')
        generator.generate
        custom_adapter_dir = File.join(source_path, 'Adapters')
        expect(Dir.exist?(custom_adapter_dir)).to be true
        expect(File.exist?(File.join(custom_adapter_dir, 'ProfileViewAdapter.swift'))).to be true
      end
    end
  end

  describe '#adapter_template' do
    it 'generates template with correct view name' do
      generator = described_class.new('Home')
      template = generator.send(:adapter_template)
      expect(template).to include('HomeViewAdapter')
      expect(template).to include('HomeView(data: data)')
    end

    it 'generates lowercase component type' do
      generator = described_class.new('Home')
      template = generator.send(:adapter_template)
      expect(template).to include('componentType: String { "home" }')
    end

    it 'includes CustomComponentAdapter protocol' do
      generator = described_class.new('Search')
      template = generator.send(:adapter_template)
      expect(template).to include('struct SearchViewAdapter: CustomComponentAdapter')
    end

    it 'includes buildView function signature' do
      generator = described_class.new('Map')
      template = generator.send(:adapter_template)
      expect(template).to include('func buildView(')
      expect(template).to include('component: DynamicComponent')
      expect(template).to include('data: [String: Any]')
      expect(template).to include('viewId: String?')
      expect(template).to include('parentOrientation: String?')
      expect(template).to include(') -> AnyView')
    end

    it 'wraps view in AnyView' do
      generator = described_class.new('Profile')
      template = generator.send(:adapter_template)
      expect(template).to include('AnyView(')
      expect(template).to include('ProfileView(data: data)')
    end

    it 'includes DEBUG preprocessor directive' do
      generator = described_class.new('Home')
      template = generator.send(:adapter_template)
      expect(template).to include('#if DEBUG')
      expect(template).to include('#endif')
    end

    it 'imports SwiftUI and SwiftJsonUI' do
      generator = described_class.new('Home')
      template = generator.send(:adapter_template)
      expect(template).to include('import SwiftUI')
      expect(template).to include('import SwiftJsonUI')
    end
  end

  describe '#registration_template' do
    it 'generates registration template with adapter' do
      generator = described_class.new('Home')
      template = generator.send(:registration_template)
      expect(template).to include('CustomComponentRegistration')
      expect(template).to include('HomeViewAdapter()')
      expect(template).to include('registerAll')
    end

    it 'includes CustomComponentRegistry usage' do
      generator = described_class.new('Search')
      template = generator.send(:registration_template)
      expect(template).to include('CustomComponentRegistry.shared.registerAll(adapters)')
    end

    it 'includes DEBUG preprocessor directive' do
      generator = described_class.new('Home')
      template = generator.send(:registration_template)
      expect(template).to include('#if DEBUG')
      expect(template).to include('#endif')
    end
  end

  describe '#update_registration_file' do
    let(:generator) { described_class.new('NewView') }
    let(:registration_file) { File.join(adapter_dir, 'CustomComponentRegistration.swift') }

    before do
      FileUtils.mkdir_p(adapter_dir)
    end

    context 'when registration file does not exist' do
      it 'creates registration file' do
        generator.send(:update_registration_file, adapter_dir)
        expect(File.exist?(registration_file)).to be true
      end

      it 'includes the new adapter' do
        generator.send(:update_registration_file, adapter_dir)
        content = File.read(registration_file)
        expect(content).to include('NewViewViewAdapter()')
      end
    end

    context 'when registration file exists with other adapters' do
      before do
        File.write(registration_file, <<~SWIFT)
          let adapters: [CustomComponentAdapter] = [
              HomeViewAdapter()
          ]
        SWIFT
      end

      it 'adds new adapter to list' do
        generator.send(:update_registration_file, adapter_dir)
        content = File.read(registration_file)
        expect(content).to include('NewViewViewAdapter()')
        expect(content).to include('HomeViewAdapter()')
      end
    end

    context 'when adapter is already registered' do
      before do
        File.write(registration_file, <<~SWIFT)
          let adapters: [CustomComponentAdapter] = [
              NewViewViewAdapter()
          ]
        SWIFT
      end

      it 'does not duplicate adapter' do
        generator.send(:update_registration_file, adapter_dir)
        content = File.read(registration_file)
        expect(content.scan('NewViewViewAdapter()').count).to eq(1)
      end
    end
  end

  describe '#get_adapter_directory' do
    context 'with extension_directory' do
      before do
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
          'extension_directory' => 'Extensions'
        })
      end

      it 'returns source_path/Extensions/Adapters' do
        generator = described_class.new('Home')
        dir = generator.send(:get_adapter_directory)
        expect(dir).to eq(File.join(source_path, 'Extensions', 'Adapters'))
      end
    end

    context 'with adapter_directory' do
      before do
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
          'adapter_directory' => 'Custom/Adapters'
        })
      end

      it 'returns source_path/adapter_directory' do
        generator = described_class.new('Home')
        dir = generator.send(:get_adapter_directory)
        expect(dir).to eq(File.join(source_path, 'Custom', 'Adapters'))
      end
    end

    context 'when ProjectFinder returns nil' do
      before do
        allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(nil)
        allow(Dir).to receive(:pwd).and_return(temp_dir)
      end

      it 'falls back to current directory' do
        generator = described_class.new('Home')
        dir = generator.send(:get_adapter_directory)
        expect(dir).to eq(File.join(temp_dir, 'Extensions', 'Adapters'))
      end
    end
  end

  describe 'component type conversion' do
    it 'converts PascalCase to lowercase for component type' do
      generator = described_class.new('HomeScreen')
      template = generator.send(:adapter_template)
      # HomeScreen -> home_screen
      expect(template).to include('componentType: String { "home_screen" }')
    end

    it 'handles single word names' do
      generator = described_class.new('Map')
      template = generator.send(:adapter_template)
      expect(template).to include('componentType: String { "map" }')
    end
  end

  describe 'generated code structure' do
    it 'generates valid Swift struct' do
      generator = described_class.new('Profile')
      template = generator.send(:adapter_template)

      # Check struct declaration
      expect(template).to match(/struct ProfileViewAdapter: CustomComponentAdapter \{/)

      # Check var componentType
      expect(template).to match(/var componentType: String \{ "profile" \}/)

      # Check func buildView
      expect(template).to match(/func buildView\(/)
    end

    it 'passes data to view initializer' do
      generator = described_class.new('Settings')
      template = generator.send(:adapter_template)
      expect(template).to include('SettingsView(data: data)')
    end
  end

  describe 'multiple adapter generation' do
    it 'adds multiple adapters to registration file' do
      # Generate first adapter
      generator1 = described_class.new('Home')
      generator1.generate

      # Generate second adapter
      generator2 = described_class.new('Search')
      generator2.generate

      # Generate third adapter
      generator3 = described_class.new('Profile')
      generator3.generate

      registration_file = File.join(adapter_dir, 'CustomComponentRegistration.swift')
      content = File.read(registration_file)

      expect(content).to include('HomeViewAdapter()')
      expect(content).to include('SearchViewAdapter()')
      expect(content).to include('ProfileViewAdapter()')
    end
  end
end
