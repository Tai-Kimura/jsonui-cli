# frozen_string_literal: true

require 'cli/commands/build'

RSpec.describe SjuiTools::CLI::Commands::Build do
  let(:command) { described_class.new }
  let(:temp_dir) { Dir.mktmpdir('build_test') }

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#run' do
    context 'with --help flag' do
      it 'shows help and exits' do
        expect { command.run(['--help']) }.to raise_error(SystemExit)
      end
    end

    context 'with --mode option' do
      before do
        allow(SjuiTools::Core::ConfigManager).to receive(:detect_mode).and_return('swiftui')
        allow(command).to receive(:process_strings_extraction)
        allow(command).to receive(:build_swiftui)
        allow(command).to receive(:build_uikit)
      end

      it 'accepts swiftui mode' do
        command.run(['--mode', 'swiftui'])
        expect(command).to have_received(:build_swiftui)
      end

      it 'accepts uikit mode' do
        command.run(['--mode', 'uikit'])
        expect(command).to have_received(:build_uikit)
      end

      it 'accepts all mode' do
        command.run(['--mode', 'all'])
        expect(command).to have_received(:build_uikit)
        expect(command).to have_received(:build_swiftui)
      end
    end

    context 'with detected mode' do
      before do
        allow(command).to receive(:process_strings_extraction)
        allow(command).to receive(:build_swiftui)
        allow(command).to receive(:build_uikit)
      end

      it 'uses detected swiftui mode' do
        allow(SjuiTools::Core::ConfigManager).to receive(:detect_mode).and_return('swiftui')
        command.run([])
        expect(command).to have_received(:build_swiftui)
        expect(command).not_to have_received(:build_uikit)
      end

      it 'uses detected uikit mode' do
        allow(SjuiTools::Core::ConfigManager).to receive(:detect_mode).and_return('uikit')
        command.run([])
        expect(command).to have_received(:build_uikit)
        expect(command).not_to have_received(:build_swiftui)
      end
    end
  end

  describe '#build_swiftui (private)' do
    before do
      allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
      allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
      allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
        'layouts_directory' => 'Layouts',
        'view_directory' => 'View'
      })

      # Create directories
      FileUtils.mkdir_p(File.join(temp_dir, 'Layouts'))
      FileUtils.mkdir_p(File.join(temp_dir, 'View'))
    end

    context 'when project not found' do
      before do
        allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(false)
      end

      it 'exits with error' do
        expect { command.send(:build_swiftui) }.to raise_error(SystemExit)
      end
    end

    context 'when no JSON files found' do
      it 'logs warning and returns' do
        expect(SjuiTools::Core::Logger).to receive(:warn).with(/No JSON files found/)
        command.send(:build_swiftui)
      end
    end

    context 'with --clean option' do
      before do
        # Load required modules
        require 'swiftui/build_cache_manager'
      end

      it 'cleans cache before building' do
        cache_manager = instance_double(SjuiTools::SwiftUI::BuildCacheManager)
        allow(SjuiTools::SwiftUI::BuildCacheManager).to receive(:new).and_return(cache_manager)
        allow(cache_manager).to receive(:clean_cache)
        allow(cache_manager).to receive(:load_last_updated).and_return({})
        allow(cache_manager).to receive(:load_last_including_files).and_return({})
        allow(cache_manager).to receive(:load_style_dependencies).and_return({})

        # Allow multiple info calls
        allow(SjuiTools::Core::Logger).to receive(:info)

        command.send(:build_swiftui, { clean: true })

        expect(SjuiTools::Core::Logger).to have_received(:info).with('Building SwiftUI files...')
        expect(SjuiTools::Core::Logger).to have_received(:info).with('Cleaning build cache...')
        expect(cache_manager).to have_received(:clean_cache)
      end
    end
  end

  describe '--strict and binding findings' do
    # A build reporting four findings still exited 0 under --strict, because
    # only attribute warnings reached the counter the flag reads (measured
    # 2026-09-04 on a Label with undefined variables). The flag says
    # "validation errors"; a binding warning is one.
    before do
      allow(SjuiTools::Core::ConfigManager).to receive(:detect_mode).and_return('swiftui')
      allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
      allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
      allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
        'layouts_directory' => 'Layouts',
        'view_directory' => 'View'
      })
      allow(command).to receive(:process_strings_extraction)
      allow(SjuiTools::Core::Logger).to receive(:info)
      allow(SjuiTools::Core::Logger).to receive(:warn)
      allow(SjuiTools::Core::Logger).to receive(:error)
      FileUtils.mkdir_p(File.join(temp_dir, 'Layouts'))
      FileUtils.mkdir_p(File.join(temp_dir, 'View'))
    end

    def write_layout(text)
      File.write(File.join(temp_dir, 'Layouts', 'sample.json'), JSON.generate(
        { 'type' => 'SafeAreaView', 'width' => 'matchParent', 'height' => 'matchParent',
          'child' => [
            { 'type' => 'Label', 'id' => 'lbl', 'width' => 'wrapContent',
              'height' => 'wrapContent', 'text' => text }
          ] }
      ))
    end

    # `@{title}` with no data section is a binding finding and nothing else.
    it 'fails the build when --strict is given' do
      write_layout('@{title}')
      expect { command.run(['--strict']) }.to raise_error(SystemExit) { |e| expect(e.status).to eq(1) }
      expect(command.instance_variable_get(:@validation_warnings).join("\n")).to match(/title/)
    end

    it 'reports the same finding without --strict and still exits 0' do
      # The finding is not new; only whether it gates is.
      write_layout('@{title}')
      expect { command.run([]) }.not_to raise_error
      expect(command.instance_variable_get(:@validation_warnings).join("\n")).to match(/title/)
    end

    it 'does not fail --strict on a tree with no findings' do
      # Control: without it, a counter that always incremented would pass
      # the first arm.
      write_layout('plain text')
      expect { command.run(['--strict']) }.not_to raise_error
      expect(command.instance_variable_get(:@validation_warnings)).to be_empty
    end
  end

  describe '#build_uikit (private)' do
    before do
      allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
      allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    end

    context 'when project not found' do
      before do
        allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(false)
      end

      it 'exits with error' do
        expect { command.send(:build_uikit) }.to raise_error(SystemExit)
      end
    end

    context 'with custom view types' do
      before do
        # Load required modules
        require 'uikit/json_loader'
        require 'uikit/import_module_manager'

        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
          'custom_view_types' => {
            'CustomButton' => {
              'class_name' => 'MyCustomButton',
              'import_module' => 'CustomUI'
            }
          }
        })
      end

      it 'configures custom view types' do
        loader_double = instance_double(SjuiTools::UIKit::JsonLoader)
        allow(SjuiTools::UIKit::JsonLoader).to receive(:new).and_return(loader_double)
        allow(loader_double).to receive(:start_analyze)
        allow(loader_double).to receive(:binding_errors).and_return([])
        allow(SjuiTools::UIKit::JsonLoader).to receive(:view_type_set).and_return({})
        allow(SjuiTools::UIKit::ImportModuleManager).to receive(:add_type_import_mapping)

        command.send(:build_uikit)

        expect(SjuiTools::UIKit::ImportModuleManager).to have_received(:add_type_import_mapping).with('CustomButton', 'CustomUI')
      end
    end
  end

  describe '#process_strings_extraction (private)' do
    before do
      allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
      allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
      allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
        'mode' => 'swiftui',
        'layouts_directory' => 'Layouts'
      })

      FileUtils.mkdir_p(File.join(temp_dir, 'Layouts'))
    end

    context 'when project not found' do
      before do
        allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(false)
      end

      it 'logs error and returns' do
        expect(SjuiTools::Core::Logger).to receive(:error).with(/Could not find project file/)
        command.send(:process_strings_extraction)
      end
    end

    context 'with swiftui mode' do
      it 'processes resources' do
        resources_manager = instance_double(SjuiTools::Core::ResourcesManager)
        allow(SjuiTools::Core::ResourcesManager).to receive(:new).and_return(resources_manager)
        allow(resources_manager).to receive(:process_resources)

        command.send(:process_strings_extraction)

        expect(resources_manager).to have_received(:process_resources)
      end
    end
  end
end
