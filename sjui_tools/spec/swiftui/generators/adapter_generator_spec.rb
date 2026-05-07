# frozen_string_literal: true

require 'swiftui/generators/adapter_generator'
require 'fileutils'
require 'tmpdir'

RSpec.describe SjuiTools::SwiftUI::Generators::AdapterGenerator do
  let(:temp_dir) { Dir.mktmpdir('adapter_generator_test') }
  let(:adapter_dir) { File.join(temp_dir, 'Extensions', 'Adapters') }

  before do
    allow(Dir).to receive(:pwd).and_return(temp_dir)
    allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
      'adapter_directory' => 'Extensions/Adapters'
    })
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'creates generator with name' do
      generator = described_class.new('TestComponent')
      expect(generator).to be_a(described_class)
    end

    it 'accepts options' do
      generator = described_class.new('TestComponent', attributes: 'text:String')
      expect(generator).to be_a(described_class)
    end
  end

  describe '#generate' do
    context 'with no adapter directory configured' do
      before do
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
      end

      it 'outputs warning and returns false' do
        generator = described_class.new('TestComponent')
        expect { generator.generate }.to output(/No adapter_directory configured/).to_stdout
        expect(generator.generate).to be false
      end
    end

    context 'with adapter directory configured' do
      it 'creates adapter directory if it does not exist' do
        generator = described_class.new('TestComponent')
        generator.generate
        expect(Dir.exist?(adapter_dir)).to be true
      end

      it 'creates adapter Swift file' do
        generator = described_class.new('TestComponent')
        generator.generate
        adapter_file = File.join(adapter_dir, 'TestComponentAdapter.swift')
        expect(File.exist?(adapter_file)).to be true
      end

      it 'generates valid Swift adapter code' do
        generator = described_class.new('TestComponent')
        generator.generate
        content = File.read(File.join(adapter_dir, 'TestComponentAdapter.swift'))
        expect(content).to include('struct TestComponentAdapter')
        expect(content).to include('CustomComponentAdapter')
        expect(content).to include('componentType')
      end

      it 'returns true on success' do
        generator = described_class.new('TestComponent')
        result = generator.generate
        expect(result).to be true
      end
    end

    context 'with extension_directory fallback' do
      before do
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
          'extension_directory' => 'Extensions'
        })
      end

      it 'creates adapter in Extensions/Adapters' do
        generator = described_class.new('FallbackComponent')
        generator.generate
        fallback_adapter_dir = File.join(temp_dir, 'Extensions', 'Adapters')
        expect(Dir.exist?(fallback_adapter_dir)).to be true
      end
    end

    context 'with existing adapter file' do
      before do
        FileUtils.mkdir_p(adapter_dir)
        File.write(File.join(adapter_dir, 'ExistingAdapter.swift'), '// existing')
      end

      it 'prompts for overwrite' do
        generator = described_class.new('Existing')
        allow(generator).to receive(:gets).and_return('n')
        expect { generator.generate }.to output(/already exists/).to_stdout
      end
    end
  end

  describe '#parse_attributes' do
    context 'with string format' do
      it 'parses simple attributes' do
        generator = described_class.new('Test', attributes: 'text:String,count:Int')
        attrs = generator.send(:parse_attributes)
        expect(attrs['text'][:type]).to eq('String')
        expect(attrs['count'][:type]).to eq('Int')
      end

      it 'parses binding attributes with @ prefix' do
        generator = described_class.new('Test', attributes: '@isEnabled:Bool,text:String')
        attrs = generator.send(:parse_attributes)
        expect(attrs['isEnabled'][:is_binding]).to be true
        expect(attrs['text'][:is_binding]).to be false
      end
    end

    context 'with hash format' do
      it 'parses hash attributes' do
        generator = described_class.new('Test', attributes: { 'text' => 'String', 'count' => 'Int' })
        attrs = generator.send(:parse_attributes)
        expect(attrs['text'][:type]).to eq('String')
        expect(attrs['count'][:type]).to eq('Int')
      end

      it 'parses binding attributes with @ prefix' do
        generator = described_class.new('Test', attributes: { '@isEnabled' => 'Bool' })
        attrs = generator.send(:parse_attributes)
        expect(attrs['isEnabled'][:is_binding]).to be true
      end
    end

    context 'with no attributes' do
      it 'returns empty hash' do
        generator = described_class.new('Test')
        attrs = generator.send(:parse_attributes)
        expect(attrs).to eq({})
      end
    end
  end

  describe '#get_default_value_for_type' do
    let(:generator) { described_class.new('Test') }

    it 'returns empty string for String' do
      expect(generator.send(:get_default_value_for_type, 'String')).to eq('""')
    end

    it 'returns false for Bool' do
      expect(generator.send(:get_default_value_for_type, 'Bool')).to eq('false')
    end

    it 'returns 0 for Int' do
      expect(generator.send(:get_default_value_for_type, 'Int')).to eq('0')
    end

    it 'returns 0.0 for Double' do
      expect(generator.send(:get_default_value_for_type, 'Double')).to eq('0.0')
    end

    it 'returns 0.0 for Float' do
      expect(generator.send(:get_default_value_for_type, 'Float')).to eq('0.0')
    end

    it 'returns nil for unknown types' do
      expect(generator.send(:get_default_value_for_type, 'CustomType')).to eq('nil')
    end
  end

  describe '#adapter_template' do
    it 'generates template with component name' do
      generator = described_class.new('MyWidget')
      template = generator.send(:adapter_template)
      expect(template).to include('MyWidgetAdapter')
      expect(template).to include('componentType: String { "MyWidget" }')
    end

    it 'generates template with attributes' do
      generator = described_class.new('MyWidget', attributes: 'title:String')
      template = generator.send(:adapter_template)
      expect(template).to include('MyWidget')
    end
  end

  describe '#registration_template' do
    it 'generates registration template' do
      generator = described_class.new('MyWidget')
      template = generator.send(:registration_template)
      expect(template).to include('CustomComponentRegistration')
      expect(template).to include('MyWidgetAdapter()')
      expect(template).to include('registerAll')
    end
  end

  describe '#update_registration_file' do
    let(:generator) { described_class.new('NewComponent') }
    let(:registration_file) { File.join(adapter_dir, 'CustomComponentRegistration.swift') }

    before do
      FileUtils.mkdir_p(adapter_dir)
    end

    context 'when registration file does not exist' do
      it 'creates registration file' do
        generator.send(:update_registration_file, 'Extensions/Adapters')
        expect(File.exist?(registration_file)).to be true
      end
    end

    context 'when registration file exists' do
      before do
        File.write(registration_file, <<~SWIFT)
          let adapters: [CustomComponentAdapter] = [
              ExistingAdapter()
          ]
        SWIFT
      end

      it 'adds new adapter to list' do
        generator.send(:update_registration_file, 'Extensions/Adapters')
        content = File.read(registration_file)
        expect(content).to include('NewComponentAdapter()')
      end

      it 'does not duplicate existing adapter' do
        File.write(registration_file, <<~SWIFT)
          let adapters: [CustomComponentAdapter] = [
              NewComponentAdapter()
          ]
        SWIFT
        generator.send(:update_registration_file, 'Extensions/Adapters')
        content = File.read(registration_file)
        expect(content.scan('NewComponentAdapter()').count).to eq(1)
      end
    end
  end

  describe '#build_non_container_implementation' do
    let(:generator) { described_class.new('SimpleComponent', no_container: true) }

    it 'generates non-container implementation' do
      attributes = { 'text' => { type: 'String', is_binding: false } }
      impl = generator.send(:build_non_container_implementation, attributes)
      expect(impl).to include('SimpleComponent')
      expect(impl).not_to include('childComponents')
    end
  end

  describe '#build_container_implementation' do
    let(:generator) { described_class.new('ContainerComponent') }

    it 'generates container implementation with children' do
      attributes = { 'title' => { type: 'String', is_binding: false } }
      impl = generator.send(:build_container_implementation, attributes)
      expect(impl).to include('childComponents')
      expect(impl).to include('DynamicComponentBuilder')
    end
  end

  describe '#generate_binding_extraction' do
    let(:generator) { described_class.new('BindingTest') }

    it 'generates binding code for String' do
      code = generator.send(:generate_binding_extraction, 'text', 'String')
      expect(code).to include('SwiftUI.Binding<String>')
      expect(code).to include('.constant(')
    end

    it 'generates binding code for Bool' do
      code = generator.send(:generate_binding_extraction, 'isEnabled', 'Bool')
      expect(code).to include('SwiftUI.Binding<Bool>')
      expect(code).to include('false')
    end

    it 'generates binding code for custom model type' do
      code = generator.send(:generate_binding_extraction, 'model', 'CustomModel')
      expect(code).to include('SwiftUI.Binding<CustomModel?>')
      expect(code).to include('.constant(nil)')
    end
  end

  describe 'source_directory handling' do
    context 'when source_directory is configured' do
      before do
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
          'source_directory' => 'MyApp',
          'adapter_directory' => 'Extensions/Adapters'
        })
        allow(File).to receive(:basename).with(temp_dir).and_return('project_root')
      end

      it 'prepends source_directory to adapter_directory' do
        generator = described_class.new('SourceTest')
        dir = generator.send(:get_adapter_directory)
        expect(dir).to eq('MyApp/Extensions/Adapters')
      end
    end

    context 'when current directory is source_directory' do
      before do
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
          'source_directory' => 'MyApp',
          'adapter_directory' => 'Extensions/Adapters'
        })
        allow(File).to receive(:basename).with(temp_dir).and_return('MyApp')
      end

      it 'does not prepend source_directory' do
        generator = described_class.new('SourceTest')
        dir = generator.send(:get_adapter_directory)
        expect(dir).to eq('Extensions/Adapters')
      end
    end
  end
end
