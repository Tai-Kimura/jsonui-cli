# frozen_string_literal: true

require 'uikit/json_loader'

RSpec.describe SjuiTools::UIKit::JsonLoader do
  describe '.view_type_set' do
    it 'returns the view type set hash' do
      expect(described_class.view_type_set).to be_a(Hash)
    end

    it 'includes common view types' do
      view_types = described_class.view_type_set
      expect(view_types).to include(:View)
      expect(view_types).to include(:Label)
      expect(view_types).to include(:Button)
      expect(view_types).to include(:Image)
    end

    it 'maps view types to Swift classes' do
      view_types = described_class.view_type_set
      expect(view_types[:View]).to eq('SJUIView')
      expect(view_types[:Label]).to eq('SJUILabel')
    end

    it 'is modifiable for custom view types' do
      original_count = described_class.view_type_set.size
      described_class.view_type_set[:CustomView] = 'MyCustomView'
      expect(described_class.view_type_set.size).to eq(original_count + 1)
      expect(described_class.view_type_set[:CustomView]).to eq('MyCustomView')

      # Cleanup
      described_class.view_type_set.delete(:CustomView)
    end
  end

  describe '#initialize' do
    let(:temp_dir) { Dir.mktmpdir('json_loader_test') }
    let(:project_path) { File.join(temp_dir, 'TestApp.xcodeproj') }

    before do
      FileUtils.mkdir_p(project_path)
      FileUtils.mkdir_p(File.join(temp_dir, 'TestApp'))
      FileUtils.mkdir_p(File.join(temp_dir, 'TestApp', 'View'))
      FileUtils.mkdir_p(File.join(temp_dir, 'TestApp', 'Layouts'))
      FileUtils.mkdir_p(File.join(temp_dir, 'TestApp', 'Styles'))
      FileUtils.mkdir_p(File.join(temp_dir, 'TestApp', 'Bindings'))

      allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
      allow(SjuiTools::Core::ProjectFinder).to receive(:project_file_path).and_return(project_path)
      allow(SjuiTools::Core::ProjectFinder).to receive(:project_dir).and_return(temp_dir)
      allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(File.join(temp_dir, 'TestApp'))
      allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
        'view_directory' => 'View',
        'layouts_directory' => 'Layouts',
        'styles_directory' => 'Styles',
        'bindings_directory' => 'Bindings'
      })
      allow(SjuiTools::Core::XcodeProjectManager).to receive(:new).and_return(nil)
    end

    after do
      FileUtils.rm_rf(temp_dir)
    end

    it 'creates instance' do
      loader = described_class.new
      expect(loader).to be_a(described_class)
    end
  end

  describe '#start_analyze' do
    let(:temp_dir) { Dir.mktmpdir('json_loader_analyze_test') }
    let(:project_path) { File.join(temp_dir, 'TestApp.xcodeproj') }
    let(:source_path) { File.join(temp_dir, 'TestApp') }
    let(:layouts_path) { File.join(source_path, 'Layouts') }

    before do
      FileUtils.mkdir_p(project_path)
      FileUtils.mkdir_p(source_path)
      FileUtils.mkdir_p(File.join(source_path, 'View'))
      FileUtils.mkdir_p(layouts_path)
      FileUtils.mkdir_p(File.join(source_path, 'Styles'))
      FileUtils.mkdir_p(File.join(source_path, 'Bindings'))

      allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
      allow(SjuiTools::Core::ProjectFinder).to receive(:project_file_path).and_return(project_path)
      allow(SjuiTools::Core::ProjectFinder).to receive(:project_dir).and_return(temp_dir)
      allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(source_path)
      allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
        'view_directory' => 'View',
        'layouts_directory' => 'Layouts',
        'styles_directory' => 'Styles',
        'bindings_directory' => 'Bindings'
      })
      allow(SjuiTools::Core::XcodeProjectManager).to receive(:new).and_return(nil)
    end

    after do
      FileUtils.rm_rf(temp_dir)
    end

    context 'when layouts directory does not exist' do
      before do
        FileUtils.rm_rf(layouts_path)
      end

      it 'logs error' do
        loader = described_class.new
        expect(SjuiTools::Core::Logger).to receive(:error).with(/Layouts directory not found/)
        expect(SjuiTools::Core::Logger).to receive(:error).with(/Please run 'sjui init'/)
        loader.start_analyze
      end
    end

    context 'when layouts directory is empty' do
      it 'completes without error' do
        loader = described_class.new
        expect { loader.start_analyze }.not_to raise_error
      end
    end

    context 'when layouts directory has json files' do
      before do
        File.write(File.join(layouts_path, 'test.json'), '{"type": "View", "children": []}')
      end

      it 'processes json files' do
        loader = described_class.new
        expect(SjuiTools::Core::Logger).to receive(:info).with(/Processing:/)
        loader.start_analyze
      end
    end

    context 'when Resources folder exists' do
      before do
        FileUtils.mkdir_p(File.join(layouts_path, 'Resources'))
        File.write(File.join(layouts_path, 'Resources', 'strings.json'), '{}')
        File.write(File.join(layouts_path, 'test.json'), '{"type": "View", "children": []}')
      end

      it 'skips Resources folder' do
        loader = described_class.new
        # Should not process Resources/strings.json
        expect(SjuiTools::Core::Logger).to receive(:info).with(/Processing:.*test.json/)
        expect(SjuiTools::Core::Logger).not_to receive(:info).with(/Processing:.*strings.json/)
        loader.start_analyze
      end
    end

    context 'when data has function type that already ends with ?' do
      let(:bindings_path) { File.join(source_path, 'Bindings') }

      before do
        json_content = {
          "data" => [
            {
              "name" => "onButtonTap",
              "class" => "((UITapGestureRecognizer) -> Void)?"
            },
            {
              "name" => "normalData",
              "class" => "String"
            }
          ],
          "type" => "View",
          "width" => "matchParent",
          "height" => "matchParent"
        }
        File.write(File.join(layouts_path, 'function_type_test.json'), JSON.generate(json_content))
      end

      it 'does not add extra ? to function types that already end with ?' do
        loader = described_class.new
        loader.start_analyze

        binding_file = File.join(bindings_path, 'FunctionTypeTestBinding.swift')
        expect(File.exist?(binding_file)).to be true

        content = File.read(binding_file)
        # Should have single ? not double ??
        expect(content).to include('var onButtonTap: ((UITapGestureRecognizer) -> Void)?')
        expect(content).not_to include('((UITapGestureRecognizer) -> Void)??')
        # Normal types should still get ? added
        expect(content).to include('var normalData: String?')
      end
    end

    context 'when binding contains business logic' do
      before do
        json_content = {
          "type" => "View",
          "width" => "matchParent",
          "height" => "matchParent",
          "child" => {
            "type" => "Label",
            "id" => "test_label",
            "text" => "@{isActive ? 'Yes' : 'No'}"
          }
        }
        File.write(File.join(layouts_path, 'business_logic_test.json'), JSON.generate(json_content))
      end

      it 'validates bindings and logs warnings for business logic' do
        loader = described_class.new
        output = StringIO.new
        $stdout = output
        loader.start_analyze
        $stdout = STDOUT

        # Check that ternary operator warning was logged
        expect(output.string).to include('ternary operator')
      end
    end

    context 'when data has Visibility type' do
      let(:bindings_path) { File.join(source_path, 'Bindings') }

      before do
        json_content = {
          "data" => [
            {
              "name" => "labelVisibility",
              "class" => "Visibility",
              "defaultValue" => "visible"
            },
            {
              "name" => "buttonVisibility",
              "class" => "Visibility",
              "defaultValue" => "gone"
            }
          ],
          "type" => "View",
          "width" => "matchParent",
          "height" => "matchParent"
        }
        File.write(File.join(layouts_path, 'visibility_test.json'), JSON.generate(json_content))
      end

      it 'converts Visibility type to SJUIView.Visibility and default values to enum format' do
        loader = described_class.new
        loader.start_analyze

        binding_file = File.join(bindings_path, 'VisibilityTestBinding.swift')
        expect(File.exist?(binding_file)).to be true

        content = File.read(binding_file)
        # Check type conversion
        expect(content).to include('var labelVisibility: SJUIView.Visibility = .visible')
        expect(content).to include('var buttonVisibility: SJUIView.Visibility = .gone')
        # Should NOT have old format
        expect(content).not_to include('Visibility = visible')
        expect(content).not_to include('Visibility = gone')
      end
    end

    context 'when partialAttributes has onClick binding without other bindings' do
      let(:bindings_path) { File.join(source_path, 'Bindings') }

      before do
        json_content = {
          "data" => [
            {
              "name" => "onLinkTap",
              "class" => "((UITapGestureRecognizer) -> Void)?"
            }
          ],
          "type" => "View",
          "width" => "matchParent",
          "height" => "matchParent",
          "child" => {
            "type" => "Label",
            "id" => "test_label",
            "width" => "matchParent",
            "height" => "wrapContent",
            "text" => "Click here for details",
            "partialAttributes" => [
              {
                "range" => ["here"],
                "onClick" => "@{onLinkTap}",
                "fontColor" => "blue"
              }
            ]
          }
        }
        File.write(File.join(layouts_path, 'partial_attr_onclick_test.json'), JSON.generate(json_content))
      end

      it 'generates setPartialAttributeOnClick for onClick binding in partialAttributes' do
        loader = described_class.new
        loader.start_analyze

        binding_file = File.join(bindings_path, 'PartialAttrOnclickTestBinding.swift')
        expect(File.exist?(binding_file)).to be true

        content = File.read(binding_file)
        # Should generate setPartialAttributeOnClick call
        expect(content).to include('testLabel?.setPartialAttributeOnClick(at: 0, handler: onLinkTap)')
      end
    end
  end
end
