# frozen_string_literal: true

require 'core/project_finder'
require 'fileutils'
require 'tmpdir'

RSpec.describe SjuiTools::Core::ProjectFinder do
  let(:temp_dir) { File.realpath(Dir.mktmpdir('project_finder_test')) }

  before do
    described_class.reset!
  end

  after do
    described_class.reset!
    FileUtils.rm_rf(temp_dir)
  end

  describe '.find_xcodeproj' do
    context 'when xcodeproj exists in starting directory' do
      it 'returns the xcodeproj path' do
        xcodeproj = File.join(temp_dir, 'Test.xcodeproj')
        FileUtils.mkdir_p(xcodeproj)

        result = described_class.find_xcodeproj(temp_dir)
        expect(result).to eq(xcodeproj)
      end
    end

    context 'when xcodeproj exists in parent directory' do
      it 'finds xcodeproj in parent' do
        xcodeproj = File.join(temp_dir, 'Parent.xcodeproj')
        FileUtils.mkdir_p(xcodeproj)

        sub_dir = File.join(temp_dir, 'subdirectory')
        FileUtils.mkdir_p(sub_dir)

        result = described_class.find_xcodeproj(sub_dir)
        expect(result).to eq(xcodeproj)
      end
    end

    context 'when no xcodeproj exists' do
      it 'returns nil' do
        result = described_class.find_xcodeproj(temp_dir)
        expect(result).to be_nil
      end
    end
  end

  describe '.find_package_swift' do
    context 'when Package.swift exists' do
      it 'returns the Package.swift path' do
        package_path = File.join(temp_dir, 'Package.swift')
        File.write(package_path, '// Swift Package')

        result = described_class.find_package_swift(temp_dir)
        expect(result).to eq(package_path)
      end
    end

    context 'when Package.swift exists in parent' do
      it 'finds Package.swift in parent' do
        package_path = File.join(temp_dir, 'Package.swift')
        File.write(package_path, '// Swift Package')

        sub_dir = File.join(temp_dir, 'Sources')
        FileUtils.mkdir_p(sub_dir)

        result = described_class.find_package_swift(sub_dir)
        expect(result).to eq(package_path)
      end
    end

    context 'when no Package.swift exists' do
      it 'returns nil' do
        result = described_class.find_package_swift(temp_dir)
        expect(result).to be_nil
      end
    end
  end

  describe '.setup_paths' do
    context 'when project file path is provided' do
      it 'uses provided path' do
        xcodeproj = File.join(temp_dir, 'MyApp.xcodeproj')
        FileUtils.mkdir_p(xcodeproj)

        result = described_class.setup_paths(xcodeproj)

        expect(result).to be true
        expect(described_class.project_file_path).to eq(xcodeproj)
        expect(described_class.project_dir).to eq(temp_dir)
      end
    end

    context 'when xcodeproj is found' do
      it 'sets up from xcodeproj' do
        xcodeproj = File.join(temp_dir, 'Test.xcodeproj')
        FileUtils.mkdir_p(xcodeproj)

        Dir.chdir(temp_dir) do
          result = described_class.setup_paths
          expect(result).to be true
          expect(described_class.project_file_path).to eq(xcodeproj)
        end
      end
    end

    context 'when Package.swift is found' do
      it 'sets up from Package.swift' do
        package_path = File.join(temp_dir, 'Package.swift')
        File.write(package_path, '// Swift Package')

        Dir.chdir(temp_dir) do
          result = described_class.setup_paths
          expect(result).to be true
          expect(described_class.project_file_path).to eq(package_path)
        end
      end
    end

    context 'when no project file is found' do
      it 'falls back to current directory' do
        Dir.chdir(temp_dir) do
          result = described_class.setup_paths
          expect(result).to be false
          expect(described_class.project_dir).to eq(temp_dir)
          expect(described_class.project_file_path).to be_nil
        end
      end
    end
  end

  describe '.find_source_directory' do
    before do
      described_class.instance_variable_set(:@project_dir, temp_dir)
    end

    context 'when source_directory is configured' do
      it 'returns configured directory' do
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
          'source_directory' => 'CustomSource'
        })

        result = described_class.find_source_directory
        expect(result).to eq('CustomSource')
      end
    end

    context 'when Sources directory exists' do
      it 'returns Sources' do
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
        FileUtils.mkdir_p(File.join(temp_dir, 'Sources'))

        result = described_class.find_source_directory
        expect(result).to eq('Sources')
      end
    end

    context 'when Source directory exists' do
      it 'returns Source' do
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
        FileUtils.mkdir_p(File.join(temp_dir, 'Source'))

        result = described_class.find_source_directory
        expect(result).to eq('Source')
      end
    end

    context 'when no source directory exists' do
      it 'returns empty string' do
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})

        result = described_class.find_source_directory
        expect(result).to eq('')
      end
    end
  end

  describe '.get_full_source_path' do
    before do
      described_class.instance_variable_set(:@project_dir, temp_dir)
    end

    context 'when source_directory is set' do
      it 'returns full path including source directory' do
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
        FileUtils.mkdir_p(File.join(temp_dir, 'Sources'))

        result = described_class.get_full_source_path
        expect(result).to eq(File.join(temp_dir, 'Sources'))
      end
    end

    context 'when source_directory is empty' do
      it 'returns project_dir' do
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
        described_class.instance_variable_set(:@source_directory, nil)

        result = described_class.get_full_source_path
        expect(result).to eq(temp_dir)
      end
    end
  end

  describe '.find_project_file' do
    context 'when xcodeproj exists' do
      it 'returns xcodeproj' do
        xcodeproj = File.join(temp_dir, 'Test.xcodeproj')
        FileUtils.mkdir_p(xcodeproj)

        result = described_class.find_project_file(temp_dir)
        expect(result).to eq(xcodeproj)
      end
    end

    context 'when Package.swift exists' do
      it 'returns Package.swift' do
        package_path = File.join(temp_dir, 'Package.swift')
        File.write(package_path, '// Swift Package')

        result = described_class.find_project_file(temp_dir)
        expect(result).to eq(package_path)
      end
    end

    context 'when no project file exists' do
      it 'returns nil' do
        result = described_class.find_project_file(temp_dir)
        expect(result).to be_nil
      end
    end
  end

  describe '.get_project_root' do
    it 'returns parent for xcodeproj' do
      result = described_class.get_project_root('/path/to/MyApp.xcodeproj')
      expect(result).to eq('/path/to')
    end

    it 'returns parent for Package.swift' do
      result = described_class.get_project_root('/path/to/Package.swift')
      expect(result).to eq('/path/to')
    end

    it 'returns grandparent for pbxproj' do
      result = described_class.get_project_root('/path/to/MyApp.xcodeproj/project.pbxproj')
      expect(result).to eq('/path/to')
    end
  end

  describe '.find_directory' do
    before do
      described_class.instance_variable_set(:@project_dir, temp_dir)
      allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    end

    context 'when directory exists in source path' do
      it 'returns directory path' do
        layouts_dir = File.join(temp_dir, 'Layouts')
        FileUtils.mkdir_p(layouts_dir)

        result = described_class.find_directory('Layouts')
        expect(result).to eq(layouts_dir)
      end
    end

    context 'when directory does not exist' do
      it 'returns nil' do
        result = described_class.find_directory('NonExistent')
        expect(result).to be_nil
      end
    end

    context 'when create is true' do
      it 'creates and returns directory' do
        result = described_class.find_directory('NewDir', create: true)
        expect(result).to eq(File.join(temp_dir, 'NewDir'))
        expect(Dir.exist?(result)).to be true
      end
    end
  end

  describe '.reset!' do
    it 'clears all instance variables' do
      described_class.instance_variable_set(:@project_dir, '/some/path')
      described_class.instance_variable_set(:@project_file_path, '/some/file')
      described_class.instance_variable_set(:@source_directory, 'Sources')

      described_class.reset!

      expect(described_class.project_dir).to be_nil
      expect(described_class.project_file_path).to be_nil
      expect(described_class.instance_variable_get(:@source_directory)).to be_nil
    end
  end
end
