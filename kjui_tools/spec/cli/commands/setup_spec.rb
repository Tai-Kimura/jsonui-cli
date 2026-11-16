# frozen_string_literal: true

require 'cli/commands/setup'
require 'core/config_manager'
require 'core/project_finder'

RSpec.describe KjuiTools::CLI::Commands::Setup do
  let(:setup) { described_class.new }
  let(:temp_dir) { Dir.mktmpdir }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:setup_paths)
    allow(KjuiTools::Core::ProjectFinder).to receive(:project_file_path).and_return(temp_dir)
    # Prevent actual setup from running
    allow(setup).to receive(:setup_compose_project)
    allow(setup).to receive(:setup_xml_project)
    allow(setup).to receive(:ensure_dependencies_installed)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#run' do
    it 'runs in compose mode by default' do
      allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
      expect(setup).to receive(:setup_compose_project)
      expect { setup.run([]) }.to output(/Setting up KotlinJsonUI project in compose mode/).to_stdout
    end

    it 'runs in xml mode when configured' do
      allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({ 'mode' => 'xml' })
      expect(setup).to receive(:setup_xml_project)
      expect { setup.run([]) }.to output(/Setting up KotlinJsonUI project in xml mode/).to_stdout
    end

    it 'runs both modes when set to all' do
      allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({ 'mode' => 'all' })
      expect(setup).to receive(:setup_xml_project)
      expect(setup).to receive(:setup_compose_project)
      expect { setup.run([]) }.to output(/Setting up KotlinJsonUI project in all mode/).to_stdout
    end

    it 'outputs setup complete message' do
      expect { setup.run([]) }.to output(/Setup complete!/).to_stdout
    end

    it 'outputs next steps for compose mode' do
      expect { setup.run([]) }.to output(/Create your layouts/).to_stdout
    end

    it 'outputs next steps for xml mode' do
      allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({ 'mode' => 'xml' })
      expect { setup.run([]) }.to output(/Run 'kjui g view HomeView'/).to_stdout
    end
  end

  describe '#parse_options' do
    it 'parses help option and exits' do
      expect { setup.send(:parse_options, ['-h']) }.to raise_error(SystemExit)
    end

    it 'parses --help option and exits' do
      expect { setup.send(:parse_options, ['--help']) }.to raise_error(SystemExit)
    end

    it 'returns empty options for no args' do
      result = setup.send(:parse_options, [])
      expect(result).to eq({})
    end
  end
end
