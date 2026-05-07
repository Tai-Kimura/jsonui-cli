# frozen_string_literal: true

require 'cli/main'
require 'cli/version'

RSpec.describe KjuiTools::CLI::Main do
  before do
    # Mock all command classes
    allow(KjuiTools::CLI::Commands::Init).to receive(:new).and_return(double(run: nil))
    allow(KjuiTools::CLI::Commands::Setup).to receive(:new).and_return(double(run: nil))
    allow(KjuiTools::CLI::Commands::Generate).to receive(:new).and_return(double(run: nil))
    allow(KjuiTools::CLI::Commands::Build).to receive(:new).and_return(double(run: nil))
  end

  describe '.run' do
    it 'runs init command' do
      init_instance = double(run: nil)
      allow(KjuiTools::CLI::Commands::Init).to receive(:new).and_return(init_instance)
      expect(init_instance).to receive(:run).with([])
      described_class.run(['init'])
    end

    it 'runs setup command' do
      setup_instance = double(run: nil)
      allow(KjuiTools::CLI::Commands::Setup).to receive(:new).and_return(setup_instance)
      expect(setup_instance).to receive(:run).with([])
      described_class.run(['setup'])
    end

    it 'runs generate command' do
      generate_instance = double(run: nil)
      allow(KjuiTools::CLI::Commands::Generate).to receive(:new).and_return(generate_instance)
      expect(generate_instance).to receive(:run).with(['view', 'Test'])
      described_class.run(['generate', 'view', 'Test'])
    end

    it 'runs g as alias for generate' do
      generate_instance = double(run: nil)
      allow(KjuiTools::CLI::Commands::Generate).to receive(:new).and_return(generate_instance)
      expect(generate_instance).to receive(:run).with(['view', 'Test'])
      described_class.run(['g', 'view', 'Test'])
    end

    it 'runs build command' do
      build_instance = double(run: nil)
      allow(KjuiTools::CLI::Commands::Build).to receive(:new).and_return(build_instance)
      expect(build_instance).to receive(:run).with([])
      described_class.run(['build'])
    end

    it 'runs b as alias for build' do
      build_instance = double(run: nil)
      allow(KjuiTools::CLI::Commands::Build).to receive(:new).and_return(build_instance)
      expect(build_instance).to receive(:run).with([])
      described_class.run(['b'])
    end

    it 'outputs watch not implemented message' do
      expect { described_class.run(['watch']) }.to output(/not yet implemented/).to_stdout
    end

    it 'outputs w as alias for watch' do
      expect { described_class.run(['w']) }.to output(/not yet implemented/).to_stdout
    end

    it 'outputs version' do
      expect { described_class.run(['version']) }.to output(/#{KjuiTools::CLI::VERSION}/).to_stdout
    end

    it 'outputs version for v alias' do
      expect { described_class.run(['v']) }.to output(/version/).to_stdout
    end

    it 'outputs version for --version flag' do
      expect { described_class.run(['--version']) }.to output(/version/).to_stdout
    end

    it 'outputs version for -v flag' do
      expect { described_class.run(['-v']) }.to output(/version/).to_stdout
    end

    it 'shows help for help command' do
      expect { described_class.run(['help']) }.to output(/Usage: kjui/).to_stdout
    end

    it 'shows help for --help flag' do
      expect { described_class.run(['--help']) }.to output(/Commands:/).to_stdout
    end

    it 'shows help for -h flag' do
      expect { described_class.run(['-h']) }.to output(/Examples:/).to_stdout
    end

    it 'shows help for nil command' do
      expect { described_class.run([]) }.to output(/Usage: kjui/).to_stdout
    end

    it 'handles unknown command and exits' do
      expect { described_class.run(['unknown']) }.to output(/Unknown command/).to_stdout.and raise_error(SystemExit)
    end
  end

  describe '.show_help' do
    it 'outputs usage information' do
      expect { described_class.show_help }.to output(/Usage: kjui/).to_stdout
    end

    it 'outputs available commands' do
      expect { described_class.show_help }.to output(/init/).to_stdout
      expect { described_class.show_help }.to output(/generate/).to_stdout
      expect { described_class.show_help }.to output(/build/).to_stdout
    end

    it 'outputs examples' do
      expect { described_class.show_help }.to output(/Examples:/).to_stdout
    end
  end
end
