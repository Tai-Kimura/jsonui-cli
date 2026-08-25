# frozen_string_literal: true

require 'tmpdir'
require 'fileutils'

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

    # `"onclick": "handleTap"` names a data property exactly as `@{handleTap}`
    # does, so a layout is entitled to declare it — and then the synthesized
    # twin collided with the declaration: duplicate identifier in the
    # interface, duplicate key in the factory literal. The declaration wins.
    it 'does not re-emit an onclick action the data section already declares' do
      data_properties = [
        { 'name' => 'handleTap', 'class' => '(String) -> Void',
          'tsType' => '((arg0: string) => void) | undefined' }
      ]

      content = generator.send(:generate_typescript_content, 'Home', data_properties, ['handleTap'])

      expect(content.scan(/^\s*handleTap\??:.*;$/).size).to eq(1)   # interface
      expect(content.scan(/^\s*handleTap: .*,$/).size).to eq(1)     # factory literal
      expect(content).to include('handleTap?: ((arg0: string) => void) | undefined;')
      expect(content).not_to include('handleTap?: () => void;')
    end
  end

  # Regression: nested data-section defaults were emptied to {} / [] —
  # binding_semantics fallbackPrecedence step 1 requires the data-section
  # defaultValue to actually seed the data map before any binding resolves.
  describe '#format_default_value with nested defaults' do
    let(:generator) { described_class.new }

    it 'emits a nested Hash default as a real JS object literal' do
      value = { 'name' => 'Grace', 'meta' => { 'age' => 36 } }
      result = generator.send(:format_default_value, value, 'Record<string, any>')
      expect(result).to eq('{ name: "Grace", meta: { age: 36 } }')
    end

    it 'emits an Array default as a real JS array literal' do
      value = [{ 'title' => 'A', 'done' => false }, { 'title' => 'B', 'done' => true }]
      result = generator.send(:format_default_value, value, 'any[]')
      expect(result).to eq('[{ title: "A", done: false }, { title: "B", done: true }]')
    end

    it 'keeps empty containers compact and quotes non-identifier keys' do
      expect(generator.send(:format_default_value, {}, 'Record<string, any>')).to eq('{}')
      expect(generator.send(:format_default_value, [], 'any[]')).to eq('[]')
      expect(generator.send(:format_default_value, { 'a-b' => 1 }, 'Record<string, any>'))
        .to eq('{ "a-b": 1 }')
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
# The CANONICAL selection spellings. Each of these converters reads its own
# spelling and emits both a `data.<prop>` reference and a report-back handler
# call derived from it, so a binding the data model does not declare becomes
# TS2339 inside an @generated file the consumer cannot patch — the same shape
# as the Radio TS2367 that blocked plan 49's push, reported by lane D.
#
# The conformance fixture corpus does NOT exercise these spellings (adding them
# moved zero generated files), so these pins are the only thing guarding them.
RSpec.describe RjuiTools::React::DataModelGenerator, 'canonical selection bindings' do
  let(:generator) { described_class.new }

  def bindings_for(node)
    generator.send(:extract_value_bindings, node)
  end

  it 'declares a SelectBox selectedDate as a string' do
    b = bindings_for({ 'type' => 'SelectBox', 'id' => 's', 'selectItemType' => 'Date',
                       'selectedDate' => '@{pickedDate}' })
    expect(b['pickedDate']).to include(type: 'string')
  end

  it 'declares a SelectBox selectedValue as a string' do
    b = bindings_for({ 'type' => 'SelectBox', 'id' => 's', 'selectedValue' => '@{choice}' })
    expect(b['choice']).to include(type: 'string')
  end

  it 'declares a Radio selectedValue, reported back through set<Prop>' do
    b = bindings_for({ 'type' => 'Radio', 'id' => 'r', 'selectedValue' => '@{picked}' })
    expect(b['picked']).to include(type: 'string', handler: :setter)
    expect(generator.send(:value_binding_handler_name, 'picked', b['picked'])).to eq('setPicked')
  end

  it 'declares a Segment selectedIndex as a NUMBER, reported back through set<Prop>' do
    b = bindings_for({ 'type' => 'Segment', 'id' => 'g', 'selectedIndex' => '@{tab}' })
    expect(b['tab']).to include(type: 'number', handler: :setter)
    expect(generator.send(:value_binding_handler_name, 'tab', b['tab'])).to eq('setTab')
  end

  # The two converters already emitted these handlers into the JSX; nothing
  # declared them, so every bound-selectedIndex SelectBox/TabView was TS2551
  # in an @generated file the consumer cannot patch (51-A urgent).
  it 'declares a SelectBox selectedIndex as a NUMBER with the on<Prop>Change convention' do
    b = bindings_for({ 'type' => 'SelectBox', 'id' => 's', 'items' => %w[A B],
                       'selectedIndex' => '@{pick}' })
    expect(b['pick']).to include(type: 'number')
    expect(generator.send(:value_binding_handler_name, 'pick', b['pick'])).to eq('onPickChange')
  end

  it 'declares a TabView selectedIndex as a NUMBER, reported back through set<Prop>' do
    b = bindings_for({ 'type' => 'TabView', 'id' => 't', 'selectedIndex' => '@{tab}' })
    expect(b['tab']).to include(type: 'number', handler: :setter)
    expect(generator.send(:value_binding_handler_name, 'tab', b['tab'])).to eq('setTab')
  end

  it 'keeps the on<Prop>Change convention for everything else' do
    b = bindings_for({ 'type' => 'SelectBox', 'id' => 's', 'selectedValue' => '@{choice}' })
    expect(generator.send(:value_binding_handler_name, 'choice', b['choice'])).to eq('onChoiceChange')
  end

  it 'leaves a static selection alone — only bindings become data properties' do
    expect(bindings_for({ 'type' => 'Radio', 'id' => 'r', 'selectedValue' => 'alpha' })).to be_empty
  end
end

RSpec.describe RjuiTools::React::DataModelGenerator, 'focus-state value bindings' do
  let(:generator) { described_class.new }

  it 'adds a boolean <camel>IsFocused binding per id-bearing editable field' do
    json = { 'type' => 'View', 'child' => [
      { 'type' => 'TextField', 'id' => 'email_field' },
      { 'type' => 'TextView', 'id' => 'note_input' },
      { 'type' => 'TextField' }
    ] }
    bindings = generator.send(:extract_value_bindings, json)
    expect(bindings['emailFieldIsFocused']).to eq({ type: 'boolean', defaultValue: false })
    expect(bindings['noteInputIsFocused']).to eq({ type: 'boolean', defaultValue: false })
    expect(bindings.keys.grep(/IsFocused/).size).to eq(2)
  end

  describe '#ensure_unique_layout_basenames! (regression: rjui-cell-data-model-name-collision-across-screens)' do
    let(:generator) { described_class.new }

    it 'aborts when two layouts share a basename across subdirectories' do
      files = ['/x/Layouts/dashboard/breakdown_row.json', '/x/Layouts/sales/breakdown_row.json']
      expect { generator.send(:ensure_unique_layout_basenames!, files) }
        .to raise_error(SystemExit)
        .and output(/duplicate layout file name.*breakdown_row\.json/m).to_stderr
    end

    it 'stays silent for unique basenames' do
      files = ['/x/Layouts/dashboard/breakdown_row.json', '/x/Layouts/sales/sales_breakdown_row.json']
      expect { generator.send(:ensure_unique_layout_basenames!, files) }.not_to raise_error
    end
  end

  describe '#collect_type_map_imports (regression: rjui-data-model-ignores-type-map-custom-types)' do
    let(:generator) { described_class.new }

    before do
      generator.instance_variable_set(:@project_type_map, {
        'SelectOption' => {
          'class' => 'SelectOption',
          'imports' => ['Models'],
          'web' => { 'class' => 'SelectOption', 'imports' => ['@/types/SelectOption'] }
        },
        'AmbientType' => {
          'class' => 'AmbientType',
          'web' => { 'class' => 'AmbientType', 'imports' => [] }
        }
      })
    end

    it 'emits a type import resolved from the web platform entry' do
      props = [{ 'name' => 'regionScopeOptions', 'class' => '[SelectOption]' }]
      lines = generator.send(:collect_type_map_imports, props)
      expect(lines).to eq(["import type { SelectOption } from '@/types/SelectOption';"])
    end

    it 'emits nothing for ambient (imports: []) web entries' do
      props = [{ 'name' => 'x', 'class' => 'AmbientType' }]
      expect(generator.send(:collect_type_map_imports, props)).to be_empty
    end

    it 'ignores tokens not registered in the type map' do
      props = [{ 'name' => 'y', 'class' => 'UnknownThing' }]
      expect(generator.send(:collect_type_map_imports, props)).to be_empty
    end

    it 'wires the import into generated TypeScript content' do
      props = [{ 'name' => 'regionScopeOptions', 'class' => '[SelectOption]', 'defaultValue' => nil }]
      content = generator.send(:generate_typescript_content, 'HeaderBar', props)
      expect(content).to include("import type { SelectOption } from '@/types/SelectOption';")
      expect(content).to include('regionScopeOptions?: SelectOption[];')
    end
  end
  # A String defaultValue whose key the layout's OWN strings.json section
  # declares resolves to a bare StringManager expression (with the import);
  # a sentinel that only foreign sections declare stays literal and SILENT —
  # the data-default canon the sjui face carries since 1.6.3, unified here.
  describe 'string defaultValue resolution (data-default canon)' do
    let(:temp_dir) { Dir.mktmpdir('rjui_data_default') }
    let(:layouts_dir) { File.join(temp_dir, 'Layouts') }
    let(:data_dir) { File.join(temp_dir, 'src/generated/data') }

    before do
      @original_dir = Dir.pwd
      Dir.chdir(temp_dir)
      FileUtils.mkdir_p(File.join(layouts_dir, 'Resources'))
      allow(RjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
        'source_path' => temp_dir,
        'layouts_directory' => 'Layouts',
        'data_directory' => 'src/generated/data'
      })
      File.write(File.join(layouts_dir, 'Resources', 'strings.json'), JSON.generate({
        'note_input' => { 'register' => 'Register' },
        'venue_detail' => { 'today' => 'Today' }
      }))
    end

    after do
      Dir.chdir(@original_dir)
      FileUtils.rm_rf(temp_dir)
    end

    it 'resolves an own-section key to a StringManager expression, with import, silently' do
      File.write(File.join(layouts_dir, 'note_input.json'), JSON.generate({
        'type' => 'View',
        'child' => [
          { 'data' => [{ 'name' => 'label', 'class' => 'String', 'defaultValue' => 'register' }] },
          { 'type' => 'Label', 'text' => '@{label}' }
        ]
      }))

      generator = described_class.new
      expect { generator.update_data_models }.not_to output(/Bare key/).to_stdout

      content = File.read(File.join(data_dir, 'NoteInputData.ts'))
      expect(content).to include('label: StringManager.currentLanguage.noteInputRegister,')
      expect(content).to include("import { StringManager } from '../StringManager';")
    end

    it 'keeps a foreign-declared sentinel literal, with no warning and no import' do
      File.write(File.join(layouts_dir, 'note_input.json'), JSON.generate({
        'type' => 'View',
        'child' => [
          { 'data' => [{ 'name' => 'selectedDateValue', 'class' => 'String', 'defaultValue' => 'today' }] },
          { 'type' => 'Label', 'text' => '@{selectedDateValue}' }
        ]
      }))

      generator = described_class.new
      expect { generator.update_data_models }.not_to output(/Bare key/).to_stdout

      content = File.read(File.join(data_dir, 'NoteInputData.ts'))
      expect(content).to include('selectedDateValue: "today",')
      expect(content).not_to include('StringManager.currentLanguage')
      expect(content).not_to include("import { StringManager }")
    end
  end
  # A kebab-case layout owns the NORMALIZED section spelling the extractor
  # writes (kebab-widget.json -> kebab_widget) — the canonical
  # namespace_candidates route; the hand-rolled spelling this replaced
  # produced "kebab-widget" and silently failed to own it.
  describe 'kebab-case own-section resolution (canonical namespace_candidates)' do
    let(:temp_dir) { Dir.mktmpdir('rjui_kebab_default') }
    let(:layouts_dir) { File.join(temp_dir, 'Layouts') }
    let(:data_dir) { File.join(temp_dir, 'src/generated/data') }

    before do
      @original_dir = Dir.pwd
      Dir.chdir(temp_dir)
      FileUtils.mkdir_p(File.join(layouts_dir, 'Resources'))
      allow(RjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
        'source_path' => temp_dir,
        'layouts_directory' => 'Layouts',
        'data_directory' => 'src/generated/data'
      })
      File.write(File.join(layouts_dir, 'Resources', 'strings.json'), JSON.generate({
        'kebab_widget' => { 'headline' => 'Headline' }
      }))
    end

    after do
      Dir.chdir(@original_dir)
      FileUtils.rm_rf(temp_dir)
    end

    it 'resolves a kebab layout data default against its normalized section' do
      File.write(File.join(layouts_dir, 'kebab-widget.json'), JSON.generate({
        'type' => 'View',
        'child' => [
          { 'data' => [{ 'name' => 'title', 'class' => 'String', 'defaultValue' => 'headline' }] },
          { 'type' => 'Label', 'text' => '@{title}' }
        ]
      }))

      generator = described_class.new
      expect { generator.update_data_models }.not_to output(/Bare key/).to_stdout

      content = File.read(File.join(data_dir, 'KebabWidgetData.ts'))
      expect(content).to include('title: StringManager.currentLanguage.kebabWidgetHeadline,')
    end
  end
end
