# frozen_string_literal: true

require 'swiftui/setup/swiftui_setup'
require 'core/setup/common_setup'
require 'swiftui/setup/hotloader_generator'

RSpec.describe SjuiTools::SwiftUI::Setup::SwiftUISetup do
  let(:temp_dir) { Dir.mktmpdir('swiftui_setup_test') }
  let(:project_path) { File.join(temp_dir, 'TestApp.xcodeproj') }
  let(:setup) { described_class.new(project_path) }

  before do
    FileUtils.mkdir_p(project_path)
    FileUtils.mkdir_p(File.join(temp_dir, 'TestApp'))
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'creates instance with project path' do
      expect(setup).to be_a(described_class)
    end

    it 'inherits from PbxprojManager' do
      expect(setup).to be_a(SjuiTools::Core::PbxprojManager)
    end
  end

  describe '#run_full_setup' do
    before do
      allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
        'layouts_directory' => 'Layouts',
        'styles_directory' => 'Styles',
        'viewmodel_directory' => 'ViewModel',
        'resource_manager_directory' => 'ResourceManager'
      })
      allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(File.join(temp_dir, 'TestApp'))

      # Mock CommonSetup
      common_setup = instance_double(SjuiTools::Core::Setup::CommonSetup)
      allow(SjuiTools::Core::Setup::CommonSetup).to receive(:new).and_return(common_setup)
      allow(common_setup).to receive(:ensure_workspace_exists)
      allow(common_setup).to receive(:setup_libraries)
      allow(common_setup).to receive(:cleanup_project_references)
      allow(common_setup).to receive(:setup_membership_exceptions)

      # Mock file additions and string manager
      allow(setup).to receive(:generate_hotloader_setup)
      allow(setup).to receive(:add_config_to_project)
      allow(setup).to receive(:create_string_manager_file)
    end

    it 'outputs start message' do
      expect { setup.run_full_setup }.to output(/Starting SwiftUI Project Setup/).to_stdout
    end

    it 'outputs completion message' do
      expect { setup.run_full_setup }.to output(/SwiftUI Project Setup Completed/).to_stdout
    end

    it 'creates swiftui directories' do
      setup.run_full_setup
      source_path = File.join(temp_dir, 'TestApp')
      expect(Dir.exist?(File.join(source_path, 'Layouts'))).to be true
      expect(Dir.exist?(File.join(source_path, 'Styles'))).to be true
      expect(Dir.exist?(File.join(source_path, 'ViewModel'))).to be true
      expect(Dir.exist?(File.join(source_path, 'ResourceManager'))).to be true
    end
  end

  describe '#create_swiftui_directories (private)' do
    before do
      allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
        'layouts_directory' => 'Layouts',
        'styles_directory' => 'Styles',
        'viewmodel_directory' => 'ViewModel',
        'resource_manager_directory' => 'ResourceManager'
      })
      allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(File.join(temp_dir, 'TestApp'))
      allow(setup).to receive(:create_string_manager_file)
    end

    it 'creates Layouts directory' do
      setup.send(:create_swiftui_directories)
      expect(Dir.exist?(File.join(temp_dir, 'TestApp', 'Layouts'))).to be true
    end

    it 'creates Styles directory' do
      setup.send(:create_swiftui_directories)
      expect(Dir.exist?(File.join(temp_dir, 'TestApp', 'Styles'))).to be true
    end

    it 'creates ViewModel directory' do
      setup.send(:create_swiftui_directories)
      expect(Dir.exist?(File.join(temp_dir, 'TestApp', 'ViewModel'))).to be true
    end

    it 'creates ResourceManager directory' do
      setup.send(:create_swiftui_directories)
      expect(Dir.exist?(File.join(temp_dir, 'TestApp', 'ResourceManager'))).to be true
    end

    it 'skips existing directories' do
      source_path = File.join(temp_dir, 'TestApp')
      FileUtils.mkdir_p(File.join(source_path, 'Layouts'))

      expect { setup.send(:create_swiftui_directories) }.not_to output(/Created directory: Layouts/).to_stdout
    end

    it 'uses default directory names when config is empty' do
      allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
      setup.send(:create_swiftui_directories)

      source_path = File.join(temp_dir, 'TestApp')
      expect(Dir.exist?(File.join(source_path, 'Layouts'))).to be true
      expect(Dir.exist?(File.join(source_path, 'Styles'))).to be true
    end
  end

  describe '#generate_hotloader_setup (private)' do
    before do
      allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(File.join(temp_dir, 'TestApp'))
      allow(SjuiTools::SwiftUI::Setup::HotLoaderGenerator).to receive(:generate)
      allow(setup).to receive(:add_file_to_project)
    end

    it 'calls HotLoaderGenerator.generate' do
      expect(SjuiTools::SwiftUI::Setup::HotLoaderGenerator).to receive(:generate)
      setup.send(:generate_hotloader_setup)
    end

    it 'outputs message' do
      expect { setup.send(:generate_hotloader_setup) }.to output(/Generating HotLoader setup/).to_stdout
    end
  end

  describe '#add_config_to_project (private)' do
    before do
      allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(File.join(temp_dir, 'TestApp'))
      allow(setup).to receive(:add_file_to_project)
    end

    it 'outputs message' do
      expect { setup.send(:add_config_to_project) }.to output(/Adding sjui.config.json/).to_stdout
    end

    context 'when config file exists' do
      before do
        File.write(File.join(temp_dir, 'sjui.config.json'), '{}')
      end

      it 'calls add_file_to_project' do
        expect(setup).to receive(:add_file_to_project)
        setup.send(:add_config_to_project)
      end
    end

    context 'when config file does not exist' do
      it 'outputs warning' do
        expect { setup.send(:add_config_to_project) }.to output(/Warning: sjui.config.json not found/).to_stdout
      end
    end
  end

  describe '#create_string_manager_file (private)' do
    let(:resource_manager_path) { File.join(temp_dir, 'TestApp', 'ResourceManager') }

    before do
      FileUtils.mkdir_p(resource_manager_path)
      allow(setup).to receive(:add_file_to_project)
    end

    it 'creates StringManager.swift file' do
      setup.send(:create_string_manager_file, resource_manager_path)
      expect(File.exist?(File.join(resource_manager_path, 'StringManager.swift'))).to be true
    end

    it 'outputs created message' do
      expect { setup.send(:create_string_manager_file, resource_manager_path) }.to output(/Created file: StringManager.swift/).to_stdout
    end

    context 'when file already exists' do
      before do
        File.write(File.join(resource_manager_path, 'StringManager.swift'), '// existing')
      end

      it 'does not overwrite' do
        setup.send(:create_string_manager_file, resource_manager_path)
        content = File.read(File.join(resource_manager_path, 'StringManager.swift'))
        expect(content).to eq('// existing')
      end

      it 'outputs already exists message' do
        expect { setup.send(:create_string_manager_file, resource_manager_path) }.to output(/File already exists/).to_stdout
      end
    end
  end
end
