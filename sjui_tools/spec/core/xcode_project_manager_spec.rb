# frozen_string_literal: true

require 'core/xcode_project_manager'

RSpec.describe SjuiTools::Core::XcodeProjectManager do
  describe 'EXCLUDED_PATTERNS' do
    it 'includes common patterns to exclude' do
      patterns = described_class::EXCLUDED_PATTERNS
      expect(patterns).to include('sjui_tools/')
      expect(patterns).to include('.git/')
      expect(patterns).to include('node_modules/')
      expect(patterns).to include('.DS_Store')
    end

    it 'is frozen' do
      expect(described_class::EXCLUDED_PATTERNS).to be_frozen
    end
  end

  describe '#initialize' do
    let(:temp_dir) { Dir.mktmpdir('xcode_project_manager_test') }
    let(:project_path) { File.join(temp_dir, 'TestApp.xcodeproj') }

    before do
      # Create a minimal xcodeproj structure
      FileUtils.mkdir_p(project_path)
      File.write(File.join(project_path, 'project.pbxproj'), minimal_pbxproj_content)
    end

    after do
      FileUtils.rm_rf(temp_dir)
    end

    it 'opens the project' do
      manager = described_class.new(project_path)
      expect(manager.project).to be_a(Xcodeproj::Project)
    end

    it 'stores the project path' do
      manager = described_class.new(project_path)
      expect(manager.project_path).to eq(project_path)
    end

    def minimal_pbxproj_content
      <<~PBXPROJ
        // !$*UTF8*$!
        {
          archiveVersion = 1;
          classes = {
          };
          objectVersion = 56;
          objects = {
            0867D690FE84155DC02AAC07 /* TestApp */ = {
              isa = PBXGroup;
              children = (
              );
              name = TestApp;
              sourceTree = "<group>";
            };
            089C1665FE841187C02AAC07 /* Project object */ = {
              isa = PBXProject;
              buildConfigurationList = 1DEB922208733DC00010E9CD;
              mainGroup = 0867D690FE84155DC02AAC07;
              projectDirPath = "";
              projectRoot = "";
              targets = (
              );
            };
            1DEB922208733DC00010E9CD /* Build configuration list for PBXProject */ = {
              isa = XCConfigurationList;
              buildConfigurations = (
              );
            };
          };
          rootObject = 089C1665FE841187C02AAC07;
        }
      PBXPROJ
    end
  end

  describe '#check_if_synchronized_project' do
    let(:temp_dir) { Dir.mktmpdir('sync_check_test') }
    let(:project_path) { File.join(temp_dir, 'TestApp.xcodeproj') }

    after do
      FileUtils.rm_rf(temp_dir)
    end

    context 'with non-synchronized project' do
      before do
        FileUtils.mkdir_p(project_path)
        File.write(File.join(project_path, 'project.pbxproj'), non_sync_pbxproj)
      end

      it 'returns false' do
        manager = described_class.new(project_path)
        expect(manager.instance_variable_get(:@is_synchronized)).to be false
      end

      def non_sync_pbxproj
        <<~PBXPROJ
          // !$*UTF8*$!
          {
            archiveVersion = 1;
            classes = {
            };
            objectVersion = 56;
            objects = {
              0867D690FE84155DC02AAC07 /* TestApp */ = {
                isa = PBXGroup;
                children = (
                );
                name = TestApp;
                sourceTree = "<group>";
              };
              089C1665FE841187C02AAC07 /* Project object */ = {
                isa = PBXProject;
                buildConfigurationList = 1DEB922208733DC00010E9CD;
                mainGroup = 0867D690FE84155DC02AAC07;
                projectDirPath = "";
                projectRoot = "";
                targets = (
                );
              };
              1DEB922208733DC00010E9CD /* Build configuration list for PBXProject */ = {
                isa = XCConfigurationList;
                buildConfigurations = (
                );
              };
            };
            rootObject = 089C1665FE841187C02AAC07;
          }
        PBXPROJ
      end
    end
  end
end
