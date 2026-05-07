# frozen_string_literal: true

require 'cli/commands/generate'
require 'core/config_manager'
require 'core/project_finder'
require 'fileutils'

RSpec.describe KjuiTools::CLI::Commands::Generate do
  let(:temp_dir) { Dir.mktmpdir('generate_test') }
  let(:layouts_dir) { File.join(temp_dir, 'src/main/assets/Layouts') }

  let(:config) do
    {
      'source_directory' => 'src/main',
      'layouts_directory' => 'assets/Layouts',
      'view_directory' => 'kotlin/com/example/app/views',
      'viewmodel_directory' => 'kotlin/com/example/app/viewmodels',
      'data_directory' => 'kotlin/com/example/app/data',
      'package_name' => 'com.example.app',
      'project_path' => temp_dir,
      'mode' => 'compose'
    }
  end

  before do
    @original_dir = Dir.pwd
    Dir.chdir(temp_dir)
    FileUtils.mkdir_p(layouts_dir)
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
    allow(KjuiTools::Core::ProjectFinder).to receive(:setup_paths)
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
  end

  after do
    Dir.chdir(@original_dir)
    FileUtils.rm_rf(temp_dir)
  end

  describe 'SUBCOMMANDS' do
    it 'includes view subcommand' do
      expect(described_class::SUBCOMMANDS).to have_key('view')
    end

    it 'includes partial subcommand' do
      expect(described_class::SUBCOMMANDS).to have_key('partial')
    end

    it 'includes collection subcommand' do
      expect(described_class::SUBCOMMANDS).to have_key('collection')
    end

    it 'includes cell subcommand' do
      expect(described_class::SUBCOMMANDS).to have_key('cell')
    end

    it 'includes binding subcommand' do
      expect(described_class::SUBCOMMANDS).to have_key('binding')
    end

    it 'includes converter subcommand' do
      expect(described_class::SUBCOMMANDS).to have_key('converter')
    end
  end

  describe '#run' do
    it 'shows help when no subcommand and no JSON files' do
      generate = described_class.new
      expect { generate.run([]) }.not_to raise_error
    end

    it 'shows help with help argument' do
      generate = described_class.new
      expect { generate.run(['help']) }.to output(/Usage:/).to_stdout
    end

    it 'shows help with --help argument' do
      generate = described_class.new
      expect { generate.run(['--help']) }.to output(/Usage:/).to_stdout
    end

    it 'handles unknown subcommand' do
      generate = described_class.new
      # unknown_command that starts with - triggers exit, others are treated as layout names
      expect { generate.run(['-unknown_command']) }.to raise_error(SystemExit)
    end

    context 'with view subcommand' do
      it 'generates a view' do
        generate = described_class.new
        expect { generate.run(['view', 'TestView']) }.to output(/Generated/).to_stdout
      end
    end
  end

  describe 'mode handling' do
    it 'uses compose mode by default' do
      generate = described_class.new
      # Should not raise error
      expect { generate.run([]) }.not_to raise_error
    end

    it 'accepts --mode option' do
      generate = described_class.new
      expect { generate.run(['--mode', 'compose']) }.not_to raise_error
    end

    it 'accepts --mode=value format' do
      generate = described_class.new
      expect { generate.run(['--mode=compose']) }.not_to raise_error
    end

    it 'accepts -m shorthand' do
      generate = described_class.new
      expect { generate.run(['-m', 'compose']) }.not_to raise_error
    end
  end

  describe 'private methods' do
    let(:generate) { described_class.new }

    describe '#parse_global_options' do
      it 'extracts --mode option' do
        args = ['--mode', 'xml', 'view', 'TestView']
        result = generate.send(:parse_global_options, args)
        expect(result[:mode]).to eq('xml')
        expect(args).to eq(['view', 'TestView'])
      end

      it 'extracts --mode=value option' do
        args = ['--mode=xml', 'view', 'TestView']
        result = generate.send(:parse_global_options, args)
        expect(result[:mode]).to eq('xml')
        expect(args).to eq(['view', 'TestView'])
      end

      it 'extracts -m option' do
        args = ['-m', 'compose', 'view']
        result = generate.send(:parse_global_options, args)
        expect(result[:mode]).to eq('compose')
      end

      it 'returns nil mode when not specified' do
        args = ['view', 'TestView']
        result = generate.send(:parse_global_options, args)
        expect(result[:mode]).to be_nil
      end
    end

    describe '#parse_view_options' do
      it 'parses --root flag' do
        args = ['--root']
        result = generate.send(:parse_view_options, args)
        expect(result[:root]).to be true
      end

      it 'parses --mode option' do
        args = ['--mode', 'xml']
        result = generate.send(:parse_view_options, args)
        expect(result[:mode]).to eq('xml')
      end

      it 'parses --type option' do
        args = ['--type', 'activity']
        result = generate.send(:parse_view_options, args)
        expect(result[:type]).to eq('activity')
      end

      it 'parses --activity shorthand' do
        args = ['--activity']
        result = generate.send(:parse_view_options, args)
        expect(result[:type]).to eq('activity')
      end

      it 'parses --fragment shorthand' do
        args = ['--fragment']
        result = generate.send(:parse_view_options, args)
        expect(result[:type]).to eq('fragment')
      end

      it 'parses --force flag' do
        args = ['--force']
        result = generate.send(:parse_view_options, args)
        expect(result[:force]).to be true
      end

      it 'parses -f shorthand for force' do
        args = ['-f']
        result = generate.send(:parse_view_options, args)
        expect(result[:force]).to be true
      end
    end

    describe '#parse_converter_options' do
      it 'parses --container flag' do
        args = ['--container']
        result = generate.send(:parse_converter_options, args)
        expect(result[:is_container]).to be true
      end

      it 'parses --no-container flag' do
        args = ['--no-container']
        result = generate.send(:parse_converter_options, args)
        expect(result[:is_container]).to be false
      end

      it 'parses --attr option' do
        args = ['--attr', 'text:String']
        result = generate.send(:parse_converter_options, args)
        expect(result[:attributes]['text']).to eq('String')
      end

      it 'parses multiple --attr options' do
        args = ['--attr', 'text:String', '--attr', 'count:Int']
        result = generate.send(:parse_converter_options, args)
        expect(result[:attributes]['text']).to eq('String')
        expect(result[:attributes]['count']).to eq('Int')
      end

      it 'parses --binding option' do
        args = ['--binding', 'title:String']
        result = generate.send(:parse_converter_options, args)
        expect(result[:attributes]['@title']).to eq('String')
      end

      it 'parses simplified attribute syntax' do
        args = ['text:String', 'count:Int']
        result = generate.send(:parse_converter_options, args)
        expect(result[:attributes]['text']).to eq('String')
        expect(result[:attributes]['count']).to eq('Int')
      end

      it 'parses binding attribute with @ prefix' do
        args = ['@title:String']
        result = generate.send(:parse_converter_options, args)
        expect(result[:attributes]['@title']).to eq('String')
      end
    end

    describe '#show_help' do
      it 'outputs help text' do
        expect { generate.send(:show_help) }.to output(/Usage:/).to_stdout
        expect { generate.send(:show_help) }.to output(/Subcommands:/).to_stdout
      end
    end
  end

  describe 'subcommand handling' do
    let(:generate) { described_class.new }

    context 'view subcommand' do
      it 'requires view name' do
        expect { generate.run(['view']) }.to raise_error(SystemExit)
      end

      it 'generates view with name' do
        expect { generate.run(['view', 'TestView']) }.to output(/Generated/).to_stdout
      end
    end

    context 'partial subcommand' do
      it 'requires partial name' do
        expect { generate.run(['partial']) }.to raise_error(SystemExit)
      end
    end

    context 'collection subcommand' do
      it 'requires collection name' do
        expect { generate.run(['collection']) }.to raise_error(SystemExit)
      end
    end

    context 'cell subcommand' do
      it 'requires cell name' do
        expect { generate.run(['cell']) }.to raise_error(SystemExit)
      end
    end

    context 'binding subcommand' do
      it 'requires binding name' do
        xml_config = config.merge('mode' => 'xml')
        allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(xml_config)
        expect { generate.run(['binding']) }.to raise_error(SystemExit)
      end

      it 'only works in xml mode' do
        expect { generate.run(['binding', 'TestBinding']) }.to raise_error(SystemExit)
      end
    end

    context 'converter subcommand' do
      it 'requires converter name' do
        expect { generate.run(['converter']) }.to raise_error(SystemExit)
      end

      it 'only works in compose mode' do
        xml_config = config.merge('mode' => 'xml')
        allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(xml_config)
        expect { generate.run(['--mode', 'xml', 'converter', 'MyCard']) }.to raise_error(SystemExit)
      end
    end

    context 'unknown mode' do
      it 'shows error for unknown mode in view' do
        expect { generate.run(['--mode', 'unknown', 'view', 'TestView']) }.to raise_error(SystemExit)
      end

      it 'shows error for unknown mode in collection' do
        expect { generate.run(['--mode', 'unknown', 'collection', 'TestCollection']) }.to raise_error(SystemExit)
      end

      it 'shows error for unknown mode in cell' do
        expect { generate.run(['--mode', 'unknown', 'cell', 'TestCell']) }.to raise_error(SystemExit)
      end
    end

    context 'cell in xml mode' do
      it 'shows error' do
        xml_config = config.merge('mode' => 'xml')
        allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(xml_config)
        expect { generate.run(['--mode', 'xml', 'cell', 'TestCell']) }.to raise_error(SystemExit)
      end
    end

    context 'layout name as subcommand' do
      it 'treats non-subcommand as layout name in compose mode' do
        allow_any_instance_of(described_class).to receive(:generate_specific_compose_layout)
        expect { generate.run(['test_layout']) }.to output(/Building layout/).to_stdout
      end
    end
  end

  describe 'xml mode' do
    let(:xml_config) { config.merge('mode' => 'xml') }

    before do
      allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(xml_config)
    end

    it 'uses xml generator when mode is xml' do
      generate = described_class.new
      allow_any_instance_of(described_class).to receive(:generate_all_xml_layouts)
      expect { generate.run([]) }.not_to raise_error
    end

    it 'generates specific xml layout when layout name given' do
      generate = described_class.new
      allow_any_instance_of(described_class).to receive(:generate_specific_xml_layout) do
        puts "Generating XML for layout: test_layout"
      end
      expect { generate.run(['test_layout']) }.to output(/Generating XML/).to_stdout
    end
  end
end
