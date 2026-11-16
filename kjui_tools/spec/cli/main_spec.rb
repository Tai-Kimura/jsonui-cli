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

    # `watch` printed a line and exited 0, so a script that called it was told
    # it had succeeded. It is not coming back — watching is `jui hotload
    # listen` — so it fails, says where to go, and is gone from the list.
    it 'fails rather than reporting success for a command it does not have' do
      expect { described_class.run(['watch']) }.to raise_error(SystemExit) { |e|
        expect(e.status).to eq(1)
      }
    end

    it 'names the command that replaced it, on stderr' do
      expect {
        expect { described_class.run(['watch']) }.to raise_error(SystemExit)
      }.to output(/jui hotload listen/).to_stderr
    end

    it 'treats the w alias the same way' do
      expect {
        expect { described_class.run(['w']) }.to raise_error(SystemExit) { |e|
          expect(e.status).to eq(1)
        }
      }.to output(/jui hotload listen/).to_stderr
    end

    it 'does not advertise watch in the command list' do
      # The list is read as a promise; docs are generated from it.
      expect { described_class.run(['help']) }.to output(/Commands:/).to_stdout
      expect { described_class.run(['help']) }.not_to output(/watch/).to_stdout
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
