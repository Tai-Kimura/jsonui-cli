# frozen_string_literal: true

require 'cli/commands/setup'

RSpec.describe SjuiTools::CLI::Commands::Setup do
  let(:command) { described_class.new }
  let(:temp_dir) { Dir.mktmpdir('setup_test') }
  let(:project_path) { File.join(temp_dir, 'TestApp.xcodeproj') }

  before do
    FileUtils.mkdir_p(project_path)
  end

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
        allow(command).to receive(:ensure_dependencies_installed)
      end

      it 'exits with error' do
        expect { command.run([]) }.to raise_error(SystemExit)
      end

      it 'shows error message' do
        expect { begin; command.run([]); rescue SystemExit; end }.to output(/Could not find project file/).to_stdout
      end
    end

    context 'when no xcodeproj found' do
      before do
        allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
        allow(SjuiTools::Core::ProjectFinder).to receive(:project_file_path).and_return(nil)
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({ 'mode' => 'swiftui' })
        allow(command).to receive(:ensure_dependencies_installed)
      end

      it 'exits with error' do
        expect { command.run([]) }.to raise_error(SystemExit)
      end
    end

    context 'with swiftui mode' do
      before do
        allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
        allow(SjuiTools::Core::ProjectFinder).to receive(:project_file_path).and_return(project_path)
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({ 'mode' => 'swiftui' })
        allow(command).to receive(:ensure_dependencies_installed)
        allow(command).to receive(:setup_swiftui_project)
      end

      it 'runs swiftui setup' do
        expect { command.run([]) }.to output(/Setting up SwiftJsonUI project in swiftui mode/).to_stdout
        expect(command).to have_received(:setup_swiftui_project)
      end

      it 'shows completion message' do
        expect { command.run([]) }.to output(/Setup complete!/).to_stdout
      end

      it 'shows swiftui-specific next steps' do
        expect { command.run([]) }.to output(/Run 'sjui convert' to generate SwiftUI code/).to_stdout
      end
    end

    context 'with uikit mode' do
      before do
        allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
        allow(SjuiTools::Core::ProjectFinder).to receive(:project_file_path).and_return(project_path)
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({ 'mode' => 'uikit' })
        allow(command).to receive(:ensure_dependencies_installed)
        allow(command).to receive(:setup_uikit_project)
      end

      it 'runs uikit setup' do
        expect { command.run([]) }.to output(/Setting up SwiftJsonUI project in uikit mode/).to_stdout
        expect(command).to have_received(:setup_uikit_project)
      end

      it 'shows uikit-specific next steps' do
        expect { command.run([]) }.to output(/Run 'sjui g view HomeView' to generate your first view/).to_stdout
      end
    end

    context 'with all mode' do
      before do
        allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
        allow(SjuiTools::Core::ProjectFinder).to receive(:project_file_path).and_return(project_path)
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({ 'mode' => 'all' })
        allow(command).to receive(:ensure_dependencies_installed)
        allow(command).to receive(:setup_uikit_project)
        allow(command).to receive(:setup_swiftui_project)
      end

      it 'runs both uikit and swiftui setup' do
        command.run([])
        expect(command).to have_received(:setup_uikit_project)
        expect(command).to have_received(:setup_swiftui_project)
      end
    end

    context 'with default mode' do
      before do
        allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
        allow(SjuiTools::Core::ProjectFinder).to receive(:project_file_path).and_return(project_path)
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
        allow(command).to receive(:ensure_dependencies_installed)
        allow(command).to receive(:setup_uikit_project)
      end

      it 'defaults to uikit mode' do
        expect { command.run([]) }.to output(/Setting up SwiftJsonUI project in uikit mode/).to_stdout
      end
    end
  end

  describe '#ensure_dependencies_installed (private)' do
    # This method checks for Gemfile.lock and runs bundle install if needed
    # The actual implementation uses Dir.chdir and system calls which are
    # difficult to test in isolation. We'll test the behavior indirectly.

    it 'is callable' do
      # Just verify the method exists and is callable
      # The actual bundle install is not run in test environment since Gemfile.lock exists
      expect { command.send(:ensure_dependencies_installed) }.not_to raise_error
    end
  end
end
