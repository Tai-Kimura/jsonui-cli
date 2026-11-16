# frozen_string_literal: true

require 'compose/setup/compose_setup'
require 'core/config_manager'
require 'core/project_finder'

RSpec.describe KjuiTools::Compose::Setup::ComposeSetup do
  let(:temp_dir) { Dir.mktmpdir }
  let(:config) do
    {
      'source_directory' => 'src/main',
      'package_name' => 'com.example.app',
      'project_path' => temp_dir
    }
  end
  let(:setup) { described_class.new(temp_dir) }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
    allow(KjuiTools::Core::ProjectFinder).to receive(:package_name).and_return('com.example.app')
    allow(KjuiTools::Core::ProjectFinder).to receive(:project_dir).and_return(temp_dir)

    # Create basic directory structure
    FileUtils.mkdir_p(File.join(temp_dir, 'src/main/kotlin/com/example/app'))
    FileUtils.mkdir_p(File.join(temp_dir, 'src/main/assets'))
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'initializes with project file path' do
      expect(setup.instance_variable_get(:@project_file_path)).to eq(temp_dir)
    end

    it 'loads config' do
      expect(setup.instance_variable_get(:@config)).to eq(config)
    end
  end

  describe '#run_full_setup' do
    before do
      # Prevent all sub-methods from running
      allow(setup).to receive(:create_directory_structure)
      allow(setup).to receive(:copy_base_files)
      allow(setup).to receive(:setup_network_security)
      allow(setup).to receive(:update_build_gradle)
    end

    it 'runs all setup steps' do
      expect(setup).to receive(:create_directory_structure)
      expect(setup).to receive(:copy_base_files)
      expect(setup).to receive(:setup_network_security)
      expect(setup).to receive(:update_build_gradle)

      expect { setup.run_full_setup }.to output(/Setting up Compose project/).to_stdout
    end

    it 'outputs completion message' do
      expect { setup.run_full_setup }.to output(/Compose setup complete!/).to_stdout
    end
  end

  describe 'private methods' do
    describe '#package_path' do
      it 'constructs correct package path' do
        result = setup.send(:package_path, 'ui/theme')
        expect(result).to include('kotlin/com/example/app/ui/theme')
      end
    end

    describe '#get_local_ip' do
      it 'returns an IP address or nil' do
        result = setup.send(:get_local_ip)
        expect([String, NilClass]).to include(result.class)
      end
    end

    describe '#create_directory_structure' do
      it 'creates required directories' do
        expect { setup.send(:create_directory_structure) }.to output(/Creating directory structure/).to_stdout
      end
    end

    describe '#find_app_gradle_file' do
      it 'returns nil when no gradle file exists' do
        result = setup.send(:find_app_gradle_file)
        expect(result).to be_nil
      end

      it 'finds build.gradle.kts' do
        gradle_path = File.join(temp_dir, 'app/build.gradle.kts')
        FileUtils.mkdir_p(File.dirname(gradle_path))
        File.write(gradle_path, 'plugins { }')

        result = setup.send(:find_app_gradle_file)
        expect(result).to eq(gradle_path)
      end

      it 'finds build.gradle' do
        gradle_path = File.join(temp_dir, 'app/build.gradle')
        FileUtils.mkdir_p(File.dirname(gradle_path))
        File.write(gradle_path, 'plugins { }')

        result = setup.send(:find_app_gradle_file)
        expect(result).to eq(gradle_path)
      end
    end

    describe '#update_build_gradle' do
      it 'outputs message' do
        expect { setup.send(:update_build_gradle) }.to output(/Updating build.gradle/).to_stdout
      end
    end

  end
end
