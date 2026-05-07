# frozen_string_literal: true

require 'compose/generators/kotlin_component_generator'
require 'core/config_manager'
require 'core/project_finder'

RSpec.describe KjuiTools::Compose::Generators::KotlinComponentGenerator do
  let(:temp_dir) { Dir.mktmpdir }
  let(:config) do
    {
      '_config_dir' => temp_dir,
      'source_directory' => 'src/main',
      'package_name' => 'com.example.app'
    }
  end

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_package_name).and_return('com.example.app')
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'sets component name' do
      generator = described_class.new('CustomCard')
      expect(generator.instance_variable_get(:@component_name)).to eq('CustomCard')
    end

    it 'sets package name with extensions' do
      generator = described_class.new('CustomCard')
      expect(generator.instance_variable_get(:@package_name)).to include('.extensions')
    end
  end

  describe 'private methods' do
    let(:generator) { described_class.new('CustomCard') }

    describe '#get_package_name' do
      it 'returns package name with extensions suffix' do
        result = generator.send(:get_package_name)
        expect(result).to eq('com.example.app.extensions')
      end
    end

    describe '#map_type_to_kotlin' do
      it 'maps string to String' do
        expect(generator.send(:map_type_to_kotlin, 'string')).to eq('String')
      end

      it 'maps text to String' do
        expect(generator.send(:map_type_to_kotlin, 'text')).to eq('String')
      end

      it 'maps int to Int' do
        expect(generator.send(:map_type_to_kotlin, 'int')).to eq('Int')
      end

      it 'maps integer to Int' do
        expect(generator.send(:map_type_to_kotlin, 'integer')).to eq('Int')
      end

      it 'maps float to Float' do
        expect(generator.send(:map_type_to_kotlin, 'float')).to eq('Float')
      end

      it 'maps double to Double' do
        expect(generator.send(:map_type_to_kotlin, 'double')).to eq('Double')
      end

      it 'maps bool to Boolean' do
        expect(generator.send(:map_type_to_kotlin, 'bool')).to eq('Boolean')
      end

      it 'maps boolean to Boolean' do
        expect(generator.send(:map_type_to_kotlin, 'boolean')).to eq('Boolean')
      end

      it 'maps color to Color' do
        expect(generator.send(:map_type_to_kotlin, 'color')).to eq('Color')
      end

      it 'maps dp to Dp' do
        expect(generator.send(:map_type_to_kotlin, 'dp')).to eq('Dp')
      end

      it 'maps size to Dp' do
        expect(generator.send(:map_type_to_kotlin, 'size')).to eq('Dp')
      end

      it 'maps alignment to Alignment' do
        expect(generator.send(:map_type_to_kotlin, 'alignment')).to eq('Alignment')
      end

      it 'maps unknown to Any' do
        expect(generator.send(:map_type_to_kotlin, 'unknown')).to eq('Any')
      end
    end

    describe '#get_default_value' do
      it 'returns empty string default for string' do
        expect(generator.send(:get_default_value, 'string')).to eq(' = ""')
      end

      it 'returns 0 default for int' do
        expect(generator.send(:get_default_value, 'int')).to eq(' = 0')
      end

      it 'returns 0f default for float' do
        expect(generator.send(:get_default_value, 'float')).to eq(' = 0f')
      end

      it 'returns 0.0 default for double' do
        expect(generator.send(:get_default_value, 'double')).to eq(' = 0.0')
      end

      it 'returns false default for bool' do
        expect(generator.send(:get_default_value, 'bool')).to eq(' = false')
      end

      it 'returns Color.Unspecified for color' do
        expect(generator.send(:get_default_value, 'color')).to eq(' = Color.Unspecified')
      end

      it 'returns 0.dp for dp' do
        expect(generator.send(:get_default_value, 'dp')).to eq(' = 0.dp')
      end

      it 'returns Alignment.TopStart for alignment' do
        expect(generator.send(:get_default_value, 'alignment')).to eq(' = Alignment.TopStart')
      end

      it 'returns null for unknown' do
        expect(generator.send(:get_default_value, 'unknown')).to eq(' = null')
      end
    end

    describe '#format_attributes_for_command' do
      it 'returns empty string for no attributes' do
        expect(generator.send(:format_attributes_for_command)).to eq('')
      end

      it 'formats attributes correctly' do
        generator_with_attrs = described_class.new('CustomCard', attributes: { 'title' => 'String', 'count' => 'Int' })
        result = generator_with_attrs.send(:format_attributes_for_command)
        expect(result).to include('--attr title:String')
        expect(result).to include('--attr count:Int')
      end
    end

    describe '#generate_kotlin_imports' do
      it 'returns empty string for no attributes' do
        expect(generator.send(:generate_kotlin_imports)).to eq('')
      end

      it 'adds Color import for color type' do
        generator_with_attrs = described_class.new('CustomCard', attributes: { 'color' => 'Color' })
        result = generator_with_attrs.send(:generate_kotlin_imports)
        expect(result).to include('import androidx.compose.ui.graphics.Color')
      end

      it 'adds dp imports for dp type' do
        generator_with_attrs = described_class.new('CustomCard', attributes: { 'size' => 'dp' })
        result = generator_with_attrs.send(:generate_kotlin_imports)
        expect(result).to include('import androidx.compose.ui.unit.dp')
        expect(result).to include('import androidx.compose.ui.unit.Dp')
      end

      it 'adds Alignment import for alignment type' do
        generator_with_attrs = described_class.new('CustomCard', attributes: { 'align' => 'alignment' })
        result = generator_with_attrs.send(:generate_kotlin_imports)
        expect(result).to include('import androidx.compose.ui.Alignment')
      end
    end

    describe '#generate_kotlin_parameters' do
      it 'returns empty string for no attributes' do
        expect(generator.send(:generate_kotlin_parameters)).to eq('')
      end

      it 'generates parameters with types and defaults' do
        generator_with_attrs = described_class.new('CustomCard', attributes: { 'title' => 'String' })
        result = generator_with_attrs.send(:generate_kotlin_parameters)
        expect(result).to include('title: String = ""')
      end
    end

    describe '#container_template' do
      it 'generates container template with BoxScope' do
        result = generator.send(:container_template)
        expect(result).to include('BoxScope')
        expect(result).to include('content: @Composable BoxScope.() -> Unit')
      end

      it 'includes component name' do
        result = generator.send(:container_template)
        expect(result).to include('fun CustomCard(')
      end
    end

    describe '#non_container_template' do
      it 'generates non-container template' do
        generator_non_container = described_class.new('CustomCard', is_container: false)
        result = generator_non_container.send(:non_container_template)
        expect(result).not_to include('BoxScope')
        expect(result).to include('modifier: Modifier = Modifier')
      end
    end

    describe '#kotlin_template' do
      it 'returns container template by default' do
        result = generator.send(:kotlin_template)
        expect(result).to include('BoxScope')
      end

      it 'returns non-container template when is_container is false' do
        generator_non_container = described_class.new('CustomCard', is_container: false)
        result = generator_non_container.send(:kotlin_template)
        expect(result).not_to include('BoxScope.() -> Unit')
      end
    end
  end
end
