# frozen_string_literal: true

require 'cli/commands/destroy'

RSpec.describe SjuiTools::CLI::Commands::Destroy do
  let(:command) { described_class.new }
  let(:temp_dir) { Dir.mktmpdir('destroy_test') }

  before do
    @original_dir = Dir.pwd
    Dir.chdir(temp_dir)

    # Create mock project structure
    FileUtils.mkdir_p('TestApp.xcodeproj')
    FileUtils.mkdir_p('Layouts')
    FileUtils.mkdir_p('View')
    FileUtils.mkdir_p('ViewModel')
    FileUtils.mkdir_p('Data')
    FileUtils.mkdir_p('Bindings')
  end

  after do
    Dir.chdir(@original_dir)
    FileUtils.rm_rf(temp_dir)
  end

  describe '#run' do
    context 'with no arguments' do
      it 'shows help' do
        expect { command.run([]) }.to output(/Usage: sjui destroy TYPE NAME/).to_stdout
      end
    end

    context 'with --help flag' do
      it 'shows help' do
        expect { command.run(['--help']) }.to output(/Usage: sjui destroy TYPE NAME/).to_stdout
      end
    end

    context 'with -h flag' do
      it 'shows help' do
        expect { command.run(['-h']) }.to output(/Usage: sjui destroy TYPE NAME/).to_stdout
      end
    end

    context 'with type but no name' do
      it 'exits with error' do
        expect { command.run(['view']) }.to raise_error(SystemExit)
      end

      it 'shows error message' do
        expect { begin; command.run(['view']); rescue SystemExit; end }.to output(/Please specify a name/).to_stdout
      end
    end

    context 'with unknown type' do
      it 'exits with error' do
        expect { command.run(['unknown', 'test']) }.to raise_error(SystemExit)
      end
    end

    context 'with view type' do
      before do
        allow(SjuiTools::Core::ConfigManager).to receive(:detect_mode).and_return('swiftui')
        allow(command).to receive(:destroy_swiftui_view)
      end

      it 'calls destroy_swiftui_view in swiftui mode' do
        command.run(['view', 'TestView'])
        expect(command).to have_received(:destroy_swiftui_view).with('view', 'TestView', false)
      end

      it 'passes force flag' do
        command.run(['view', 'TestView', '--force'])
        expect(command).to have_received(:destroy_swiftui_view).with('view', 'TestView', true)
      end

      it 'passes force flag with -f' do
        command.run(['view', '-f', 'TestView'])
        expect(command).to have_received(:destroy_swiftui_view).with('view', 'TestView', true)
      end
    end

    context 'with partial type' do
      before do
        allow(SjuiTools::Core::ConfigManager).to receive(:detect_mode).and_return('swiftui')
        allow(command).to receive(:destroy_swiftui_view)
      end

      it 'calls destroy_swiftui_view' do
        command.run(['partial', 'TestPartial'])
        expect(command).to have_received(:destroy_swiftui_view).with('partial', 'TestPartial', false)
      end
    end

    context 'with collection type' do
      before do
        allow(SjuiTools::Core::ConfigManager).to receive(:detect_mode).and_return('swiftui')
        allow(command).to receive(:destroy_swiftui_view)
      end

      it 'calls destroy_swiftui_view' do
        command.run(['collection', 'TestCollection'])
        expect(command).to have_received(:destroy_swiftui_view).with('collection', 'TestCollection', false)
      end
    end

    context 'with uikit_binding type' do
      before do
        allow(SjuiTools::Core::ConfigManager).to receive(:detect_mode).and_return('uikit')
        allow(command).to receive(:destroy_binding)
      end

      it 'calls destroy_binding' do
        command.run(['uikit_binding', 'TestBinding'])
        expect(command).to have_received(:destroy_binding)
      end
    end
  end

  describe '#destroy_swiftui_view (private)' do
    before do
      allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
        'layouts_directory' => 'Layouts',
        'view_directory' => 'View',
        'viewmodel_directory' => 'ViewModel',
        'data_directory' => 'Data',
        'source_directory' => ''
      })
    end

    context 'when no files found' do
      it 'logs warning' do
        expect(SjuiTools::Core::Logger).to receive(:warn).with(/No files found/)
        command.send(:destroy_swiftui_view, 'view', 'nonexistent', true)
      end
    end

    context 'with existing files' do
      before do
        # Create test files
        File.write('Layouts/test_view.json', '{}')
        FileUtils.mkdir_p('View/TestView')
        File.write('View/TestView/TestViewView.swift', '')
        File.write('ViewModel/TestViewViewModel.swift', '')
        File.write('Data/TestViewData.swift', '')
      end

      it 'deletes files with --force' do
        command.send(:destroy_swiftui_view, 'view', 'test_view', true)

        expect(File.exist?('Layouts/test_view.json')).to be false
        expect(Dir.exist?('View/TestView')).to be false
        expect(File.exist?('ViewModel/TestViewViewModel.swift')).to be false
        expect(File.exist?('Data/TestViewData.swift')).to be false
      end
    end

    context 'with nested path' do
      before do
        FileUtils.mkdir_p('Layouts/home')
        File.write('Layouts/home/dashboard.json', '{}')
        FileUtils.mkdir_p('View/home/Dashboard')
        File.write('View/home/Dashboard/DashboardView.swift', '')
      end

      it 'handles nested paths' do
        command.send(:destroy_swiftui_view, 'view', 'home/dashboard', true)

        expect(File.exist?('Layouts/home/dashboard.json')).to be false
        expect(Dir.exist?('View/home/Dashboard')).to be false
      end
    end
  end

  describe '#find_project_root (private)' do
    it 'returns current directory when project file exists' do
      result = command.send(:find_project_root)
      # Use File.realpath to handle macOS /private/var symlink
      expect(File.realpath(result)).to eq(File.realpath(temp_dir))
    end

    it 'returns current directory as fallback' do
      Dir.chdir('/')
      result = command.send(:find_project_root)
      expect(result).to eq('/')
      Dir.chdir(temp_dir)
    end
  end

  describe '#show_help (private)' do
    it 'outputs usage information' do
      expect { command.send(:show_help) }.to output(/Usage: sjui destroy TYPE NAME/).to_stdout
    end

    it 'lists available types' do
      output = capture_stdout { command.send(:show_help) }
      expect(output).to include('view')
      expect(output).to include('partial')
      expect(output).to include('collection')
      expect(output).to include('binding')
    end

    it 'shows examples' do
      expect { command.send(:show_help) }.to output(/Examples:/).to_stdout
    end
  end

  describe '#destroy_view (private for UIKit)' do
    before do
      allow(SjuiTools::Core::ConfigManager).to receive(:detect_mode).and_return('uikit')
      allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
        'layouts_path' => 'Layouts',
        'source_directory' => ''
      })
    end

    context 'when no files exist' do
      it 'outputs message when no files found' do
        expect { command.send(:destroy_view, 'view', 'nonexistent') }.to output(/No files found/).to_stdout
      end
    end

    context 'with existing UIKit files' do
      before do
        FileUtils.mkdir_p('Layouts')
        FileUtils.mkdir_p('View/TestClass')
        FileUtils.mkdir_p('Bindings')
        File.write('Layouts/test_class.json', '{}')
        File.write('Bindings/TestClassBinding.swift', '')
        File.write('View/TestClass/TestClassViewController.swift', '')
      end

      it 'lists files to delete' do
        allow(STDIN).to receive(:gets).and_return('n')
        expect { command.send(:destroy_view, 'view', 'test_class') }.to output(/will be deleted/).to_stdout
      end
    end
  end

  describe '#destroy_binding (private)' do
    before do
      allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
        'source_directory' => ''
      })
    end

    context 'when binding file does not exist' do
      it 'outputs not found message' do
        expect { command.send(:destroy_binding, 'nonexistent') }.to output(/not found/).to_stdout
      end
    end

    context 'when binding file exists' do
      before do
        FileUtils.mkdir_p('Bindings')
        File.write('Bindings/TestBinding.swift', '')
      end

      it 'lists file to delete' do
        allow(STDIN).to receive(:gets).and_return('n')
        expect { command.send(:destroy_binding, 'test') }.to output(/will be deleted/).to_stdout
      end
    end
  end

  describe '#update_xcode_project (private)' do
    it 'handles missing xcodeproj gracefully' do
      FileUtils.rm_rf('TestApp.xcodeproj')
      expect { command.send(:update_xcode_project, ['/some/path']) }.not_to raise_error
    end
  end

  private

  def capture_stdout
    original_stdout = $stdout
    $stdout = StringIO.new
    yield
    $stdout.string
  ensure
    $stdout = original_stdout
  end
end
