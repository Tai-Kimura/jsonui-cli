# frozen_string_literal: true

require 'cli/commands/init'
require 'core/config_manager'
require 'core/project_finder'
require 'fileutils'

RSpec.describe KjuiTools::CLI::Commands::Init do
  let(:temp_dir) { Dir.mktmpdir('init_test') }

  before do
    @original_dir = Dir.pwd
    Dir.chdir(temp_dir)
    allow(KjuiTools::Core::ProjectFinder).to receive(:setup_paths)
    allow(KjuiTools::Core::ProjectFinder).to receive(:package_name).and_return('com.example.app')
    allow(KjuiTools::Core::ProjectFinder).to receive(:find_source_directory).and_return('src/main')
    allow(KjuiTools::Core::ConfigManager).to receive(:detect_mode).and_return('compose')
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
      'source_directory' => 'src/main',
      'layouts_directory' => 'assets/Layouts',
      'styles_directory' => 'assets/Styles'
    })
  end

  after do
    Dir.chdir(@original_dir)
    FileUtils.rm_rf(temp_dir)
  end

  describe '#run' do
    context 'in compose mode' do
      it 'creates config file' do
        init = described_class.new
        expect { init.run(['--mode', 'compose']) }.to output(/Initializing KotlinJsonUI/).to_stdout
        expect(File.exist?('kjui.config.json')).to be true
      end

      it 'shows initialization complete message' do
        init = described_class.new
        expect { init.run(['--mode', 'compose']) }.to output(/Initialization complete/).to_stdout
      end

      it 'shows next steps with setup instruction' do
        init = described_class.new
        expect { init.run(['--mode', 'compose']) }.to output(/Run 'kjui setup'/).to_stdout
      end
    end

    context 'in xml mode' do
      it 'creates config file' do
        init = described_class.new
        expect { init.run(['--mode', 'xml']) }.to output(/Initializing KotlinJsonUI/).to_stdout
        expect(File.exist?('kjui.config.json')).to be true
      end

      it 'shows initialization complete' do
        init = described_class.new
        expect { init.run(['--mode', 'xml']) }.to output(/Initialization complete/).to_stdout
      end

      it 'shows next steps message' do
        init = described_class.new
        expect { init.run(['--mode', 'xml']) }.to output(/Next steps/).to_stdout
      end
    end

    context 'when config already exists' do
      before do
        File.write('kjui.config.json', JSON.generate({
          'mode' => 'compose',
          'source_directory' => 'src/main'
        }))
      end

      it 'detects existing config' do
        init = described_class.new
        expect { init.run(['--mode', 'compose']) }.to output(/Config file already exists/).to_stdout
      end
    end

    context 'mode detection' do
      it 'uses compose mode by default' do
        init = described_class.new
        expect { init.run([]) }.to output(/compose mode/).to_stdout
      end
    end
  end

  describe 'option parsing' do
    it 'accepts --mode option' do
      init = described_class.new
      expect { init.run(['--mode', 'compose']) }.to output(/Initialization complete/).to_stdout
    end

    it 'shows help with --help' do
      init = described_class.new
      expect { init.run(['--help']) }.to raise_error(SystemExit)
    end
  end
end
