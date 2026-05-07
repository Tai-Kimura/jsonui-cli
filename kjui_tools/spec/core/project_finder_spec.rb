# frozen_string_literal: true

require 'core/project_finder'

RSpec.describe KjuiTools::Core::ProjectFinder do
  let(:temp_dir) { Dir.mktmpdir('project_finder_test') }

  before do
    @original_dir = Dir.pwd
    Dir.chdir(temp_dir)
    described_class.instance_variable_set(:@project_dir, nil)
    described_class.instance_variable_set(:@project_file_path, nil)
  end

  after do
    Dir.chdir(@original_dir)
    FileUtils.rm_rf(temp_dir)
  end

  describe '.setup_paths' do
    it 'sets up project_dir and project_file_path' do
      described_class.setup_paths
      expect(described_class.project_dir).not_to be_nil
    end
  end

  describe '.find_project_dir' do
    context 'when in Android project directory' do
      before do
        File.write(File.join(temp_dir, 'build.gradle'), 'android {}')
      end

      it 'returns current directory' do
        expect(described_class.find_project_dir).to eq(Dir.pwd)
      end
    end

    context 'when in subdirectory of Android project' do
      before do
        File.write(File.join(temp_dir, 'settings.gradle'), "rootProject.name = 'Test'")
        sub_dir = File.join(temp_dir, 'app')
        FileUtils.mkdir_p(sub_dir)
        Dir.chdir(sub_dir)
      end

      it 'returns parent directory' do
        result = described_class.find_project_dir
        # Parent should contain settings.gradle
        expect(File.exist?(File.join(result, 'settings.gradle'))).to be true
      end
    end

    context 'when not in Android project' do
      it 'returns current directory' do
        expect(described_class.find_project_dir).to eq(Dir.pwd)
      end
    end
  end

  describe '.find_project_file' do
    context 'when build.gradle exists' do
      before do
        File.write(File.join(temp_dir, 'build.gradle'), 'android {}')
      end

      it 'returns the gradle file' do
        expect(described_class.find_project_file).to eq('build.gradle')
      end
    end

    context 'when build.gradle.kts exists' do
      before do
        File.write(File.join(temp_dir, 'build.gradle.kts'), 'android {}')
      end

      it 'returns the gradle file' do
        expect(described_class.find_project_file).to include('build.gradle.kts')
      end
    end

    context 'when no gradle file exists' do
      it 'returns nil' do
        expect(described_class.find_project_file).to be_nil
      end
    end
  end

  describe '.find_source_directory' do
    context 'when app/src/main exists' do
      before do
        FileUtils.mkdir_p(File.join(temp_dir, 'app', 'src', 'main'))
        described_class.instance_variable_set(:@project_dir, temp_dir)
      end

      it 'returns app/src/main' do
        expect(described_class.find_source_directory).to eq('app/src/main')
      end
    end

    context 'when src/main exists' do
      before do
        FileUtils.mkdir_p(File.join(temp_dir, 'src', 'main'))
        described_class.instance_variable_set(:@project_dir, temp_dir)
      end

      it 'returns src/main' do
        expect(described_class.find_source_directory).to eq('src/main')
      end
    end

    context 'when no standard directory exists' do
      before do
        described_class.instance_variable_set(:@project_dir, temp_dir)
      end

      it 'returns default app/src/main' do
        expect(described_class.find_source_directory).to eq('app/src/main')
      end
    end
  end

  describe '.get_full_source_path' do
    before do
      described_class.instance_variable_set(:@project_dir, temp_dir)
    end

    it 'returns project_dir' do
      expect(described_class.get_full_source_path).to eq(temp_dir)
    end
  end

  describe '.package_name' do
    context 'when AndroidManifest.xml exists' do
      before do
        manifest_dir = File.join(temp_dir, 'app', 'src', 'main')
        FileUtils.mkdir_p(manifest_dir)
        File.write(File.join(manifest_dir, 'AndroidManifest.xml'),
                   '<manifest package="com.test.myapp">')
        described_class.instance_variable_set(:@project_dir, temp_dir)
      end

      it 'extracts package name from manifest' do
        expect(described_class.package_name).to eq('com.test.myapp')
      end
    end

    context 'when build.gradle has namespace' do
      before do
        app_dir = File.join(temp_dir, 'app')
        FileUtils.mkdir_p(app_dir)
        File.write(File.join(app_dir, 'build.gradle'), "namespace = 'com.gradle.namespace'")
      end

      it 'extracts package name from gradle' do
        expect(described_class.package_name).to eq('com.gradle.namespace')
      end
    end

    context 'when build.gradle has applicationId' do
      before do
        app_dir = File.join(temp_dir, 'app')
        FileUtils.mkdir_p(app_dir)
        File.write(File.join(app_dir, 'build.gradle'), "applicationId = 'com.gradle.appid'")
      end

      it 'extracts package name from gradle' do
        expect(described_class.package_name).to eq('com.gradle.appid')
      end
    end

    context 'when no package info found' do
      it 'returns default package name' do
        expect(described_class.package_name).to eq('com.example.app')
      end
    end
  end

  describe '.get_package_name' do
    it 'delegates to package_name' do
      expect(described_class).to receive(:package_name).and_return('com.test.app')
      expect(described_class.get_package_name).to eq('com.test.app')
    end
  end
end
