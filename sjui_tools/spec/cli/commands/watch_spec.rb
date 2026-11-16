# frozen_string_literal: true

require 'cli/commands/watch'

RSpec.describe SjuiTools::CLI::Commands::Watch do
  let(:command) { described_class.new }
  let(:temp_dir) { Dir.mktmpdir('watch_test') }

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#run' do
    context 'with --help flag' do
      it 'shows help and exits' do
        expect { command.run(['--help']) }.to raise_error(SystemExit)
      end
    end

    context 'when project not found' do
      before do
        allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(false)
      end

      it 'exits with error' do
        expect { command.run([]) }.to raise_error(SystemExit)
      end

      it 'shows error message' do
        expect { begin; command.run([]); rescue SystemExit; end }.to output(/Could not find project file/).to_stdout
      end
    end

    context 'with --mode option' do
      before do
        allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
        allow(command).to receive(:watch_uikit)
        allow(command).to receive(:watch_swiftui)
      end

      it 'accepts swiftui mode' do
        expect { command.run(['--mode', 'swiftui']) }.to output(/Starting watch mode \(swiftui\)/).to_stdout
        expect(command).to have_received(:watch_swiftui)
      end

      it 'accepts uikit mode' do
        expect { command.run(['--mode', 'uikit']) }.to output(/Starting watch mode \(uikit\)/).to_stdout
        expect(command).to have_received(:watch_uikit)
      end

      it 'accepts all mode' do
        expect { command.run(['--mode', 'all']) }.to output(/Starting watch mode \(all\)/).to_stdout
        expect(command).to have_received(:watch_uikit)
      end
    end

    context 'with unknown mode' do
      before do
        allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
        allow(SjuiTools::Core::ConfigManager).to receive(:detect_mode).and_return('unknown')
      end

      it 'exits with error' do
        expect { command.run([]) }.to raise_error(SystemExit)
      end
    end

    context 'with detected mode' do
      before do
        allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
        allow(command).to receive(:watch_uikit)
        allow(command).to receive(:watch_swiftui)
      end

      it 'uses detected swiftui mode' do
        allow(SjuiTools::Core::ConfigManager).to receive(:detect_mode).and_return('swiftui')
        expect { command.run([]) }.to output(/Starting watch mode \(swiftui\)/).to_stdout
        expect(command).to have_received(:watch_swiftui)
      end

      it 'uses detected uikit mode' do
        allow(SjuiTools::Core::ConfigManager).to receive(:detect_mode).and_return('uikit')
        expect { command.run([]) }.to output(/Starting watch mode \(uikit\)/).to_stdout
        expect(command).to have_received(:watch_uikit)
      end
    end
  end

  describe '#watch_swiftui (private)' do
    it 'outputs not implemented message' do
      expect { command.send(:watch_swiftui) }.to output(/SwiftUI watch mode not yet implemented/).to_stdout
    end
  end

  describe '#watch_uikit (private)' do
    before do
      allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
        'layouts_directory' => 'Layouts',
        'styles_directory' => 'Styles'
      })
      allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)

      FileUtils.mkdir_p(File.join(temp_dir, 'Layouts'))
      FileUtils.mkdir_p(File.join(temp_dir, 'Styles'))
    end

    it 'runs initial build' do
      require 'uikit/json_loader'

      loader = instance_double(SjuiTools::UIKit::JsonLoader)
      allow(SjuiTools::UIKit::JsonLoader).to receive(:new).and_return(loader)
      allow(loader).to receive(:start_analyze)

      watcher = instance_double(SjuiTools::Core::FileWatcher)
      allow(SjuiTools::Core::FileWatcher).to receive(:new).and_return(watcher)
      allow(watcher).to receive(:start)
      allow(watcher).to receive(:stop)

      # Simulate Ctrl+C after a moment
      thread = Thread.new do
        sleep 0.1
        Thread.main.raise(Interrupt)
      end

      expect { command.send(:watch_uikit) }.to output(/Running initial build/).to_stdout

      thread.join
    end
  end
end
