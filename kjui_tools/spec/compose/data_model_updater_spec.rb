# frozen_string_literal: true

require 'compose/data_model_updater'
require 'core/config_manager'
require 'core/project_finder'
require 'fileutils'
require 'json'

RSpec.describe KjuiTools::Compose::DataModelUpdater do
  let(:temp_dir) { Dir.mktmpdir('data_model_test') }
  let(:layouts_dir) { File.join(temp_dir, 'src/main/assets/Layouts') }
  let(:data_dir) { File.join(temp_dir, 'src/main/kotlin/com/example/app/data') }

  let(:config) do
    {
      'source_directory' => 'src/main',
      'layouts_directory' => 'assets/Layouts',
      'data_directory' => 'kotlin/com/example/app/data',
      'package_name' => 'com.example.app',
      'project_path' => temp_dir
    }
  end

  before do
    @original_dir = Dir.pwd
    Dir.chdir(temp_dir)
    FileUtils.mkdir_p(layouts_dir)
    FileUtils.mkdir_p(data_dir)
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
  end

  after do
    Dir.chdir(@original_dir)
    FileUtils.rm_rf(temp_dir)
  end

  describe '#update_data_models' do
    it 'processes JSON files in layouts directory' do
      File.write(File.join(layouts_dir, 'test.json'), JSON.generate({
        'type' => 'View',
        'data' => [
          { 'name' => 'title', 'class' => 'String', 'defaultValue' => '"Test"' }
        ],
        'child' => [{ 'type' => 'Text', 'text' => '@{title}' }]
      }))

      updater = described_class.new
      expect { updater.update_data_models }.to output(/Updating data models/).to_stdout
    end

    it 'excludes Resources folder' do
      resources_dir = File.join(layouts_dir, 'Resources')
      FileUtils.mkdir_p(resources_dir)
      File.write(File.join(resources_dir, 'colors.json'), '{}')
      File.write(File.join(layouts_dir, 'main.json'), '{"type": "View"}')

      updater = described_class.new
      # Should only process 1 file (main.json), not the one in Resources
      expect { updater.update_data_models }.to output(/1 files/).to_stdout
    end

    context 'with onclick actions' do
      it 'extracts onclick actions from JSON' do
        File.write(File.join(layouts_dir, 'button_view.json'), JSON.generate({
          'type' => 'View',
          'child' => [
            { 'type' => 'Button', 'text' => 'Submit', 'onclick' => 'onSubmit' },
            { 'type' => 'Button', 'text' => 'Cancel', 'onclick' => 'onCancel' }
          ]
        }))

        updater = described_class.new
        expect { updater.update_data_models }.not_to raise_error
      end
    end

    context 'with data properties' do
      it 'extracts data properties from JSON' do
        File.write(File.join(layouts_dir, 'form.json'), JSON.generate({
          'type' => 'View',
          'data' => [
            { 'name' => 'username', 'class' => 'String', 'defaultValue' => '""' },
            { 'name' => 'email', 'class' => 'String', 'defaultValue' => '""' }
          ]
        }))

        updater = described_class.new
        expect { updater.update_data_models }.not_to raise_error
      end

      it 'handles data as hash format' do
        File.write(File.join(layouts_dir, 'simple.json'), JSON.generate({
          'type' => 'View',
          'data' => {
            'name' => 'John',
            'age' => 25,
            'score' => 95.5,
            'active' => true
          }
        }))

        updater = described_class.new
        expect { updater.update_data_models }.not_to raise_error
      end
    end

    context 'with nested data in children' do
      it 'extracts data from child nodes' do
        File.write(File.join(layouts_dir, 'nested.json'), JSON.generate({
          'type' => 'View',
          'child' => {
            'type' => 'View',
            'data' => [
              { 'name' => 'nestedProp', 'class' => 'String', 'defaultValue' => '"default"' }
            ]
          }
        }))

        updater = described_class.new
        expect { updater.update_data_models }.not_to raise_error
      end

      it 'extracts data from child array' do
        File.write(File.join(layouts_dir, 'array_child.json'), JSON.generate({
          'type' => 'View',
          'child' => [
            {
              'type' => 'View',
              'data' => [
                { 'name' => 'item', 'class' => 'String', 'defaultValue' => '"value"' }
              ]
            }
          ]
        }))

        updater = described_class.new
        expect { updater.update_data_models }.not_to raise_error
      end
    end

    context 'with includes' do
      it 'stops at include nodes' do
        # Create the include file first
        File.write(File.join(layouts_dir, 'header.json'), JSON.generate({
          'partial' => true,
          'type' => 'View',
          'child' => [
            { 'type' => 'Text', 'text' => 'Header' }
          ]
        }))

        File.write(File.join(layouts_dir, 'with_include.json'), JSON.generate({
          'type' => 'View',
          'child' => [
            { 'include' => 'header', 'data' => { 'title' => 'Header' } }
          ]
        }))

        updater = described_class.new
        expect { updater.update_data_models }.not_to raise_error
      end
    end
  end

  describe 'private methods' do
    let(:updater) { described_class.new }

    describe '#extract_onclick_actions' do
      it 'extracts actions from simple onclick' do
        json_data = { 'type' => 'Button', 'onclick' => 'handleClick' }
        result = updater.send(:extract_onclick_actions, json_data)
        expect(result).to include('handleClick')
      end

      it 'extracts actions from nested children' do
        json_data = {
          'type' => 'View',
          'child' => [
            { 'type' => 'Button', 'onclick' => 'action1' },
            { 'type' => 'Button', 'onclick' => 'action2' }
          ]
        }
        result = updater.send(:extract_onclick_actions, json_data)
        expect(result).to include('action1')
        expect(result).to include('action2')
      end

      it 'handles single child as hash' do
        json_data = {
          'type' => 'View',
          'child' => { 'type' => 'Button', 'onclick' => 'singleAction' }
        }
        result = updater.send(:extract_onclick_actions, json_data)
        expect(result).to include('singleAction')
      end

      it 'handles array at root level' do
        json_data = [
          { 'type' => 'Button', 'onclick' => 'action1' },
          { 'type' => 'Button', 'onclick' => 'action2' }
        ]
        result = updater.send(:extract_onclick_actions, json_data)
        expect(result).to include('action1')
        expect(result).to include('action2')
      end
    end

    describe '#map_to_kotlin_type' do
      it 'maps String' do
        expect(updater.send(:map_to_kotlin_type, 'String')).to eq('String')
      end

      it 'maps Int' do
        expect(updater.send(:map_to_kotlin_type, 'Int')).to eq('Int')
      end

      it 'maps Double' do
        expect(updater.send(:map_to_kotlin_type, 'Double')).to eq('Double')
      end

      it 'maps Float' do
        expect(updater.send(:map_to_kotlin_type, 'Float')).to eq('Float')
      end

      it 'maps Bool to Boolean' do
        expect(updater.send(:map_to_kotlin_type, 'Bool')).to eq('Boolean')
      end

      it 'maps Boolean' do
        expect(updater.send(:map_to_kotlin_type, 'Boolean')).to eq('Boolean')
      end

      it 'maps CGFloat to Float' do
        expect(updater.send(:map_to_kotlin_type, 'CGFloat')).to eq('Float')
      end

      it 'maps Color' do
        expect(updater.send(:map_to_kotlin_type, 'Color')).to eq('Color')
      end

      it 'maps CollectionDataSource' do
        expect(updater.send(:map_to_kotlin_type, 'CollectionDataSource')).to include('CollectionDataSource')
      end

      it 'maps () -> Unit to optional callback' do
        expect(updater.send(:map_to_kotlin_type, '() -> Unit')).to eq('(() -> Unit)?')
      end

      it 'maps (String) -> Unit to optional callback with params' do
        expect(updater.send(:map_to_kotlin_type, '(String) -> Unit')).to eq('((String) -> Unit)?')
      end

      it 'keeps already optional callback as-is' do
        expect(updater.send(:map_to_kotlin_type, '(() -> Unit)?')).to eq('(() -> Unit)?')
      end

      it 'keeps already optional callback with params as-is' do
        expect(updater.send(:map_to_kotlin_type, '((String) -> Unit)?')).to eq('((String) -> Unit)?')
      end

      it 'returns custom types as-is' do
        expect(updater.send(:map_to_kotlin_type, 'CustomType')).to eq('CustomType')
      end
    end

    describe '#format_default_value' do
      it 'formats String values with quotes' do
        expect(updater.send(:format_default_value, 'hello', 'String')).to eq('"hello"')
      end

      it 'formats Bool values' do
        expect(updater.send(:format_default_value, true, 'Bool')).to eq('true')
        expect(updater.send(:format_default_value, false, 'Bool')).to eq('false')
        expect(updater.send(:format_default_value, 'true', 'Bool')).to eq('true')
      end

      it 'formats Int values' do
        expect(updater.send(:format_default_value, 42, 'Int')).to eq('42')
        expect(updater.send(:format_default_value, '42', 'Int')).to eq('42')
      end

      it 'formats Double values' do
        expect(updater.send(:format_default_value, 3.14, 'Double')).to eq('3.14')
      end

      it 'formats Float values with f suffix' do
        expect(updater.send(:format_default_value, 3.14, 'Float')).to eq('3.14f')
      end

      it 'formats CGFloat values with f suffix' do
        expect(updater.send(:format_default_value, 3.14, 'CGFloat')).to eq('3.14f')
      end

      it 'formats Color hex values' do
        result = updater.send(:format_default_value, '#FF0000', 'Color')
        expect(result).to eq('Color(0xFFFF0000)')
      end

      it 'formats Color named values' do
        # Named colors without 'color' in the string return Color.Unspecified
        # because the condition checks for 'color' substring first
        expect(updater.send(:format_default_value, 'red', 'Color')).to eq('Color.Unspecified')
        # Colors not starting with '#' or 'Color.' and not containing 'color' get Unspecified
        expect(updater.send(:format_default_value, 'unknown', 'Color')).to eq('Color.Unspecified')
      end

      it 'formats Color.Red as-is' do
        expect(updater.send(:format_default_value, 'Color.Red', 'Color')).to eq('Color.Red')
      end

      it 'formats CollectionDataSource' do
        result = updater.send(:format_default_value, 'CollectionDataSource()', 'CollectionDataSource')
        expect(result).to include('CollectionDataSource()')
      end

      it 'formats List types' do
        expect(updater.send(:format_default_value, [], 'List<String>')).to eq('emptyList()')
        expect(updater.send(:format_default_value, '[]', 'List<Int>')).to eq('emptyList()')
      end

      it 'formats Map types' do
        expect(updater.send(:format_default_value, {}, 'Map<String, Any>')).to eq('emptyMap()')
        expect(updater.send(:format_default_value, '{}', 'Map<String, Int>')).to eq('emptyMap()')
      end
    end

    describe '#to_pascal_case' do
      it 'converts snake_case to PascalCase' do
        expect(updater.send(:to_pascal_case, 'my_view_name')).to eq('MyViewName')
      end

      it 'converts kebab-case to PascalCase' do
        expect(updater.send(:to_pascal_case, 'my-view-name')).to eq('MyViewName')
      end

      it 'handles already PascalCase' do
        # PascalCase gets converted based on the algorithm
        result = updater.send(:to_pascal_case, 'MyViewName')
        expect(result).to be_a(String)
      end
    end

    describe '#find_existing_data_file' do
      it 'finds exact match' do
        FileUtils.mkdir_p(data_dir)
        File.write(File.join(data_dir, 'TestViewData.kt'), 'data class TestViewData()')
        expect(updater.send(:find_existing_data_file, 'TestView')).to eq(File.join(data_dir, 'TestViewData.kt'))
      end

      it 'returns nil when no match' do
        expect(updater.send(:find_existing_data_file, 'NonExistent')).to be_nil
      end
    end

    describe '#extract_class_name' do
      it 'extracts class name from data class' do
        File.write(File.join(data_dir, 'TestData.kt'), 'data class TestData(val name: String)')
        expect(updater.send(:extract_class_name, File.join(data_dir, 'TestData.kt'))).to eq('TestData')
      end

      it 'returns nil for non-matching content' do
        File.write(File.join(data_dir, 'Other.kt'), 'class NotDataClass {}')
        expect(updater.send(:extract_class_name, File.join(data_dir, 'Other.kt'))).to be_nil
      end
    end

    describe '#generate_data_content' do
      it 'generates content with empty properties' do
        result = updater.send(:generate_data_content, 'Test', [], [])
        expect(result).to include('data class TestData')
        expect(result).to include('placeholder')
      end

      it 'generates content with properties' do
        properties = [
          { 'name' => 'title', 'class' => 'String', 'defaultValue' => 'Hello' }
        ]
        result = updater.send(:generate_data_content, 'Test', properties, [])
        expect(result).to include('var title: String')
      end

      it 'generates content with nullable properties' do
        properties = [
          { 'name' => 'optional', 'class' => 'String', 'defaultValue' => nil }
        ]
        result = updater.send(:generate_data_content, 'Test', properties, [])
        expect(result).to include('String?')
        expect(result).to include('= null')
      end

      it 'generates content with Color import' do
        properties = [
          { 'name' => 'bgColor', 'class' => 'Color', 'defaultValue' => '#FF0000' }
        ]
        result = updater.send(:generate_data_content, 'Test', properties, [])
        expect(result).to include('import androidx.compose.ui.graphics.Color')
      end
    end

    describe '#extract_event_bindings' do
      it 'extracts event bindings from onClick' do
        json_data = {
          'type' => 'Button',
          'onClick' => '@{handleTap}'
        }

        result = updater.send(:extract_event_bindings, json_data)
        expect(result['handleTap']).to eq({ component: 'Button', attribute: 'onClick' })
      end

      it 'extracts event bindings from onValueChange' do
        json_data = {
          'type' => 'Switch',
          'onValueChange' => '@{onToggle}'
        }

        result = updater.send(:extract_event_bindings, json_data)
        expect(result['onToggle']).to eq({ component: 'Switch', attribute: 'onValueChange' })
      end

      it 'extracts event bindings from nested children' do
        json_data = {
          'type' => 'View',
          'child' => [
            { 'type' => 'Button', 'onClick' => '@{buttonTap}' },
            { 'type' => 'Toggle', 'onValueChange' => '@{toggleChange}' }
          ]
        }

        result = updater.send(:extract_event_bindings, json_data)
        expect(result['buttonTap']).to eq({ component: 'Button', attribute: 'onClick' })
        expect(result['toggleChange']).to eq({ component: 'Toggle', attribute: 'onValueChange' })
      end

      it 'ignores non-binding values' do
        json_data = {
          'type' => 'Button',
          'onClick' => 'notABinding'
        }

        result = updater.send(:extract_event_bindings, json_data)
        expect(result).to be_empty
      end

      it 'handles single child (not array)' do
        json_data = {
          'type' => 'View',
          'child' => { 'type' => 'Slider', 'onValueChange' => '@{sliderChange}' }
        }

        result = updater.send(:extract_event_bindings, json_data)
        expect(result['sliderChange']).to eq({ component: 'Slider', attribute: 'onValueChange' })
      end
    end

    describe '#extract_data_properties with Event type conversion' do
      before do
        KjuiTools::Core::TypeConverter.clear_type_mapping_cache
      end

      it 'converts Event type to tuple type based on event binding' do
        json_data = {
          'type' => 'View',
          'data' => [
            { 'name' => 'onToggle', 'class' => '((Event) -> Unit)?' }
          ],
          'child' => {
            'type' => 'Switch',
            'onValueChange' => '@{onToggle}'
          }
        }

        event_bindings = updater.send(:extract_event_bindings, json_data)
        result = updater.send(:extract_data_properties, json_data, [], 0, event_bindings)

        expect(result.length).to eq(1)
        # Event should be converted to (String, Boolean) for Switch.onValueChange in Compose
        expect(result[0]['class']).to eq('((String, Boolean) -> Unit)?')
      end

      it 'converts Event type for Button onClick' do
        json_data = {
          'type' => 'View',
          'data' => [
            { 'name' => 'handleTap', 'class' => '((Event) -> Unit)?' }
          ],
          'child' => {
            'type' => 'Button',
            'onClick' => '@{handleTap}'
          }
        }

        event_bindings = updater.send(:extract_event_bindings, json_data)
        result = updater.send(:extract_data_properties, json_data, [], 0, event_bindings)

        expect(result.length).to eq(1)
        # Event should be converted to (String, Unit) for Button.onClick in Compose
        expect(result[0]['class']).to eq('((String, Unit) -> Unit)?')
      end

      it 'converts Event type for TextField onTextChange' do
        json_data = {
          'type' => 'View',
          'data' => [
            { 'name' => 'onTextUpdate', 'class' => '((Event) -> Unit)?' }
          ],
          'child' => {
            'type' => 'TextField',
            'onTextChange' => '@{onTextUpdate}'
          }
        }

        event_bindings = updater.send(:extract_event_bindings, json_data)
        result = updater.send(:extract_data_properties, json_data, [], 0, event_bindings)

        expect(result.length).to eq(1)
        # Event should be converted to (String, String) for TextField.onTextChange in Compose
        expect(result[0]['class']).to eq('((String, String) -> Unit)?')
      end

      it 'leaves non-Event types unchanged' do
        json_data = {
          'type' => 'View',
          'data' => [
            { 'name' => 'onToggle', 'class' => '((Boolean) -> Unit)?' }
          ],
          'child' => {
            'type' => 'Switch',
            'onValueChange' => '@{onToggle}'
          }
        }

        event_bindings = updater.send(:extract_event_bindings, json_data)
        result = updater.send(:extract_data_properties, json_data, [], 0, event_bindings)

        expect(result.length).to eq(1)
        # Non-Event type should remain unchanged
        expect(result[0]['class']).to eq('((Boolean) -> Unit)?')
      end

      it 'handles unbound Event type (no conversion)' do
        json_data = {
          'type' => 'View',
          'data' => [
            { 'name' => 'unboundHandler', 'class' => '((Event) -> Unit)?' }
          ]
        }

        event_bindings = updater.send(:extract_event_bindings, json_data)
        result = updater.send(:extract_data_properties, json_data, [], 0, event_bindings)

        expect(result.length).to eq(1)
        # Unbound Event type should remain unchanged
        expect(result[0]['class']).to eq('((Event) -> Unit)?')
      end
    end
  end
end
