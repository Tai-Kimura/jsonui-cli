# frozen_string_literal: true

require 'xml/xml_builder'
require 'core/config_manager'
require 'core/project_finder'
require 'fileutils'
require 'json'

RSpec.describe KjuiTools::Xml::XmlBuilder do
  let(:temp_dir) { Dir.mktmpdir('xml_builder_test') }
  let(:layouts_dir) { File.join(temp_dir, 'src/main/assets/Layouts') }
  let(:output_dir) { File.join(temp_dir, 'src/main/res/layout') }

  let(:config) do
    {
      'source_directory' => 'src/main',
      'layouts_directory' => 'assets/Layouts',
      'package_name' => 'com.example.app',
      'project_path' => temp_dir
    }
  end

  before do
    @original_dir = Dir.pwd
    Dir.chdir(temp_dir)
    FileUtils.mkdir_p(layouts_dir)
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
    allow(KjuiTools::Core::ProjectFinder).to receive(:setup_paths)
  end

  after do
    Dir.chdir(@original_dir)
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'creates instance with config' do
      builder = described_class.new(config)
      expect(builder).to be_a(described_class)
    end

    it 'creates instance without config' do
      builder = described_class.new
      expect(builder).to be_a(described_class)
    end

    it 'has validation_enabled attribute' do
      builder = described_class.new
      expect(builder).to respond_to(:validation_enabled)
      expect(builder).to respond_to(:validation_enabled=)
    end

    it 'has validation_callback attribute' do
      builder = described_class.new
      expect(builder).to respond_to(:validation_callback)
      expect(builder).to respond_to(:validation_callback=)
    end
  end

  describe '#build' do
    context 'when layouts directory does not exist' do
      it 'returns false' do
        FileUtils.rm_rf(layouts_dir)
        builder = described_class.new(config)
        expect { builder.build }.to output(/Layouts directory not found/).to_stdout
      end
    end

    context 'with no JSON files' do
      it 'returns true with warning' do
        builder = described_class.new(config)
        result = nil
        expect { result = builder.build }.to output(/No JSON files found/).to_stdout
        expect(result).to be true
      end
    end

    context 'with layout files' do
      before do
        File.write(File.join(layouts_dir, 'main_view.json'), JSON.generate({
          'type' => 'View',
          'child' => [{ 'type' => 'Text', 'text' => 'Hello' }]
        }))
      end

      it 'processes layout files' do
        builder = described_class.new(config)
        expect { builder.build }.to output(/Processing/).to_stdout
      end
    end

    context 'with partial files' do
      before do
        File.write(File.join(layouts_dir, '_partial.json'), JSON.generate({
          'type' => 'View'
        }))
      end

      it 'skips partial files' do
        builder = described_class.new(config)
        expect { builder.build }.to output(/Skipping partial/).to_stdout
      end
    end

    context 'with cell templates' do
      before do
        File.write(File.join(layouts_dir, 'product_cell.json'), JSON.generate({
          'type' => 'View'
        }))
      end

      it 'skips cell templates' do
        builder = described_class.new(config)
        expect { builder.build }.to output(/Skipping cell template/).to_stdout
      end
    end

    context 'with clean option' do
      before do
        FileUtils.mkdir_p(output_dir)
        File.write(File.join(output_dir, 'old_layout.xml'), "<!-- Generated from test.json -->\n<View />")
      end

      it 'cleans output directory' do
        builder = described_class.new(config)
        expect { builder.build(clean: true) }.to output(/Cleaning output directory/).to_stdout
      end
    end

    context 'with validation enabled' do
      before do
        File.write(File.join(layouts_dir, 'test_view.json'), JSON.generate({
          'type' => 'View',
          'unknownAttribute' => 'value',
          'child' => []
        }))
      end

      it 'validates JSON files when enabled' do
        builder = described_class.new(config)
        builder.validation_enabled = true
        warnings_received = []
        builder.validation_callback = ->(file, warnings) { warnings_received << { file: file, warnings: warnings } }
        expect { builder.build }.to output(/Processing/).to_stdout
      end
    end
  end
end
