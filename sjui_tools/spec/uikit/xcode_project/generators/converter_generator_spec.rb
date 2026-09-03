# frozen_string_literal: true

require 'spec_helper'
require 'uikit/xcode_project/generators/converter_generator'
require 'core/config_manager'
require 'fileutils'
require 'json'

RSpec.describe SjuiTools::UIKit::XcodeProject::Generators::ConverterGenerator do
  # One directory per example (`Dir.mktmpdir`), never a fixed name: with
  # `Dir.tmpdir/sjui_converter_test` two rspec processes (the 3.3 and 2.6
  # suites side by side) shared the path and each `after { rm_rf }` deleted
  # the other's files — 5 of 5 concurrent pairs red, 2026-09-03. realpath,
  # because the spec chdirs here and macOS's /var is a symlink to /private/var.
  let(:temp_dir) { File.realpath(Dir.mktmpdir('sjui_converter_test')) }
  # Generator writes handler files to handlers/extensions (new layout) within the test app structure
  # when the current directory contains a `sjui_tools` subdirectory.
  let(:handlers_dir) { File.join(temp_dir, 'sjui_tools', 'lib', 'uikit', 'handlers', 'extensions') }
  let(:attr_defs_dir) { File.join(temp_dir, 'sjui_tools', 'lib', 'uikit', 'extensions', 'attribute_definitions') }
  let(:config_file) { File.join(temp_dir, 'sjui.config.json') }

  before do
    # Create temporary directory structure matching the "test app" layout so the
    # generator takes the `sjui_tools/...` branch when resolving output paths.
    FileUtils.mkdir_p(File.join(temp_dir, 'sjui_tools'))
    FileUtils.mkdir_p(handlers_dir)
    FileUtils.mkdir_p(attr_defs_dir)

    # Change to temp directory
    @original_dir = Dir.pwd
    Dir.chdir(temp_dir)

    # Mock ConfigManager
    allow(SjuiTools::Core::ConfigManager).to receive(:find_config_file).and_return(config_file)
  end

  after do
    # Restore original directory
    Dir.chdir(@original_dir)
    # Clean up
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'sets up the generator with correct naming' do
      generator = described_class.new('MyCustomView')
      expect(generator.instance_variable_get(:@component_pascal_case)).to eq('MyCustomView')
      expect(generator.instance_variable_get(:@class_name)).to eq('MyCustomViewBindingHandler')
    end

    it 'builds command string correctly with attributes' do
      options = { attributes: { 'title' => 'String', 'count' => 'Int' } }
      generator = described_class.new('MyCustomView', options)
      command = generator.instance_variable_get(:@command)
      expect(command).to include('sjui g converter MyCustomView')
      expect(command).to include('--attributes=')
      expect(command).to include('title:String')
      expect(command).to include('count:Int')
    end

    it 'builds command string correctly with import module' do
      options = { import_module: 'CustomModule' }
      generator = described_class.new('MyCustomView', options)
      command = generator.instance_variable_get(:@command)
      expect(command).to include('--import-module=CustomModule')
    end
  end

  describe '#generate' do
    let(:generator) { described_class.new('MyCustomView') }

    before do
      # Stub user input for overwrite prompts
      allow(generator).to receive(:gets).and_return("y\n")
      # Stub logger to avoid output during tests
      allow(SjuiTools::Core::Logger).to receive(:info)
      allow(SjuiTools::Core::Logger).to receive(:success)
      allow(SjuiTools::Core::Logger).to receive(:warn)
    end

    it 'creates binding handler file' do
      generator.generate
      handler_file = File.join(handlers_dir, 'my_custom_view_binding_handler.rb')
      expect(File.exist?(handler_file)).to be true
    end

    it 'generates correct binding handler content' do
      generator.generate
      handler_file = File.join(handlers_dir, 'my_custom_view_binding_handler.rb')
      content = File.read(handler_file)

      expect(content).to include('class MyCustomViewBindingHandler < ViewBindingHandler')
      expect(content).to include('def handle_specific_binding(view_name, key, value)')
      expect(content).to include('Generator: sjui g converter MyCustomView')
    end

    it 'creates the attribute definition file' do
      generator.generate
      attr_file = File.join(attr_defs_dir, 'my_custom_view.json')
      expect(File.exist?(attr_file)).to be true
    end

    it 'writes MyCustomView key into attribute definition file' do
      generator.generate
      attr_file = File.join(attr_defs_dir, 'my_custom_view.json')
      json = JSON.parse(File.read(attr_file))
      expect(json).to have_key('MyCustomView')
    end

    it 'creates or updates config file' do
      generator.generate
      expect(File.exist?(config_file)).to be true
    end

    it 'adds custom_view_types to config' do
      generator.generate
      config = JSON.parse(File.read(config_file))
      expect(config['custom_view_types']).to have_key('MyCustomView')
      expect(config['custom_view_types']['MyCustomView']['class_name']).to eq('MyCustomView')
    end

    context 'with attributes' do
      let(:options) { { attributes: { 'title' => 'String', 'isEnabled' => 'Bool' } } }
      let(:generator) { described_class.new('MyCustomView', options) }

      it 'generates binding handler with attribute cases' do
        generator.generate
        handler_file = File.join(handlers_dir, 'my_custom_view_binding_handler.rb')
        content = File.read(handler_file)

        expect(content).to include('when "title"')
        expect(content).to include('when "isEnabled"')
      end

      it 'adds attributes to config' do
        generator.generate
        config = JSON.parse(File.read(config_file))
        expect(config['custom_view_types']['MyCustomView']['attributes']).to eq(options[:attributes])
      end
    end

    context 'with import module' do
      let(:options) { { import_module: 'CustomModule' } }
      let(:generator) { described_class.new('MyCustomView', options) }

      it 'adds import_module to config' do
        generator.generate
        config = JSON.parse(File.read(config_file))
        expect(config['custom_view_types']['MyCustomView']['import_module']).to eq('CustomModule')
      end
    end

    context 'with custom class name' do
      let(:options) { { class_name: 'CustomUIView' } }
      let(:generator) { described_class.new('MyCustomView', options) }

      it 'uses custom class name in config' do
        generator.generate
        config = JSON.parse(File.read(config_file))
        expect(config['custom_view_types']['MyCustomView']['class_name']).to eq('CustomUIView')
      end
    end
  end

  describe '#snake_case' do
    let(:generator) { described_class.new('MyCustomView') }

    it 'converts PascalCase to snake_case' do
      expect(generator.send(:snake_case, 'MyCustomView')).to eq('my_custom_view')
    end

    it 'handles single word' do
      expect(generator.send(:snake_case, 'Button')).to eq('button')
    end

    it 'handles consecutive capitals' do
      expect(generator.send(:snake_case, 'HTTPRequest')).to eq('http_request')
    end
  end

  describe '#to_camel_case' do
    let(:generator) { described_class.new('MyCustomView') }

    it 'converts snake_case to camelCase' do
      expect(generator.send(:to_camel_case, 'my_property')).to eq('myProperty')
    end

    it 'converts kebab-case to camelCase' do
      expect(generator.send(:to_camel_case, 'my-property')).to eq('myProperty')
    end

    it 'handles single word' do
      expect(generator.send(:to_camel_case, 'property')).to eq('property')
    end

    it 'preserves already camelCase' do
      expect(generator.send(:to_camel_case, 'myProperty')).to eq('myProperty')
    end
  end

  describe 'integration with existing handlers' do
    it 'does not duplicate config entries when generated twice' do
      generator = described_class.new('MyCustomView')
      allow(generator).to receive(:gets).and_return("y\n")
      allow(SjuiTools::Core::Logger).to receive(:info)
      allow(SjuiTools::Core::Logger).to receive(:success)
      allow(SjuiTools::Core::Logger).to receive(:warn)

      # Generate once
      generator.generate

      # Generate again with same name
      generator2 = described_class.new('MyCustomView')
      allow(generator2).to receive(:gets).and_return("y\n")
      generator2.generate

      # custom_view_types should still have a single entry for MyCustomView.
      config = JSON.parse(File.read(config_file))
      expect(config['custom_view_types'].keys.count { |k| k == 'MyCustomView' }).to eq(1)
    end
  end
end
