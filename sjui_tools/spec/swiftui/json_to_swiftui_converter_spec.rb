# frozen_string_literal: true

require 'swiftui/json_to_swiftui_converter'

RSpec.describe SjuiTools::SwiftUI::JsonToSwiftUIConverter do
  let(:converter) { described_class.new }
  let(:temp_dir) { File.realpath(Dir.mktmpdir('converter_test')) }

  before do
    allow(SjuiTools::SwiftUI::StyleLoader).to receive(:load_and_merge) { |data| data }
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#convert_component' do
    it 'converts Label component' do
      json_data = { 'type' => 'Label', 'text' => 'Hello' }
      result = converter.convert_component(json_data)

      expect(result).to include('Hello')
    end

    it 'converts Button component' do
      json_data = { 'type' => 'Button', 'text' => 'Click Me' }
      result = converter.convert_component(json_data)

      expect(result).to include('Button')
      expect(result).to include('Click Me')
    end

    it 'converts View with children' do
      json_data = {
        'type' => 'View',
        'child' => [
          { 'type' => 'Label', 'text' => 'Child 1' },
          { 'type' => 'Label', 'text' => 'Child 2' }
        ]
      }
      result = converter.convert_component(json_data)

      expect(result).to include('Child 1')
      expect(result).to include('Child 2')
    end

    it 'respects indent level' do
      json_data = { 'type' => 'Label', 'text' => 'Test' }
      result = converter.convert_component(json_data, 2)

      expect(result).to include('Test')
    end
  end

  describe '#convert_json_to_view' do
    let(:json_file) { File.join(temp_dir, 'test.json') }

    it 'converts JSON file to SwiftUI code' do
      json_content = { 'type' => 'View', 'child' => { 'type' => 'Label', 'text' => 'Hello' } }
      File.write(json_file, JSON.generate(json_content))

      code, actions = converter.convert_json_to_view(json_file)

      expect(code).to include('Hello')
      expect(actions).to be_an(Array)
    end

    it 'raises error for non-existent file' do
      expect { converter.convert_json_to_view('/nonexistent.json') }.to raise_error(/not found/)
    end

    it 'extracts onclick actions' do
      json_content = {
        'type' => 'Button',
        'text' => 'Submit',
        'onClick' => 'handleSubmit'
      }
      File.write(json_file, JSON.generate(json_content))

      code, actions = converter.convert_json_to_view(json_file)

      expect(actions).to include('handleSubmit')
    end

    it 'extracts nested onclick actions' do
      json_content = {
        'type' => 'View',
        'child' => [
          { 'type' => 'Button', 'text' => 'A', 'onClick' => 'actionA' },
          { 'type' => 'Button', 'text' => 'B', 'onClick' => 'actionB' }
        ]
      }
      File.write(json_file, JSON.generate(json_content))

      code, actions = converter.convert_json_to_view(json_file)

      expect(actions).to include('actionA')
      expect(actions).to include('actionB')
    end
  end

  describe '#process_includes' do
    it 'expands include and uses included type' do
      json_data = { 'include' => 'header' }
      include_file = File.join(temp_dir, 'header.json')
      File.write(include_file, '{"type": "View"}')

      result = converter.process_includes(json_data, temp_dir)

      # Include is expanded inline, so type comes from included file
      expect(result['type']).to eq('View')
    end

    it 'raises error for missing include file' do
      json_data = { 'include' => 'nonexistent' }

      expect { converter.process_includes(json_data, temp_dir) }.to raise_error(/Include file not found/)
    end

    it 'processes child includes recursively' do
      json_data = {
        'type' => 'View',
        'child' => [
          { 'include' => 'part1' },
          { 'type' => 'Label', 'text' => 'Hello' }
        ]
      }
      File.write(File.join(temp_dir, 'part1.json'), '{"type": "View"}')

      result = converter.process_includes(json_data, temp_dir)

      # Include is expanded inline, so type comes from included file
      expect(result['child'][0]['type']).to eq('View')
      expect(result['child'][1]['type']).to eq('Label')
    end

    it 'normalizes children to child' do
      json_data = {
        'type' => 'View',
        'children' => [
          { 'type' => 'Label', 'text' => 'Test' }
        ]
      }

      result = converter.process_includes(json_data, temp_dir)

      expect(result['child']).not_to be_nil
      expect(result['children']).to be_nil
    end

    it 'returns non-hash data unchanged' do
      expect(converter.process_includes('string', temp_dir)).to eq('string')
      expect(converter.process_includes(nil, temp_dir)).to be_nil
    end
  end

  describe '#extract_onclick_actions' do
    before do
      converter.instance_variable_set(:@onclick_actions, Set.new)
    end

    it 'extracts onclick from hash' do
      json_data = { 'onClick' => 'myAction' }
      converter.extract_onclick_actions(json_data)

      actions = converter.instance_variable_get(:@onclick_actions)
      expect(actions).to include('myAction')
    end

    it 'extracts from nested children' do
      json_data = {
        'type' => 'View',
        'children' => [
          { 'onClick' => 'action1' },
          { 'onClick' => 'action2' }
        ]
      }
      converter.extract_onclick_actions(json_data)

      actions = converter.instance_variable_get(:@onclick_actions)
      expect(actions).to include('action1')
      expect(actions).to include('action2')
    end

    it 'handles array input' do
      json_data = [
        { 'onClick' => 'arrayAction1' },
        { 'onClick' => 'arrayAction2' }
      ]
      converter.extract_onclick_actions(json_data)

      actions = converter.instance_variable_get(:@onclick_actions)
      expect(actions).to include('arrayAction1')
      expect(actions).to include('arrayAction2')
    end

    it 'ignores non-string onclick values' do
      json_data = { 'onClick' => { 'complex' => 'object' } }
      converter.extract_onclick_actions(json_data)

      actions = converter.instance_variable_get(:@onclick_actions)
      expect(actions).to be_empty
    end
  end

  describe '#convert_file' do
    let(:json_file) { File.join(temp_dir, 'my_view.json') }
    let(:output_file) { File.join(temp_dir, 'MyViewView.swift') }

    it 'generates Swift file from JSON' do
      json_content = { 'type' => 'View', 'child' => { 'type' => 'Label', 'text' => 'Hello' } }
      File.write(json_file, JSON.generate(json_content))

      result = converter.convert_file(json_file)

      expect(File.exist?(result)).to be true
      content = File.read(result)
      expect(content).to include('import SwiftUI')
      expect(content).to include('struct MyViewView: View')
    end

    it 'converts snake_case to PascalCase' do
      snake_file = File.join(temp_dir, 'my_complex_view.json')
      File.write(snake_file, '{"type": "View"}')

      result = converter.convert_file(snake_file)

      content = File.read(result)
      expect(content).to include('struct MyComplexViewView: View')
    end

    it 'removes underscore prefix' do
      prefixed_file = File.join(temp_dir, '_partial_view.json')
      File.write(prefixed_file, '{"type": "View"}')

      result = converter.convert_file(prefixed_file)

      content = File.read(result)
      expect(content).to include('struct PartialViewView: View')
    end

    it 'uses custom output path' do
      File.write(json_file, '{"type": "View"}')
      custom_output = File.join(temp_dir, 'CustomOutput.swift')

      result = converter.convert_file(json_file, custom_output)

      expect(result).to eq(custom_output)
      expect(File.exist?(custom_output)).to be true
    end

    it 'raises error for non-existent file' do
      expect { converter.convert_file('/nonexistent.json') }.to raise_error(/not found/)
    end

    it 'includes preview code' do
      File.write(json_file, '{"type": "View"}')

      result = converter.convert_file(json_file)
      content = File.read(result)

      expect(content).to include('PreviewProvider')
      expect(content).to include('previews')
    end
  end
end
