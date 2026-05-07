# frozen_string_literal: true

require 'swiftui/generators/swift_component_generator'
require 'fileutils'
require 'tmpdir'

RSpec.describe SjuiTools::SwiftUI::Generators::SwiftComponentGenerator do
  let(:temp_dir) { Dir.mktmpdir('swift_component_generator_test') }

  before do
    allow(Dir).to receive(:pwd).and_return(temp_dir)
    allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
      'extension_directory' => 'Extensions'
    })
    # Generator routes output through ProjectFinder.get_full_source_path;
    # stub it to stay within the test's temporary directory.
    allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths)
    allow(SjuiTools::Core::ProjectFinder).to receive(:project_dir).and_return(temp_dir)
    allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'creates generator with name' do
      generator = described_class.new('MyComponent')
      expect(generator).to be_a(described_class)
    end

    it 'accepts options' do
      generator = described_class.new('MyComponent', is_container: true)
      expect(generator).to be_a(described_class)
    end
  end

  describe '#generate' do
    it 'creates Swift file' do
      generator = described_class.new('TestComponent')
      generator.generate
      expect(File.exist?(File.join(temp_dir, 'Extensions', 'TestComponent.swift'))).to be true
    end

    it 'creates directory if not exists' do
      generator = described_class.new('TestComponent')
      generator.generate
      expect(Dir.exist?(File.join(temp_dir, 'Extensions'))).to be true
    end

    context 'when file already exists' do
      before do
        FileUtils.mkdir_p(File.join(temp_dir, 'Extensions'))
        File.write(File.join(temp_dir, 'Extensions', 'Existing.swift'), '// existing')
      end

      it 'prompts for overwrite' do
        generator = described_class.new('Existing')
        allow(generator).to receive(:gets).and_return('n')
        expect { generator.generate }.to output(/already exists/).to_stdout
      end
    end
  end

  describe '#swift_template (private)' do
    context 'with container component' do
      it 'generates container template' do
        generator = described_class.new('MyContainer', is_container: true)
        template = generator.send(:swift_template)
        expect(template).to include('struct MyContainer<Content: View>: View')
        expect(template).to include('@ViewBuilder content')
      end
    end

    context 'with non-container component' do
      it 'generates non-container template' do
        generator = described_class.new('MyComponent', is_container: false)
        template = generator.send(:swift_template)
        expect(template).to include('struct MyComponent: View')
        expect(template).not_to include('<Content: View>')
      end
    end
  end

  describe '#generate_swift_properties (private)' do
    it 'generates properties from attributes' do
      generator = described_class.new('Test', attributes: { 'title' => 'String', 'count' => 'Int' })
      props = generator.send(:generate_swift_properties)
      expect(props).to include('let title: String')
      expect(props).to include('let count: Int')
    end

    it 'generates binding properties with @ prefix' do
      generator = described_class.new('Test', attributes: { '@isEnabled' => 'Bool' })
      props = generator.send(:generate_swift_properties)
      expect(props).to include('@SwiftUI.Binding var isEnabled: Bool')
    end

    it 'generates content property for containers' do
      generator = described_class.new('Test', is_container: true)
      props = generator.send(:generate_swift_properties)
      expect(props).to include('let content: Content')
    end

    it 'returns empty string when no attributes' do
      generator = described_class.new('Test', is_container: false)
      props = generator.send(:generate_swift_properties)
      expect(props).to eq('')
    end
  end

  describe '#generate_swift_init_params (private)' do
    it 'generates init parameters' do
      generator = described_class.new('Test', attributes: { 'title' => 'String' })
      params = generator.send(:generate_swift_init_params)
      expect(params).to include('title: String')
    end

    it 'generates binding init parameters' do
      generator = described_class.new('Test', attributes: { '@value' => 'Int' })
      params = generator.send(:generate_swift_init_params)
      expect(params).to include('value: SwiftUI.Binding<Int>')
    end

    it 'adds default nil for optional types' do
      generator = described_class.new('Test', attributes: { 'model' => 'CustomModel' })
      params = generator.send(:generate_swift_init_params)
      expect(params).to include('model: CustomModel? = nil')
    end
  end

  describe '#generate_swift_init_assignments (private)' do
    it 'generates assignments for regular properties' do
      generator = described_class.new('Test', attributes: { 'title' => 'String' })
      assignments = generator.send(:generate_swift_init_assignments)
      expect(assignments).to include('self.title = title')
    end

    it 'generates assignments for binding properties' do
      generator = described_class.new('Test', attributes: { '@value' => 'Int' })
      assignments = generator.send(:generate_swift_init_assignments)
      expect(assignments).to include('self._value = value')
    end
  end

  describe '#generate_swift_preview_params (private)' do
    it 'generates preview parameters' do
      generator = described_class.new('Test', attributes: { 'title' => 'String', 'count' => 'Int' })
      params = generator.send(:generate_swift_preview_params)
      expect(params).to include('title: "Sample Text"')
      expect(params).to include('count: 0')
    end

    it 'generates constant binding for preview' do
      generator = described_class.new('Test', attributes: { '@isEnabled' => 'Bool' })
      params = generator.send(:generate_swift_preview_params)
      expect(params).to include('isEnabled: .constant(true)')
    end
  end

  describe '#map_to_swift_type (private)' do
    let(:generator) { described_class.new('Test') }

    it 'maps String type' do
      expect(generator.send(:map_to_swift_type, 'String')).to eq('String')
    end

    it 'maps Int type' do
      expect(generator.send(:map_to_swift_type, 'Int')).to eq('Int')
    end

    it 'maps Double type' do
      expect(generator.send(:map_to_swift_type, 'Double')).to eq('Double')
    end

    it 'maps Bool type' do
      expect(generator.send(:map_to_swift_type, 'Bool')).to eq('Bool')
    end

    it 'maps Color type' do
      expect(generator.send(:map_to_swift_type, 'Color')).to eq('Color')
    end

    it 'maps EdgeInsets type' do
      expect(generator.send(:map_to_swift_type, 'EdgeInsets')).to eq('EdgeInsets')
    end

    it 'makes custom types optional by default' do
      expect(generator.send(:map_to_swift_type, 'CustomModel')).to eq('CustomModel?')
    end

    it 'respects !! suffix for non-optional' do
      expect(generator.send(:map_to_swift_type, 'CustomModel!!')).to eq('CustomModel')
    end

    it 'handles case-insensitive matching' do
      expect(generator.send(:map_to_swift_type, 'string')).to eq('String')
      expect(generator.send(:map_to_swift_type, 'boolean')).to eq('Bool')
      expect(generator.send(:map_to_swift_type, 'integer')).to eq('Int')
      expect(generator.send(:map_to_swift_type, 'float')).to eq('Double')
    end
  end

  describe '#get_swift_default_value (private)' do
    let(:generator) { described_class.new('Test') }

    it 'returns default for String' do
      expect(generator.send(:get_swift_default_value, 'String')).to eq('"Sample Text"')
    end

    it 'returns default for Int' do
      expect(generator.send(:get_swift_default_value, 'Int')).to eq('0')
    end

    it 'returns default for Double' do
      expect(generator.send(:get_swift_default_value, 'Double')).to eq('0.0')
    end

    it 'returns default for Bool' do
      expect(generator.send(:get_swift_default_value, 'Bool')).to eq('true')
    end

    it 'returns default for Color' do
      expect(generator.send(:get_swift_default_value, 'Color')).to eq('.blue')
    end

    it 'returns default for EdgeInsets' do
      expect(generator.send(:get_swift_default_value, 'EdgeInsets')).to include('EdgeInsets')
    end

    it 'returns nil for optional custom types' do
      expect(generator.send(:get_swift_default_value, 'CustomModel')).to eq('nil')
    end

    it 'returns .mock for non-optional custom types' do
      expect(generator.send(:get_swift_default_value, 'CustomModel!!')).to eq('CustomModel.mock')
    end
  end

  describe '#generate_container_init (private)' do
    it 'generates required content init for explicit container' do
      generator = described_class.new('Test', is_container: true)
      init_code = generator.send(:generate_container_init)
      expect(init_code).to include('@ViewBuilder content')
      expect(init_code).not_to include('EmptyView()')
    end

    it 'generates optional content init for default container' do
      generator = described_class.new('Test')
      init_code = generator.send(:generate_container_init)
      expect(init_code).to include('EmptyView()')
    end
  end

  describe '#generate_container_body (private)' do
    it 'generates simple content body for explicit container' do
      generator = described_class.new('Test', is_container: true)
      body = generator.send(:generate_container_body)
      expect(body).to include('content')
      expect(body).not_to include('Group')
    end

    it 'generates optional content body for default container' do
      generator = described_class.new('Test')
      body = generator.send(:generate_container_body)
      expect(body).to include('Group')
      expect(body).to include('if let content')
    end
  end

  describe '#generate_non_container_init (private)' do
    it 'generates init with attributes' do
      generator = described_class.new('Test', attributes: { 'title' => 'String' }, is_container: false)
      init_code = generator.send(:generate_non_container_init)
      expect(init_code).to include('init(')
      expect(init_code).to include('title: String')
    end

    it 'returns empty string without attributes' do
      generator = described_class.new('Test', is_container: false)
      init_code = generator.send(:generate_non_container_init)
      expect(init_code).to eq('')
    end
  end

  describe '#generate_non_container_body (private)' do
    it 'generates TODO body' do
      generator = described_class.new('Test', is_container: false)
      body = generator.send(:generate_non_container_body)
      expect(body).to include('TODO')
      expect(body).to include('EmptyView()')
    end
  end

  describe '#to_camel_case (private)' do
    let(:generator) { described_class.new('Test') }

    it 'converts snake_case to CamelCase' do
      expect(generator.send(:to_camel_case, 'my_component')).to eq('MyComponent')
    end

    it 'handles single word' do
      expect(generator.send(:to_camel_case, 'test')).to eq('Test')
    end
  end
end
