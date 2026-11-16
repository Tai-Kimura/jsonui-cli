# frozen_string_literal: true

require 'compose/generators/view_adapter_generator'
require 'core/config_manager'
require 'core/project_finder'
require 'core/logger'
require 'fileutils'
require 'tmpdir'

RSpec.describe KjuiTools::Compose::Generators::ViewAdapterGenerator do
  let(:temp_dir) { Dir.mktmpdir('view_adapter_generator_test') }
  let(:adapter_dir) { File.join(temp_dir, 'src/debug/kotlin/com/example/app/dynamic/components/adapters') }
  let(:registry_dir) { File.join(temp_dir, 'src/debug/kotlin/com/example/app/dynamic') }

  before do
    @original_dir = Dir.pwd
    Dir.chdir(temp_dir)
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
      '_config_dir' => temp_dir,
      'source_directory' => 'src/main',
      'package_name' => 'com.example.app'
    })
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_package_name).and_return('com.example.app')
    allow(KjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
    allow(KjuiTools::Core::Logger).to receive(:info)
    allow(KjuiTools::Core::Logger).to receive(:warn)
    allow(KjuiTools::Core::Logger).to receive(:success)
  end

  after do
    Dir.chdir(@original_dir)
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
    it 'creates adapter directory if it does not exist' do
      generator = described_class.new('Home')
      generator.generate
      expect(Dir.exist?(adapter_dir)).to be true
    end

    it 'creates adapter Kotlin file' do
      generator = described_class.new('Home')
      generator.generate
      adapter_file = File.join(adapter_dir, 'HomeViewAdapter.kt')
      expect(File.exist?(adapter_file)).to be true
    end

    it 'creates DynamicComponentRegistry if it does not exist' do
      generator = described_class.new('Home')
      generator.generate
      registry_file = File.join(registry_dir, 'DynamicComponentRegistry.kt')
      expect(File.exist?(registry_file)).to be true
    end

    it 'returns true on success' do
      generator = described_class.new('Home')
      result = generator.generate
      expect(result).to be true
    end
  end

  describe '#adapter_template' do
    it 'generates template with correct adapter name' do
      generator = described_class.new('Home')
      # Call generate first to set up instance variables
      allow(generator).to receive(:create_adapter_file)
      allow(generator).to receive(:update_registry_file)
      generator.generate
      template = generator.send(:adapter_template)
      expect(template).to include('HomeViewAdapter')
      expect(template).to include('HomeView()')
    end

    it 'generates lowercase component type' do
      generator = described_class.new('Home')
      allow(generator).to receive(:create_adapter_file)
      allow(generator).to receive(:update_registry_file)
      generator.generate
      template = generator.send(:adapter_template)
      expect(template).to include('"home"')
    end

    it 'includes package declaration' do
      generator = described_class.new('Profile')
      allow(generator).to receive(:create_adapter_file)
      allow(generator).to receive(:update_registry_file)
      generator.generate
      template = generator.send(:adapter_template)
      expect(template).to include('package com.example.app.dynamic.components.adapters')
    end

    it 'includes @Composable annotation' do
      generator = described_class.new('Settings')
      allow(generator).to receive(:create_adapter_file)
      allow(generator).to receive(:update_registry_file)
      generator.generate
      template = generator.send(:adapter_template)
      expect(template).to include('@Composable')
    end

    it 'imports the View with subdirectory' do
      generator = described_class.new('Search')
      allow(generator).to receive(:create_adapter_file)
      allow(generator).to receive(:update_registry_file)
      generator.generate
      template = generator.send(:adapter_template)
      expect(template).to include('import com.example.app.views.search.SearchView')
    end
  end

  describe '#to_snake_case' do
    let(:generator) { described_class.new('Test') }

    it 'converts single word to lowercase' do
      result = generator.send(:to_snake_case, 'Home')
      expect(result).to eq('home')
    end

    it 'converts PascalCase to snake_case' do
      result = generator.send(:to_snake_case, 'HomeScreen')
      expect(result).to eq('home_screen')
    end

    it 'handles multiple uppercase letters' do
      result = generator.send(:to_snake_case, 'MyCustomView')
      expect(result).to eq('my_custom_view')
    end

    it 'handles consecutive uppercase letters' do
      result = generator.send(:to_snake_case, 'HTTPServer')
      expect(result).to eq('http_server')
    end
  end

  describe '#update_registry_file' do
    let(:generator) { described_class.new('NewView') }
    let(:registry_file) { File.join(registry_dir, 'DynamicComponentRegistry.kt') }

    context 'when registry file does not exist' do
      it 'creates registry file' do
        generator.generate
        expect(File.exist?(registry_file)).to be true
      end

      it 'includes the new adapter' do
        generator.generate
        content = File.read(registry_file, encoding: 'UTF-8')
        expect(content).to include('NewViewViewAdapter')
      end
    end

    context 'when registry file exists with other adapters' do
      before do
        FileUtils.mkdir_p(registry_dir)
        File.write(registry_file, <<~KOTLIN)
          package com.example.app.dynamic

          import androidx.compose.runtime.Composable
          import com.google.gson.JsonObject
          import com.example.app.dynamic.components.adapters.HomeViewAdapter

          object DynamicComponentRegistry {
              @Composable
              fun createCustomComponent(
                  type: String,
                  json: JsonObject,
                  data: Map<String, Any>
              ): Boolean {
                  return when (type) {
                      "home" -> {
                          HomeViewAdapter.create(json, data)
                          true
                      }
                      else -> false
                  }
              }
          }
        KOTLIN
      end

      it 'adds new adapter to list' do
        generator.generate
        content = File.read(registry_file, encoding: 'UTF-8')
        expect(content).to include('NewViewViewAdapter')
        expect(content).to include('HomeViewAdapter')
      end
    end

    context 'when adapter is already registered' do
      before do
        FileUtils.mkdir_p(registry_dir)
        File.write(registry_file, <<~KOTLIN)
          package com.example.app.dynamic

          import androidx.compose.runtime.Composable
          import com.google.gson.JsonObject
          import com.example.app.dynamic.components.adapters.NewViewViewAdapter

          object DynamicComponentRegistry {
              @Composable
              fun createCustomComponent(
                  type: String,
                  json: JsonObject,
                  data: Map<String, Any>
              ): Boolean {
                  return when (type) {
                      "new_view" -> {
                          NewViewViewAdapter.create(json, data)
                          true
                      }
                      else -> false
                  }
              }
          }
        KOTLIN
      end

      it 'does not duplicate adapter' do
        generator.generate
        content = File.read(registry_file, encoding: 'UTF-8')
        expect(content.scan('NewViewViewAdapter').count).to eq(2) # import + usage
      end
    end
  end

  describe 'multiple adapter generation' do
    it 'adds multiple adapters to registry file' do
      # Generate first adapter
      generator1 = described_class.new('Home')
      generator1.generate

      # Generate second adapter
      generator2 = described_class.new('Search')
      generator2.generate

      # Generate third adapter
      generator3 = described_class.new('Profile')
      generator3.generate

      registry_file = File.join(registry_dir, 'DynamicComponentRegistry.kt')
      content = File.read(registry_file, encoding: 'UTF-8')

      expect(content).to include('HomeViewAdapter')
      expect(content).to include('SearchViewAdapter')
      expect(content).to include('ProfileViewAdapter')
    end
  end

  describe 'generated code structure' do
    it 'generates valid Kotlin object' do
      generator = described_class.new('Profile')
      generator.generate

      adapter_file = File.join(adapter_dir, 'ProfileViewAdapter.kt')
      content = File.read(adapter_file, encoding: 'UTF-8')

      # Check object declaration
      expect(content).to match(/object ProfileViewAdapter \{/)

      # Check create function
      expect(content).to match(/@Composable/)
      expect(content).to match(/fun create\(/)
    end

    it 'calls view without parameters' do
      generator = described_class.new('Settings')
      generator.generate

      adapter_file = File.join(adapter_dir, 'SettingsViewAdapter.kt')
      content = File.read(adapter_file, encoding: 'UTF-8')
      expect(content).to include('SettingsView()')
    end
  end

  describe '#create_dynamic_initializers' do
    let(:debug_initializer_file) { File.join(temp_dir, 'src/debug/kotlin/com/example/app/DynamicComponentInitializer.kt') }
    let(:release_initializer_file) { File.join(temp_dir, 'src/release/kotlin/com/example/app/DynamicComponentInitializer.kt') }

    it 'creates debug DynamicComponentInitializer' do
      generator = described_class.new('Home')
      generator.generate
      expect(File.exist?(debug_initializer_file)).to be true
    end

    it 'creates release DynamicComponentInitializer' do
      generator = described_class.new('Home')
      generator.generate
      expect(File.exist?(release_initializer_file)).to be true
    end

    it 'debug initializer sets customComponentHandler' do
      generator = described_class.new('Home')
      generator.generate
      content = File.read(debug_initializer_file, encoding: 'UTF-8')
      expect(content).to include('Configuration.customComponentHandler')
      expect(content).to include('DynamicComponentRegistry.createCustomComponent')
    end

    it 'release initializer is no-op' do
      generator = described_class.new('Home')
      generator.generate
      content = File.read(release_initializer_file, encoding: 'UTF-8')
      expect(content).to include('fun initialize()')
      expect(content).not_to include('Configuration.customComponentHandler')
    end

    it 'does not overwrite existing initializers' do
      # Create existing initializer
      debug_dir = File.dirname(debug_initializer_file)
      FileUtils.mkdir_p(debug_dir)
      File.write(debug_initializer_file, 'EXISTING CONTENT')

      generator = described_class.new('Home')
      generator.generate

      content = File.read(debug_initializer_file, encoding: 'UTF-8')
      expect(content).to eq('EXISTING CONTENT')
    end
  end
end
