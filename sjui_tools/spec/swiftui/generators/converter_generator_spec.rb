# frozen_string_literal: true

require 'swiftui/generators/converter_generator'
require 'fileutils'
require 'json'

RSpec.describe SjuiTools::SwiftUI::Generators::ConverterGenerator do
  let(:temp_dir) { File.realpath(Dir.mktmpdir('converter_generator_test')) }

  before do
    allow(SjuiTools::Core::Logger).to receive(:info)
    allow(SjuiTools::Core::Logger).to receive(:debug)
    allow(SjuiTools::Core::Logger).to receive(:warn)
    allow(SjuiTools::Core::Logger).to receive(:success)
    allow(Dir).to receive(:pwd).and_return(temp_dir)

    # Create minimal structure
    FileUtils.mkdir_p(File.join(temp_dir, 'tools', 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions'))
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'stores name and options' do
      generator = described_class.new('CustomButton', attributes: { 'text' => 'String' })
      expect(generator.instance_variable_get(:@name)).to eq('CustomButton')
      expect(generator.instance_variable_get(:@class_name)).to eq('CustomButtonConverter')
    end
  end

  describe '#command_string' do
    # W3-2: build_command_string(name, options) became the shared core's
    # build_command_string(prefix) — the command is derived from the
    # instance's own @name/@options in the constructor and exposed via the
    # command_string hook (used for the _generated provenance markers).
    it 'builds basic command' do
      generator = described_class.new('MyComponent')
      expect(generator.send(:command_string)).to eq('sjui g converter MyComponent')
    end

    it 'includes attributes' do
      generator = described_class.new('MyCard', attributes: { 'title' => 'String' })
      result = generator.send(:command_string)
      expect(result).to include('--attributes=')
      expect(result).to include('title:String')
    end

    it 'includes container flag' do
      generator = described_class.new('MyContainer', is_container: true)
      expect(generator.send(:command_string)).to include('--container')
    end

    it 'includes no-container flag' do
      generator = described_class.new('MyView', is_container: false)
      expect(generator.send(:command_string)).to include('--no-container')
    end
  end

  describe '#generate_container_check (private)' do
    it 'returns forced container true' do
      generator = described_class.new('Test', is_container: true)
      result = generator.send(:generate_container_check)
      expect(result).to include('is_container = true')
    end

    it 'returns forced container false' do
      generator = described_class.new('Test', is_container: false)
      result = generator.send(:generate_container_check)
      expect(result).to include('is_container = false')
    end

    it 'returns auto-detect when not specified' do
      generator = described_class.new('Test')
      result = generator.send(:generate_container_check)
      expect(result).to include('Auto-detect')
      expect(result).to include("@component['children']")
    end
  end

  describe '#generate_parameter_collection (private)' do
    it 'returns empty for no attributes' do
      generator = described_class.new('Test')
      result = generator.send(:generate_parameter_collection)
      expect(result).to eq('')
    end

    it 'generates string parameter code' do
      generator = described_class.new('Test', attributes: { 'title' => 'String' })
      result = generator.send(:generate_parameter_collection)
      expect(result).to include("@component['title']")
      expect(result).to include("format_value(value, 'String')")
    end

    it 'generates boolean parameter code with key? check' do
      generator = described_class.new('Test', attributes: { 'isEnabled' => 'Bool' })
      result = generator.send(:generate_parameter_collection)
      expect(result).to include("@component.key?('isEnabled')")
    end

    it 'generates binding parameter code' do
      generator = described_class.new('Test', attributes: { '@value' => 'String' })
      result = generator.send(:generate_parameter_collection)
      expect(result).to include('$data.')
    end
  end

  describe '#generate_modifiers_code (private)' do
    it 'includes apply_modifiers call' do
      generator = described_class.new('Test')
      result = generator.send(:generate_modifiers_code)
      expect(result).to include('apply_modifiers')
    end
  end

  describe '#to_camel_case (private)' do
    let(:generator) { described_class.new('Test') }

    it 'converts snake_case to CamelCase' do
      result = generator.send(:to_camel_case, 'my_component')
      expect(result).to eq('MyComponent')
    end

    it 'handles single word' do
      result = generator.send(:to_camel_case, 'test')
      expect(result).to eq('Test')
    end
  end

  describe '#converter_template (private)' do
    it 'generates converter class template' do
      generator = described_class.new('CustomCard')
      result = generator.send(:converter_template)

      expect(result).to include('class CustomCardConverter < BaseViewConverter')
      expect(result).to include('module Extensions')
      expect(result).to include('def convert')
      # format_value has an is_binding_attr: keyword arg in the generated template.
      expect(result).to include('def format_value(value, type')
      expect(result).to include('def format_color_value(value)')
      expect(result).to include('def format_edge_insets_value(value)')
    end

    it 'includes component name method' do
      generator = described_class.new('MyButton')
      result = generator.send(:converter_template)

      expect(result).to include('def component_name')
      expect(result).to include('"MyButton"')
    end

    # Regression: sjui-markdown-text-converter-ignores-responsive
    # Generated extension converters must check for a `responsive` block
    # at the top of `convert` and delegate to ResponsiveHelper.generate_leaf_function
    # so size-class overrides (maxWidth / centerHorizontal / margin / etc.)
    # take effect. The fix is in the SCAFFOLD template — existing converter
    # files in consumer projects need to be regenerated to pick this up.
    it 'emits a responsive leaf wrapper at the top of convert (regression: sjui-markdown-text-converter-ignores-responsive)' do
      generator = described_class.new('MarkdownText')
      result = generator.send(:converter_template)

      expect(result).to include("require_relative '../responsive_helper'")
      expect(result).to include('ResponsiveHelper.generate_leaf_function(')
      expect(result).to include('@factory.next_responsive_name')
      expect(result).to include('@factory.register_responsive_function(func_code)')
    end

    # Regression: sjui-converter-generator-emits-responsive-as-module-method-crash
    # The responsive guard must call JsonUIShared::ResponsiveResolver.responsive?
    # directly (mirror embed/collection converters) — NOT
    # ResponsiveHelper.responsive?, which is an INSTANCE method on the module and
    # crashes with `undefined method 'responsive?' for ...ResponsiveHelper:Module`
    # the moment a scaffolded component (or a sibling node on its layout) carries
    # a `responsive` block, aborting iOS GeneratedView codegen.
    it 'guards responsive via the resolver, not the ResponsiveHelper.responsive? module method (regression: sjui-converter-generator-emits-responsive-as-module-method-crash)' do
      generator = described_class.new('ScannerCamera')
      result = generator.send(:converter_template)

      expect(result).to include('JsonUIShared::ResponsiveResolver.responsive?(@component)')
      expect(result).not_to include('ResponsiveHelper.responsive?(@component)')
    end
  end

  describe '#create_initial_mappings_file (private)' do
    it 'creates mappings file with initial mapping' do
      generator = described_class.new('NewComponent')
      generator.send(:create_initial_mappings_file)

      mappings_file = File.join(temp_dir, 'tools', 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'converter_mappings.rb')
      expect(File.exist?(mappings_file)).to be true

      content = File.read(mappings_file)
      expect(content).to include("'NewComponent' => 'NewComponentConverter'")
      expect(content).to include('CONVERTER_MAPPINGS')
    end
  end

  describe '#map_type_to_json_type (private)' do
    let(:generator) { described_class.new('Test') }

    it 'maps string to string with binding support' do
      result = generator.send(:map_type_to_json_type, 'string')
      expect(result).to eq(['string', 'binding'])
    end

    it 'maps String to string with binding support' do
      result = generator.send(:map_type_to_json_type, 'String')
      expect(result).to eq(['string', 'binding'])
    end

    it 'maps int to number with binding support' do
      result = generator.send(:map_type_to_json_type, 'int')
      expect(result).to eq(['number', 'binding'])
    end

    it 'maps integer to number with binding support' do
      result = generator.send(:map_type_to_json_type, 'integer')
      expect(result).to eq(['number', 'binding'])
    end

    it 'maps Int to number with binding support' do
      result = generator.send(:map_type_to_json_type, 'Int')
      expect(result).to eq(['number', 'binding'])
    end

    it 'maps double to number with binding support' do
      result = generator.send(:map_type_to_json_type, 'double')
      expect(result).to eq(['number', 'binding'])
    end

    it 'maps float to number with binding support' do
      result = generator.send(:map_type_to_json_type, 'float')
      expect(result).to eq(['number', 'binding'])
    end

    it 'maps Double to number with binding support' do
      result = generator.send(:map_type_to_json_type, 'Double')
      expect(result).to eq(['number', 'binding'])
    end

    it 'maps bool to boolean with binding support' do
      result = generator.send(:map_type_to_json_type, 'bool')
      expect(result).to eq(['boolean', 'binding'])
    end

    it 'maps boolean to boolean with binding support' do
      result = generator.send(:map_type_to_json_type, 'boolean')
      expect(result).to eq(['boolean', 'binding'])
    end

    it 'maps Bool to boolean with binding support' do
      result = generator.send(:map_type_to_json_type, 'Bool')
      expect(result).to eq(['boolean', 'binding'])
    end

    it 'maps Color to string with binding support (semantic key or @{binding})' do
      result = generator.send(:map_type_to_json_type, 'Color')
      expect(result).to eq(['string', 'binding'])
    end

    it 'maps lowercase color the same way' do
      result = generator.send(:map_type_to_json_type, 'color')
      expect(result).to eq(['string', 'binding'])
    end

    it 'maps unknown types to binding only' do
      result = generator.send(:map_type_to_json_type, 'CustomType')
      expect(result).to eq('binding')
    end
  end

  describe '#generate_attribute_definition_file (private)' do
    context 'when attributes are empty' do
      it 'does not create attribute definition file' do
        generator = described_class.new('MyComponent')
        generator.send(:generate_attribute_definition_file)

        attr_defs_dir = File.join(temp_dir, 'tools', 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'attribute_definitions')
        expect(Dir.exist?(attr_defs_dir)).to be false
      end
    end

    context 'when attributes are nil' do
      it 'does not create attribute definition file' do
        generator = described_class.new('MyComponent', attributes: nil)
        generator.send(:generate_attribute_definition_file)

        attr_defs_dir = File.join(temp_dir, 'tools', 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'attribute_definitions')
        expect(Dir.exist?(attr_defs_dir)).to be false
      end
    end

    context 'when attributes exist' do
      it 'creates attribute definitions directory' do
        generator = described_class.new('MyCustomCard', attributes: { 'title' => 'string' })
        generator.send(:generate_attribute_definition_file)

        attr_defs_dir = File.join(temp_dir, 'tools', 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'attribute_definitions')
        expect(Dir.exist?(attr_defs_dir)).to be true
      end

      it 'creates JSON file with component name' do
        generator = described_class.new('MyCustomCard', attributes: { 'title' => 'string' })
        generator.send(:generate_attribute_definition_file)

        file_path = File.join(temp_dir, 'tools', 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'attribute_definitions', 'MyCustomCard.json')
        expect(File.exist?(file_path)).to be true
      end

      it 'generates correct JSON structure for string attribute' do
        generator = described_class.new('MyCustomCard', attributes: { 'title' => 'string' })
        generator.send(:generate_attribute_definition_file)

        file_path = File.join(temp_dir, 'tools', 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'attribute_definitions', 'MyCustomCard.json')
        content = JSON.parse(File.read(file_path))

        expect(content).to have_key('MyCustomCard')
        expect(content['MyCustomCard']).to have_key('title')
        expect(content['MyCustomCard']['title']['type']).to eq(['string', 'binding'])
        expect(content['MyCustomCard']['title']['description']).to eq('title attribute')
      end

      it 'generates correct JSON structure for number attribute' do
        generator = described_class.new('MyCounter', attributes: { 'count' => 'int' })
        generator.send(:generate_attribute_definition_file)

        file_path = File.join(temp_dir, 'tools', 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'attribute_definitions', 'MyCounter.json')
        content = JSON.parse(File.read(file_path))

        expect(content['MyCounter']['count']['type']).to eq(['number', 'binding'])
        expect(content['MyCounter']['count']['description']).to eq('count attribute')
      end

      it 'generates correct JSON structure for boolean attribute' do
        generator = described_class.new('MyToggle', attributes: { 'isEnabled' => 'bool' })
        generator.send(:generate_attribute_definition_file)

        file_path = File.join(temp_dir, 'tools', 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'attribute_definitions', 'MyToggle.json')
        content = JSON.parse(File.read(file_path))

        expect(content['MyToggle']['isEnabled']['type']).to eq(['boolean', 'binding'])
      end

      it 'handles multiple attributes' do
        attributes = {
          'title' => 'string',
          'count' => 'int',
          'price' => 'double',
          'isActive' => 'bool'
        }
        generator = described_class.new('MyCard', attributes: attributes)
        generator.send(:generate_attribute_definition_file)

        file_path = File.join(temp_dir, 'tools', 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'attribute_definitions', 'MyCard.json')
        content = JSON.parse(File.read(file_path))

        expect(content['MyCard'].keys).to contain_exactly('title', 'count', 'price', 'isActive')
        expect(content['MyCard']['title']['type']).to eq(['string', 'binding'])
        expect(content['MyCard']['count']['type']).to eq(['number', 'binding'])
        expect(content['MyCard']['price']['type']).to eq(['number', 'binding'])
        expect(content['MyCard']['isActive']['type']).to eq(['boolean', 'binding'])
      end

      it 'removes @ prefix from binding attributes' do
        generator = described_class.new('MyInput', attributes: { '@value' => 'string' })
        generator.send(:generate_attribute_definition_file)

        file_path = File.join(temp_dir, 'tools', 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'attribute_definitions', 'MyInput.json')
        content = JSON.parse(File.read(file_path))

        expect(content['MyInput']).to have_key('value')
        expect(content['MyInput']).not_to have_key('@value')
        expect(content['MyInput']['value']['type']).to eq(['string', 'binding'])
      end

      it 'handles mixed binding and non-binding attributes' do
        attributes = {
          'title' => 'string',
          '@value' => 'string',
          'count' => 'int'
        }
        generator = described_class.new('MixedComponent', attributes: attributes)
        generator.send(:generate_attribute_definition_file)

        file_path = File.join(temp_dir, 'tools', 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'attribute_definitions', 'MixedComponent.json')
        content = JSON.parse(File.read(file_path))

        expect(content['MixedComponent'].keys).to contain_exactly('title', 'value', 'count')
        expect(content['MixedComponent']['value']['type']).to eq(['string', 'binding'])
      end

      it 'handles test app structure' do
        # Create test app structure
        test_app_dir = File.realpath(Dir.mktmpdir('test_app'))
        allow(Dir).to receive(:pwd).and_return(test_app_dir)
        FileUtils.mkdir_p(File.join(test_app_dir, 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions'))

        generator = described_class.new('TestComponent', attributes: { 'name' => 'string' })
        generator.send(:generate_attribute_definition_file)

        file_path = File.join(test_app_dir, 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'attribute_definitions', 'TestComponent.json')
        expect(File.exist?(file_path)).to be true

        content = JSON.parse(File.read(file_path))
        expect(content).to have_key('TestComponent')
        expect(content['TestComponent']['name']['type']).to eq(['string', 'binding'])

        FileUtils.rm_rf(test_app_dir)
      end

      it 'generates valid JSON that can be parsed' do
        generator = described_class.new('ValidComponent', attributes: { 'text' => 'string', 'value' => 'int' })
        generator.send(:generate_attribute_definition_file)

        file_path = File.join(temp_dir, 'tools', 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'attribute_definitions', 'ValidComponent.json')

        expect {
          JSON.parse(File.read(file_path))
        }.not_to raise_error
      end
    end
  end

  describe 'integration with AttributeValidator' do
    it 'generates attribute definitions that can be loaded by AttributeValidator' do
      # Generate attribute definition file
      generator = described_class.new('IntegrationTest', attributes: { 'title' => 'string', 'count' => 'int' })
      generator.send(:generate_attribute_definition_file)

      file_path = File.join(temp_dir, 'tools', 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'attribute_definitions', 'IntegrationTest.json')

      # Load the generated file
      content = JSON.parse(File.read(file_path))

      # Verify it has the expected structure for AttributeValidator
      expect(content).to have_key('IntegrationTest')
      expect(content['IntegrationTest']).to be_a(Hash)
      content['IntegrationTest'].each do |attr_name, attr_def|
        expect(attr_def).to have_key('type')
        expect(attr_def).to have_key('description')
      end
    end
  end
end
