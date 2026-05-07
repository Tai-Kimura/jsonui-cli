# frozen_string_literal: true

require 'compose/generators/dynamic_component_generator'
require 'core/config_manager'
require 'core/project_finder'
require 'core/logger'
require 'fileutils'

RSpec.describe KjuiTools::Compose::Generators::DynamicComponentGenerator do
  let(:temp_dir) { Dir.mktmpdir('dynamic_gen_test') }

  before do
    @original_dir = Dir.pwd
    Dir.chdir(temp_dir)
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
      '_config_dir' => temp_dir,
      'source_directory' => 'src/main',
      'package_name' => 'com.example.app'
    })
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_package_name).and_return('com.example.app')
    allow(KjuiTools::Core::Logger).to receive(:info)
    allow(KjuiTools::Core::Logger).to receive(:warn)
  end

  after do
    Dir.chdir(@original_dir)
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'creates generator with name' do
      generator = described_class.new('TestComponent')
      expect(generator).to be_a(described_class)
    end

    it 'creates generator with options' do
      generator = described_class.new('TestComponent', { attributes: { 'title' => 'String' } })
      expect(generator).to be_a(described_class)
    end
  end

  describe 'private helper methods' do
    let(:generator) { described_class.new('TestComponent') }

    describe '#get_parser_method_name' do
      it 'returns parseString for string type' do
        result = generator.send(:get_parser_method_name, 'string')
        expect(result).to eq('parseString')
      end

      it 'returns parseString for text type' do
        result = generator.send(:get_parser_method_name, 'text')
        expect(result).to eq('parseString')
      end

      it 'returns parseInt for int type' do
        result = generator.send(:get_parser_method_name, 'int')
        expect(result).to eq('parseInt')
      end

      it 'returns parseInt for integer type' do
        result = generator.send(:get_parser_method_name, 'integer')
        expect(result).to eq('parseInt')
      end

      it 'returns parseBoolean for bool type' do
        result = generator.send(:get_parser_method_name, 'bool')
        expect(result).to eq('parseBoolean')
      end

      it 'returns parseBoolean for boolean type' do
        result = generator.send(:get_parser_method_name, 'boolean')
        expect(result).to eq('parseBoolean')
      end

      it 'returns parseColor for color type' do
        result = generator.send(:get_parser_method_name, 'color')
        expect(result).to eq('parseColor')
      end

      it 'returns parseFloat for float type' do
        result = generator.send(:get_parser_method_name, 'float')
        expect(result).to eq('parseFloat')
      end

      it 'returns parseString for unknown type' do
        result = generator.send(:get_parser_method_name, 'unknown')
        expect(result).to eq('parseString')
      end
    end

    describe '#get_default_value' do
      it 'returns empty string for string type' do
        result = generator.send(:get_default_value, 'string')
        expect(result).to eq('""')
      end

      it 'returns 0 for int type' do
        result = generator.send(:get_default_value, 'int')
        expect(result).to eq('0')
      end

      it 'returns false for bool type' do
        result = generator.send(:get_default_value, 'bool')
        expect(result).to eq('false')
      end

      it 'returns 0.0 for float type' do
        result = generator.send(:get_default_value, 'float')
        expect(result).to eq('0.0')
      end

      it 'returns Color.Unspecified for color type' do
        result = generator.send(:get_default_value, 'color')
        expect(result).to include('Color.Unspecified')
      end

      it 'returns null for unknown type' do
        result = generator.send(:get_default_value, 'unknown')
        expect(result).to eq('null')
      end
    end
  end

  describe 'template generation' do
    describe '#dynamic_template' do
      it 'generates basic template' do
        generator = described_class.new('TestCard')
        template = generator.send(:dynamic_template)
        expect(template).to include('package com.example.app')
        expect(template).to include('DynamicTestCardComponent')
        expect(template).to include('@Composable')
        expect(template).to include('fun create')
      end

      it 'includes container handling for container components' do
        generator = described_class.new('TestCard', { is_container: true })
        template = generator.send(:dynamic_template)
        expect(template).to include('children')
      end
    end

    describe '#generate_dynamic_imports' do
      it 'returns empty string when no attributes' do
        generator = described_class.new('Test')
        result = generator.send(:generate_dynamic_imports, 'com.example.app')
        expect(result).to eq('')
      end

      it 'adds ResourceResolver import for string type' do
        generator = described_class.new('Test', { attributes: { 'title' => 'String' } })
        result = generator.send(:generate_dynamic_imports, 'com.example.app')
        expect(result).to include('ResourceResolver')
      end

      it 'adds ResourceResolver import for text type' do
        generator = described_class.new('Test', { attributes: { 'textAlign' => 'text' } })
        result = generator.send(:generate_dynamic_imports, 'com.example.app')
        expect(result).to include('ResourceResolver')
      end

      it 'adds Color import for color type' do
        generator = described_class.new('Test', { attributes: { 'color' => 'color' } })
        result = generator.send(:generate_dynamic_imports, 'com.example.app')
        expect(result).to include('Color')
      end
    end

    describe '#generate_attribute_docs' do
      it 'returns default doc when no attributes' do
        generator = described_class.new('Test')
        result = generator.send(:generate_attribute_docs)
        expect(result).to include('child/children')
      end

      it 'includes custom attributes in docs' do
        generator = described_class.new('Test', { attributes: { 'title' => 'String' } })
        result = generator.send(:generate_attribute_docs)
        expect(result).to include('title')
        expect(result).to include('String')
      end

      it 'marks binding attributes' do
        generator = described_class.new('Test', { attributes: { '@name' => 'String' } })
        result = generator.send(:generate_attribute_docs)
        expect(result).to include('binding')
      end
    end

    describe '#generate_dynamic_parameter_parsing' do
      it 'returns empty when no attributes' do
        generator = described_class.new('Test')
        result = generator.send(:generate_dynamic_parameter_parsing)
        expect(result).to eq('')
      end

      it 'generates parsing code for attributes' do
        generator = described_class.new('Test', { attributes: { 'title' => 'String' } })
        result = generator.send(:generate_dynamic_parameter_parsing)
        expect(result).to include('ResourceResolver.resolveText')
        expect(result).to include('title')
      end
    end

    describe '#generate_component_parameters' do
      it 'returns empty when no attributes' do
        generator = described_class.new('Test')
        result = generator.send(:generate_component_parameters)
        expect(result).to eq('')
      end

      it 'generates parameter assignments for attributes' do
        generator = described_class.new('Test', { attributes: { 'title' => 'String' } })
        result = generator.send(:generate_component_parameters)
        expect(result).to include('title =')
      end
    end

    describe '#generate_helper_methods' do
      it 'returns empty when no attributes' do
        generator = described_class.new('Test')
        result = generator.send(:generate_helper_methods)
        expect(result).to eq('')
      end

      it 'generates string parser for string attributes' do
        # String attributes don't need helper methods; they are parsed inline via
        # ResourceResolver.resolveText, so the helper block is empty.
        generator = described_class.new('Test', { attributes: { 'title' => 'String' } })
        result = generator.send(:generate_helper_methods)
        expect(result).to eq('')
      end

      it 'generates int parser for int attributes' do
        generator = described_class.new('Test', { attributes: { 'count' => 'Int' } })
        result = generator.send(:generate_helper_methods)
        expect(result).to include('resolveInt')
      end

      it 'generates boolean parser for boolean attributes' do
        generator = described_class.new('Test', { attributes: { 'enabled' => 'Bool' } })
        result = generator.send(:generate_helper_methods)
        expect(result).to include('resolveBool')
      end

      it 'generates color parser for color attributes' do
        # Color attributes rely on ColorParser inlined in parameter parsing; no helper method is emitted.
        generator = described_class.new('Test', { attributes: { 'bg' => 'Color' } })
        result = generator.send(:generate_helper_methods)
        expect(result).to eq('')
      end
    end
  end
end
