# frozen_string_literal: true

require 'spec_helper'
require 'cli/commands/generate'
require 'core/config_manager'
require 'core/project_finder'
require 'core/logger'

RSpec.describe SjuiTools::CLI::Commands::Generate do
  let(:command) { described_class.new }

  before do
    allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
    allow(SjuiTools::Core::ProjectFinder).to receive(:find_project_file).and_return('/mock/project.xcodeproj')
  end

  describe '#run' do
    it 'shows help when no subcommand provided' do
      expect { command.run([]) }.to output(/Usage: sjui generate SUBCOMMAND/).to_stdout
    end

    it 'shows help for unknown subcommand' do
      expect { command.run(['unknown']) }.to output(/Unknown generate command/).to_stdout
      .and raise_error(SystemExit)
    end
  end

  describe '#generate_view (private)' do
    before do
      allow(SjuiTools::Core::ConfigManager).to receive(:detect_mode).and_return('uikit')
    end

    it 'requires view name' do
      expect { command.send(:generate_view, [], 'uikit') }.to output(/View name is required/).to_stdout
      .and raise_error(SystemExit)
    end

    context 'with valid view name' do
      it 'calls UIKit generator' do
        # Stub the require to avoid loading the actual file
        allow(command).to receive(:require_relative)

        # Create a mock module structure
        stub_const('SjuiTools::UIKit', Module.new)
        stub_const('SjuiTools::UIKit::XcodeProject', Module.new)
        stub_const('SjuiTools::UIKit::XcodeProject::Generators', Module.new)

        mock_generator = double('ViewGenerator')
        expect(mock_generator).to receive(:generate)

        view_generator_class = double('ViewGeneratorClass')
        expect(view_generator_class).to receive(:new).with('TestView', hash_including(root: false)).and_return(mock_generator)
        stub_const('SjuiTools::UIKit::XcodeProject::Generators::ViewGenerator', view_generator_class)

        command.send(:generate_view, ['TestView'], 'uikit')
      end
    end
  end

  describe '#generate_partial (private)' do
    before do
      allow(SjuiTools::Core::ConfigManager).to receive(:detect_mode).and_return('uikit')
    end

    it 'requires partial name' do
      expect { command.send(:generate_partial, [], 'uikit') }.to output(/Partial name is required/).to_stdout
      .and raise_error(SystemExit)
    end
  end

  describe '#generate_collection (private)' do
    before do
      allow(SjuiTools::Core::ConfigManager).to receive(:detect_mode).and_return('uikit')
    end

    it 'requires collection name' do
      expect { command.send(:generate_collection, [], 'uikit') }.to output(/Collection name is required/).to_stdout
      .and raise_error(SystemExit)
    end
  end

  describe '#generate_binding (private)' do
    it 'requires binding name' do
      expect { command.send(:generate_binding, [], 'uikit') }.to output(/Binding name is required/).to_stdout
      .and raise_error(SystemExit)
    end

    it 'only works in UIKit mode' do
      expect { command.send(:generate_binding, ['TestBinding'], 'swiftui') }
        .to output(/only available in UIKit mode/).to_stdout
        .and raise_error(SystemExit)
    end
  end

  describe '#generate_converter (private)' do
    context 'without name' do
      it 'exits with error' do
        expect { command.send(:generate_converter, [], 'swiftui') }.to raise_error(SystemExit)
      end
    end

    context 'with UIKit mode' do
      let(:temp_dir) { File.join(Dir.tmpdir, 'sjui_test_uikit_converter') }
      # The converter generator writes handlers into sjui_tools/lib/uikit/handlers/extensions
      # when it detects a 'sjui_tools' directory beside the cwd (test-app layout).
      let(:handlers_dir) { File.join(temp_dir, 'sjui_tools', 'lib', 'uikit', 'handlers', 'extensions') }
      let(:config_file) { File.join(temp_dir, 'sjui.config.json') }

      before do
        # Eager-load the UIKit converter generator so the constant is defined
        # before allow_any_instance_of is evaluated below.
        require 'uikit/xcode_project/generators/converter_generator'

        FileUtils.mkdir_p(File.join(temp_dir, 'sjui_tools'))
        FileUtils.mkdir_p(handlers_dir)

        # Change to temp directory
        @original_dir = Dir.pwd
        Dir.chdir(temp_dir)

        # Mock ConfigManager and Logger
        allow(SjuiTools::Core::ConfigManager).to receive(:find_config_file).and_return(config_file)
        allow(SjuiTools::Core::Logger).to receive(:info)
        allow(SjuiTools::Core::Logger).to receive(:success)
        allow(SjuiTools::Core::Logger).to receive(:warn)
      end

      after do
        Dir.chdir(@original_dir)
        FileUtils.rm_rf(temp_dir)
      end

      it 'generates UIKit converter successfully' do
        # Mock user input for overwrite prompt
        allow_any_instance_of(SjuiTools::UIKit::XcodeProject::Generators::ConverterGenerator)
          .to receive(:gets).and_return("y\n")

        command.send(:generate_converter, ['TestConverter'], 'uikit')

        # Check that handler file was created
        handler_file = File.join(handlers_dir, 'test_converter_binding_handler.rb')
        expect(File.exist?(handler_file)).to be true
      end
    end

    context 'with SwiftUI mode' do
      it 'calls SwiftUI generator' do
        # Stub the require to avoid loading the actual file
        allow(command).to receive(:require_relative)

        mock_generator = double('ConverterGenerator')
        expect(mock_generator).to receive(:generate)

        converter_generator_class = double('ConverterGeneratorClass')
        expect(converter_generator_class).to receive(:new).with('TestConverter', hash_including(attributes: {})).and_return(mock_generator)
        stub_const('SjuiTools::SwiftUI::Generators::ConverterGenerator', converter_generator_class)

        command.send(:generate_converter, ['TestConverter'], 'swiftui')
      end
    end

    context 'with unknown mode' do
      it 'exits with error' do
        expect { command.send(:generate_converter, ['TestConverter'], 'unknown') }
          .to output(/Unknown mode/).to_stdout
          .and raise_error(SystemExit)
      end
    end
  end

  describe '#parse_view_options (private)' do
    it 'parses --root option' do
      options = command.send(:parse_view_options, ['--root'])
      expect(options[:root]).to be true
    end

    it 'parses --mode option' do
      options = command.send(:parse_view_options, ['--mode', 'swiftui'])
      expect(options[:mode]).to eq('swiftui')
    end

    it 'returns default options' do
      options = command.send(:parse_view_options, [])
      expect(options[:root]).to be false
      expect(options[:mode]).to be_nil
    end
  end

  describe '#parse_converter_options (private)' do
    it 'parses --attributes option' do
      options = command.send(:parse_converter_options, ['--attributes', 'text:String,count:Int'])
      expect(options[:attributes]).to eq({ 'text' => 'String', 'count' => 'Int' })
    end

    it 'keeps a comma-bearing closure type as one attribute (regression: jui-generate-converter-comma-in-prop-type-breaks-attributes)' do
      options = command.send(:parse_converter_options,
                             ['--attributes', 'onRangeChange:((String, String) -> Void)?,title:String'])
      expect(options[:attributes]).to eq(
        'onRangeChange' => '((String, String) -> Void)?',
        'title' => 'String'
      )
    end

    it 'parses --container option' do
      options = command.send(:parse_converter_options, ['--container'])
      expect(options[:is_container]).to be true
    end

    it 'parses --no-container option' do
      options = command.send(:parse_converter_options, ['--no-container'])
      expect(options[:is_container]).to be false
    end

    it 'parses --class-name option' do
      options = command.send(:parse_converter_options, ['--class-name', 'CustomView'])
      expect(options[:class_name]).to eq('CustomView')
    end

    it 'parses --import-module option' do
      options = command.send(:parse_converter_options, ['--import-module', 'CustomModule'])
      expect(options[:import_module]).to eq('CustomModule')
    end

    it 'returns default options' do
      options = command.send(:parse_converter_options, [])
      expect(options[:use_default_attributes]).to be true
      expect(options[:attributes]).to eq({})
      expect(options[:is_container]).to be_nil
      expect(options[:class_name]).to be_nil
      expect(options[:import_module]).to be_nil
    end
  end
end
