# frozen_string_literal: true

require 'core/config_manager'
require 'tempfile'
require 'json'

RSpec.describe SjuiTools::Core::ConfigManager do
  describe '.load_config' do
    context 'with no config file' do
      before do
        allow(described_class).to receive(:find_config_file).and_return(nil)
      end

      it 'returns default configuration' do
        config = described_class.load_config

        expect(config['mode']).to eq('uikit')
        expect(config['layouts_directory']).to eq('Layouts')
        expect(config['bindings_directory']).to eq('Bindings')
        expect(config['view_directory']).to eq('View')
        expect(config['styles_directory']).to eq('Styles')
      end

      it 'includes swiftui defaults' do
        config = described_class.load_config

        expect(config['swiftui']['output_directory']).to eq('Generated')
      end
    end

    context 'with valid config file' do
      it 'merges with defaults' do
        Tempfile.create(['sjui.config', '.json']) do |file|
          file.write(JSON.generate({
            'mode' => 'swiftui',
            'project_name' => 'TestProject'
          }))
          file.rewind

          config = described_class.load_config(file.path)

          expect(config['mode']).to eq('swiftui')
          expect(config['project_name']).to eq('TestProject')
          # Defaults should still be present
          expect(config['layouts_directory']).to eq('Layouts')
        end
      end
    end

    context 'with invalid JSON config' do
      it 'falls back to defaults with warning' do
        Tempfile.create(['sjui.config', '.json']) do |file|
          file.write('{ invalid json }')
          file.rewind

          expect {
            config = described_class.load_config(file.path)
            expect(config['mode']).to eq('uikit')
          }.to output(/Warning/).to_stdout
        end
      end
    end
  end

  describe 'getter methods' do
    before do
      allow(described_class).to receive(:load_config).and_return({
        'mode' => 'swiftui',
        'source_directory' => 'Sources',
        'layouts_directory' => 'Layouts',
        'bindings_directory' => 'Bindings',
        'view_directory' => 'View',
        'styles_directory' => 'Styles',
        'project_file_name' => 'TestProject',
        'custom_view_types' => { 'CustomView' => 'View' },
        'use_network' => false
      })
    end

    describe '.get_source_directory' do
      it 'returns source directory' do
        expect(described_class.get_source_directory).to eq('Sources')
      end
    end

    describe '.get_layouts_directory' do
      it 'returns layouts directory' do
        expect(described_class.get_layouts_directory).to eq('Layouts')
      end
    end

    describe '.get_bindings_directory' do
      it 'returns bindings directory' do
        expect(described_class.get_bindings_directory).to eq('Bindings')
      end
    end

    describe '.get_view_directory' do
      it 'returns view directory' do
        expect(described_class.get_view_directory).to eq('View')
      end
    end

    describe '.get_styles_directory' do
      it 'returns styles directory' do
        expect(described_class.get_styles_directory).to eq('Styles')
      end
    end

    describe '.get_project_file_name' do
      it 'returns project file name' do
        expect(described_class.get_project_file_name).to eq('TestProject')
      end
    end

    describe '.get_custom_view_types' do
      it 'returns custom view types hash' do
        expect(described_class.get_custom_view_types).to eq({ 'CustomView' => 'View' })
      end
    end

    describe '.get_use_network' do
      it 'returns use_network setting' do
        expect(described_class.get_use_network).to eq(false)
      end
    end

  end

  describe '.get_bindings_path' do
    context 'with source directory' do
      before do
        allow(described_class).to receive(:load_config).and_return({
          'source_directory' => 'Sources',
          'bindings_directory' => 'Bindings'
        })
      end

      it 'returns path including source directory' do
        path = described_class.get_bindings_path('/project')
        expect(path).to eq('/project/Sources/Bindings')
      end
    end

    context 'without source directory' do
      before do
        allow(described_class).to receive(:load_config).and_return({
          'source_directory' => '',
          'bindings_directory' => 'Bindings'
        })
      end

      it 'returns path without source directory' do
        path = described_class.get_bindings_path('/project')
        expect(path).to eq('/project/Bindings')
      end
    end
  end

  describe '.get_source_path' do
    context 'with source directory' do
      before do
        allow(described_class).to receive(:load_config).and_return({
          'source_directory' => 'Sources'
        })
      end

      it 'returns path including source directory' do
        path = described_class.get_source_path('/project')
        expect(path).to eq('/project/Sources')
      end
    end

    context 'without source directory' do
      before do
        allow(described_class).to receive(:load_config).and_return({
          'source_directory' => ''
        })
      end

      it 'returns parent directory' do
        path = described_class.get_source_path('/project')
        expect(path).to eq('/project')
      end
    end
  end

  describe '.detect_mode' do
    context 'with mode in config' do
      before do
        allow(described_class).to receive(:load_config).and_return({
          'mode' => 'swiftui'
        })
      end

      it 'returns configured mode' do
        expect(described_class.detect_mode).to eq('swiftui')
      end
    end

    context 'with Package.swift present' do
      before do
        allow(described_class).to receive(:load_config).and_return({
          'mode' => ''
        })
        allow(File).to receive(:exist?).and_call_original
        allow(File).to receive(:exist?).with(File.join(Dir.pwd, 'Package.swift')).and_return(true)
      end

      it 'auto-detects swiftui mode' do
        expect(described_class.detect_mode).to eq('swiftui')
      end
    end

    context 'without Package.swift' do
      before do
        allow(described_class).to receive(:load_config).and_return({
          'mode' => ''
        })
        allow(File).to receive(:exist?).and_call_original
        allow(File).to receive(:exist?).with(File.join(Dir.pwd, 'Package.swift')).and_return(false)
      end

      it 'defaults to uikit mode' do
        expect(described_class.detect_mode).to eq('uikit')
      end
    end
  end

  describe '.get_hot_loader_directory' do
    context 'with hot_loader_directory configured' do
      before do
        allow(described_class).to receive(:load_config).and_return({
          'hot_loader_directory' => 'CustomHotLoader',
          'project_file_name' => 'TestProject'
        })
      end

      it 'returns configured hot_loader_directory' do
        expect(described_class.get_hot_loader_directory).to eq('CustomHotLoader')
      end
    end

    context 'without hot_loader_directory' do
      before do
        allow(described_class).to receive(:load_config).and_return({
          'hot_loader_directory' => '',
          'project_file_name' => 'TestProject'
        })
      end

      it 'returns project_file_name as fallback' do
        expect(described_class.get_hot_loader_directory).to eq('TestProject')
      end
    end
  end
end
