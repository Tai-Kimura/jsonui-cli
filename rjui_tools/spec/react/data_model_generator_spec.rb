# frozen_string_literal: true

require_relative '../spec_helper'
require 'react/data_model_generator'

RSpec.describe RjuiTools::React::DataModelGenerator do
  describe '#extract_data_properties' do
    let(:generator) { described_class.new }

    it 'extracts data properties from data-only element' do
      json_data = {
        'type' => 'View',
        'child' => [
          { 'data' => [
            { 'name' => 'title', 'class' => 'String' },
            { 'name' => 'count', 'class' => 'Int' }
          ] },
          { 'type' => 'Label', 'text' => '@{title}' }
        ]
      }

      properties = generator.send(:extract_data_properties, json_data)
      expect(properties.size).to eq(2)
      expect(properties[0]['name']).to eq('title')
      expect(properties[0]['tsType']).to eq('string')
      expect(properties[1]['name']).to eq('count')
      expect(properties[1]['tsType']).to eq('number')
    end

    it 'extracts callback properties' do
      json_data = {
        'type' => 'View',
        'child' => [
          { 'data' => [
            { 'name' => 'onTap', 'class' => '(() -> Void)' }
          ] }
        ]
      }

      properties = generator.send(:extract_data_properties, json_data)
      expect(properties.size).to eq(1)
      expect(properties[0]['name']).to eq('onTap')
    end

    it 'returns empty array when no data section exists' do
      json_data = {
        'type' => 'View',
        'child' => [
          { 'type' => 'Label', 'text' => 'Hello' }
        ]
      }

      properties = generator.send(:extract_data_properties, json_data)
      expect(properties).to be_empty
    end
  end

  describe '#extract_onclick_actions' do
    let(:generator) { described_class.new }

    it 'extracts onclick actions from JSON' do
      json_data = {
        'type' => 'View',
        'child' => [
          { 'type' => 'Button', 'onclick' => 'handleTap' },
          { 'type' => 'Button', 'onclick' => 'handleSubmit' }
        ]
      }

      actions = generator.send(:extract_onclick_actions, json_data)
      expect(actions).to contain_exactly('handleTap', 'handleSubmit')
    end

    it 'returns unique actions' do
      json_data = {
        'type' => 'View',
        'child' => [
          { 'type' => 'Button', 'onclick' => 'handleTap' },
          { 'type' => 'Button', 'onclick' => 'handleTap' }
        ]
      }

      actions = generator.send(:extract_onclick_actions, json_data)
      expect(actions.size).to eq(1)
      expect(actions).to include('handleTap')
    end

    it 'returns empty array when no onclick exists' do
      json_data = {
        'type' => 'View',
        'child' => [
          { 'type' => 'Label', 'text' => 'Hello' }
        ]
      }

      actions = generator.send(:extract_onclick_actions, json_data)
      expect(actions).to be_empty
    end
  end

  describe '#generate_typescript_content' do
    let(:generator) { described_class.new }

    before do
      generator.instance_variable_set(:@use_typescript, true)
    end

    it 'generates TypeScript interface with properties' do
      data_properties = [
        { 'name' => 'title', 'tsType' => 'string' },
        { 'name' => 'count', 'tsType' => 'number', 'defaultValue' => '0' }
      ]

      content = generator.send(:generate_typescript_content, 'Home', data_properties, [])

      expect(content).to include('export interface HomeData')
      expect(content).to include('title?: string;')
      expect(content).to include('count: number;')
      expect(content).to include('export const createHomeData')
    end

    it 'generates interface with onclick actions' do
      onclick_actions = ['handleTap', 'handleSubmit']

      content = generator.send(:generate_typescript_content, 'Home', [], onclick_actions)

      expect(content).to include('handleTap?: () => void;')
      expect(content).to include('handleSubmit?: () => void;')
    end
  end

  describe '#to_pascal_case' do
    let(:generator) { described_class.new }

    it 'converts snake_case to PascalCase' do
      expect(generator.send(:to_pascal_case, 'home_view')).to eq('HomeView')
    end

    it 'converts kebab-case to PascalCase' do
      expect(generator.send(:to_pascal_case, 'home-view')).to eq('HomeView')
    end

    it 'handles already PascalCase input' do
      expect(generator.send(:to_pascal_case, 'HomeView')).to eq('HomeView')
    end
  end

  describe '#extract_event_bindings_for_type' do
    let(:generator) { described_class.new }

    it 'extracts event bindings from onClick' do
      json_data = {
        'type' => 'Button',
        'onClick' => '@{handleTap}'
      }

      result = generator.send(:extract_event_bindings_for_type, json_data)
      expect(result['handleTap']).to eq({ component: 'Button', attribute: 'onClick' })
    end

    it 'extracts event bindings from onValueChange' do
      json_data = {
        'type' => 'Switch',
        'onValueChange' => '@{onToggle}'
      }

      result = generator.send(:extract_event_bindings_for_type, json_data)
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

      result = generator.send(:extract_event_bindings_for_type, json_data)
      expect(result['buttonTap']).to eq({ component: 'Button', attribute: 'onClick' })
      expect(result['toggleChange']).to eq({ component: 'Toggle', attribute: 'onValueChange' })
    end

    it 'ignores non-binding values' do
      json_data = {
        'type' => 'Button',
        'onClick' => 'notABinding'
      }

      result = generator.send(:extract_event_bindings_for_type, json_data)
      expect(result).to be_empty
    end

    it 'handles single child (not array)' do
      json_data = {
        'type' => 'View',
        'child' => { 'type' => 'Slider', 'onValueChange' => '@{sliderChange}' }
      }

      result = generator.send(:extract_event_bindings_for_type, json_data)
      expect(result['sliderChange']).to eq({ component: 'Slider', attribute: 'onValueChange' })
    end
  end

  describe '#extract_data_properties with Event type conversion' do
    let(:generator) { described_class.new }

    before do
      RjuiTools::Core::TypeConverter.clear_type_mapping_cache
    end

    it 'converts Event type to React event type based on event binding' do
      json_data = {
        'type' => 'View',
        'data' => [
          { 'name' => 'onToggle', 'class' => '((Event) -> void)?' }
        ],
        'child' => {
          'type' => 'Switch',
          'onValueChange' => '@{onToggle}'
        }
      }

      event_bindings = generator.send(:extract_event_bindings_for_type, json_data)
      result = generator.send(:extract_data_properties, json_data, [], true, event_bindings)

      expect(result.length).to eq(1)
      # Event should be converted to React.ChangeEvent<HTMLInputElement> for Switch.onValueChange
      expect(result[0]['tsType']).to include('React.ChangeEvent<HTMLInputElement>')
    end

    it 'converts Event type for Button onClick' do
      json_data = {
        'type' => 'View',
        'data' => [
          { 'name' => 'handleTap', 'class' => '((Event) -> void)?' }
        ],
        'child' => {
          'type' => 'Button',
          'onClick' => '@{handleTap}'
        }
      }

      event_bindings = generator.send(:extract_event_bindings_for_type, json_data)
      result = generator.send(:extract_data_properties, json_data, [], true, event_bindings)

      expect(result.length).to eq(1)
      # Event should be converted to React.MouseEvent<HTMLButtonElement> for Button.onClick
      expect(result[0]['tsType']).to include('React.MouseEvent<HTMLButtonElement>')
    end

    it 'converts Event type for TextField onTextChange' do
      json_data = {
        'type' => 'View',
        'data' => [
          { 'name' => 'onTextUpdate', 'class' => '((Event) -> void)?' }
        ],
        'child' => {
          'type' => 'TextField',
          'onTextChange' => '@{onTextUpdate}'
        }
      }

      event_bindings = generator.send(:extract_event_bindings_for_type, json_data)
      result = generator.send(:extract_data_properties, json_data, [], true, event_bindings)

      expect(result.length).to eq(1)
      # Event should be converted to React.ChangeEvent<HTMLInputElement> for TextField.onTextChange
      expect(result[0]['tsType']).to include('React.ChangeEvent<HTMLInputElement>')
    end

    it 'leaves non-Event types unchanged' do
      json_data = {
        'type' => 'View',
        'data' => [
          { 'name' => 'onToggle', 'class' => '((boolean) -> void)?' }
        ],
        'child' => {
          'type' => 'Switch',
          'onValueChange' => '@{onToggle}'
        }
      }

      event_bindings = generator.send(:extract_event_bindings_for_type, json_data)
      result = generator.send(:extract_data_properties, json_data, [], true, event_bindings)

      expect(result.length).to eq(1)
      # Non-Event type should remain unchanged (converted to TypeScript)
      expect(result[0]['tsType']).to include('boolean')
    end

    it 'handles unbound Event type (no conversion)' do
      json_data = {
        'type' => 'View',
        'data' => [
          { 'name' => 'unboundHandler', 'class' => '((Event) -> void)?' }
        ]
      }

      event_bindings = generator.send(:extract_event_bindings_for_type, json_data)
      result = generator.send(:extract_data_properties, json_data, [], true, event_bindings)

      expect(result.length).to eq(1)
      # Unbound Event type should remain unchanged
      expect(result[0]['tsType']).to include('Event')
    end
  end
end
