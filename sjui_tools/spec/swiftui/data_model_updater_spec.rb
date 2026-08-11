# frozen_string_literal: true

require 'swiftui/data_model_updater'
require 'fileutils'
require 'tmpdir'

RSpec.describe SjuiTools::SwiftUI::DataModelUpdater do
  let(:temp_dir) { Dir.mktmpdir('data_model_updater_test') }
  let(:layouts_dir) { File.join(temp_dir, 'Layouts') }
  let(:data_dir) { File.join(temp_dir, 'Data') }

  before do
    FileUtils.mkdir_p(layouts_dir)
    FileUtils.mkdir_p(data_dir)

    allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
      'layouts_directory' => 'Layouts',
      'data_directory' => 'Data',
      'styles_directory' => 'Styles'
    })
    allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#extract_data_properties' do
    let(:updater) { described_class.new }

    it 'extracts data from JSON' do
      json_data = {
        'child' => [
          {
            'data' => [
              { 'name' => 'title', 'class' => 'String', 'defaultValue' => 'Hello' },
              { 'name' => 'count', 'class' => 'Int', 'defaultValue' => 0 }
            ]
          }
        ]
      }

      result = updater.send(:extract_data_properties, json_data)
      expect(result.length).to eq(2)
      expect(result[0]['name']).to eq('title')
      expect(result[1]['name']).to eq('count')
    end

    it 'handles nested children' do
      json_data = {
        'child' => {
          'data' => [
            { 'name' => 'nested', 'class' => 'String' }
          ]
        }
      }

      result = updater.send(:extract_data_properties, json_data)
      expect(result.length).to eq(1)
      expect(result[0]['name']).to eq('nested')
    end

    it 'handles arrays' do
      json_data = [
        { 'data' => [{ 'name' => 'item1', 'class' => 'String' }] },
        { 'data' => [{ 'name' => 'item2', 'class' => 'Int' }] }
      ]

      result = updater.send(:extract_data_properties, json_data)
      expect(result.length).to eq(2)
    end

    it 'returns empty for non-hash' do
      expect(updater.send(:extract_data_properties, 'string')).to eq([])
    end

    # EditText / Input are aliases for TextField (attribute_definitions
    # `_alias_of: TextField`); TextFieldConverter emits data.<id>IsFocused
    # references for every routed component with an id, so the auto-generated
    # focus property must cover the aliases too or generated code won't compile.
    it 'auto-generates isFocused property for TextField and its aliases' do
      %w[TextField EditText Input TextView].each do |type|
        json_data = { 'type' => type, 'id' => 'email_field' }
        result = updater.send(:extract_data_properties, json_data)
        names = result.map { |p| p['name'] }
        expect(names).to include('emailFieldIsFocused'),
                         "expected #{type} to auto-generate emailFieldIsFocused, got #{names.inspect}"
      end
    end
  end

  describe '#extract_onclick_actions' do
    let(:updater) { described_class.new }

    it 'extracts onclick from JSON' do
      json_data = {
        'onClick' => 'handleTap',
        'child' => [
          { 'onClick' => 'onButtonClick' }
        ]
      }

      result = updater.send(:extract_onclick_actions, json_data)
      expect(result).to include('handleTap')
      expect(result).to include('onButtonClick')
    end

    it 'handles nested children' do
      json_data = {
        'child' => {
          'onClick' => 'nestedClick'
        }
      }

      result = updater.send(:extract_onclick_actions, json_data)
      expect(result).to include('nestedClick')
    end

    it 'handles arrays' do
      json_data = [
        { 'onClick' => 'action1' },
        { 'onClick' => 'action2' }
      ]

      result = updater.send(:extract_onclick_actions, json_data)
      expect(result).to include('action1')
      expect(result).to include('action2')
    end

    it 'returns unique actions' do
      json_data = {
        'onClick' => 'sameAction',
        'child' => [
          { 'onClick' => 'sameAction' }
        ]
      }

      result = updater.send(:extract_onclick_actions, json_data)
      expect(result.count('sameAction')).to eq(1)
    end
  end

  describe '#generate_data_content' do
    let(:updater) { described_class.new }

    context 'with data properties' do
      it 'generates struct with properties' do
        properties = [
          { 'name' => 'title', 'class' => 'String', 'defaultValue' => 'Test' },
          { 'name' => 'count', 'class' => 'Int', 'defaultValue' => 0 }
        ]

        content = updater.send(:generate_data_content, 'MyView', properties, [])

        expect(content).to include('struct MyViewData')
        expect(content).to include('var title: String = "Test"')
        expect(content).to include('var count: Int = 0')
      end

      it 'handles optional properties' do
        properties = [
          { 'name' => 'optional', 'class' => 'String', 'defaultValue' => nil }
        ]

        content = updater.send(:generate_data_content, 'Test', properties, [])

        expect(content).to include('var optional: String? = nil')
      end

      it 'generates update function' do
        properties = [
          { 'name' => 'title', 'class' => 'String', 'defaultValue' => 'Test' }
        ]

        content = updater.send(:generate_data_content, 'Test', properties, [])

        expect(content).to include('mutating func update(dictionary: [String: Any])')
        expect(content).to include('if let stringValue = value as? String')
      end

      it 'coerces a runtime String on a Color field instead of dropping it' do
        # The data contract declares Color fields with token-string defaults
        # ("slate_300"), so a runtime String IS a legal value. `as? Color`
        # alone silently kept the default while the dynamic path rendered the
        # token — downstream hour rows, 2026-08-08.
        properties = [
          { 'name' => 'accent', 'class' => 'Color', 'defaultValue' => 'slate_300' }
        ]

        content = updater.send(:generate_data_content, 'Test', properties, [])

        expect(content).to include('if let typedValue = value as? Color')
        expect(content).to include('let resolved = ColorManager.swiftui.color(for: spelling)')
        expect(content).to include('?? SwiftJsonUIConfiguration.shared.getColor(for: spelling)')
      end

      it 'generates toDictionary function' do
        properties = [
          { 'name' => 'title', 'class' => 'String', 'defaultValue' => 'Test' }
        ]

        content = updater.send(:generate_data_content, 'Test', properties, [])

        # toDictionary() takes no arguments; closures are passed via the stored property directly.
        expect(content).to include('func toDictionary() -> [String: Any]')
        expect(content).to include('dict["title"] = title')
      end
    end

    context 'with onclick actions' do
      it 'includes onclick closures in toDictionary' do
        actions = ['onTap', 'onSubmit']

        content = updater.send(:generate_data_content, 'Test', [], actions)

        # Actions are stored as closures on the model; toDictionary forwards them by name.
        expect(content).to include('dict["onTap"] = onTap')
        expect(content).to include('dict["onSubmit"] = onSubmit')
      end
    end

    context 'with empty properties' do
      it 'generates struct with comment' do
        content = updater.send(:generate_data_content, 'Empty', [], [])

        expect(content).to include('// No data properties defined in JSON')
        expect(content).to include('// No properties to update')
      end
    end

    context 'with different types' do
      it 'handles Int type' do
        properties = [{ 'name' => 'num', 'class' => 'Int', 'defaultValue' => 0 }]
        content = updater.send(:generate_data_content, 'Test', properties, [])

        expect(content).to include('if let intValue = value as? Int')
      end

      it 'handles Double type' do
        properties = [{ 'name' => 'amount', 'class' => 'Double', 'defaultValue' => 0.0 }]
        content = updater.send(:generate_data_content, 'Test', properties, [])

        expect(content).to include('if let doubleValue = value as? Double')
      end

      it 'handles Bool type' do
        properties = [{ 'name' => 'flag', 'class' => 'Bool', 'defaultValue' => false }]
        content = updater.send(:generate_data_content, 'Test', properties, [])

        expect(content).to include('if let boolValue = value as? Bool')
      end

      it 'handles CGFloat type' do
        properties = [{ 'name' => 'size', 'class' => 'CGFloat', 'defaultValue' => 0 }]
        content = updater.send(:generate_data_content, 'Test', properties, [])

        expect(content).to include('if let floatValue = value as? CGFloat')
        expect(content).to include('else if let doubleValue = value as? Double')
      end

      it 'handles custom types' do
        properties = [{ 'name' => 'custom', 'class' => 'CustomType', 'defaultValue' => nil }]
        content = updater.send(:generate_data_content, 'Test', properties, [])

        expect(content).to include('if let typedValue = value as? CustomType')
      end
    end
  end

  describe '#format_default_value' do
    let(:updater) { described_class.new }

    it 'adds quotes for String class' do
      result = updater.send(:format_default_value, 'Hello', 'String')
      expect(result).to eq('"Hello"')
    end

    it 'returns value as-is for other types' do
      expect(updater.send(:format_default_value, 'true', 'Bool')).to eq('true')
      expect(updater.send(:format_default_value, '0', 'Int')).to eq('0')
    end
  end

  describe '#to_pascal_case' do
    let(:updater) { described_class.new }

    it 'converts snake_case' do
      expect(updater.send(:to_pascal_case, 'my_view')).to eq('MyView')
    end

    it 'converts kebab-case' do
      expect(updater.send(:to_pascal_case, 'my-view')).to eq('MyView')
    end

    it 'handles already PascalCase' do
      expect(updater.send(:to_pascal_case, 'MyView')).to eq('MyView')
    end
  end

  describe '#find_existing_data_file' do
    let(:updater) { described_class.new }

    it 'returns exact match' do
      path = File.join(data_dir, 'TestData.swift')
      File.write(path, 'struct TestData {}')

      result = updater.send(:find_existing_data_file, 'Test')
      expect(result).to eq(path)
    end

    it 'returns case-insensitive match' do
      path = File.join(data_dir, 'MyviewData.swift')
      File.write(path, 'struct MyviewData {}')

      result = updater.send(:find_existing_data_file, 'Myview')
      expect(result).to eq(path)
    end

    it 'returns nil when not found' do
      result = updater.send(:find_existing_data_file, 'NotFound')
      expect(result).to be_nil
    end
  end

  describe '#extract_type_name' do
    let(:updater) { described_class.new }

    # W3-2: extract_struct_name(path) became the shared core's
    # extract_type_name(content) hook — same regex, content-in instead
    # of path-in (the core reads the file once in update_data_file).
    it 'extracts struct name from content' do
      result = updater.send(:extract_type_name, "struct MyCustomData {\n  // content\n}")
      expect(result).to eq('MyCustomData')
    end

    it 'returns nil if no struct found' do
      result = updater.send(:extract_type_name, '// empty file')
      expect(result).to be_nil
    end
  end

  describe '#update_data_file' do
    let(:updater) { described_class.new }

    it 'creates new data file when not exists' do
      properties = [{ 'name' => 'title', 'class' => 'String', 'defaultValue' => 'Test' }]

      expect {
        updater.send(:update_data_file, 'new_view', properties, [])
      }.to output(/Updated Data model/).to_stdout

      expect(File.exist?(File.join(data_dir, 'NewViewData.swift'))).to be true
    end

    it 'updates existing data file' do
      # Create existing file
      existing_path = File.join(data_dir, 'ExistingData.swift')
      File.write(existing_path, "struct ExistingData {\n  var old: String = \"\"\n}")

      properties = [{ 'name' => 'new', 'class' => 'String', 'defaultValue' => 'Value' }]

      expect {
        updater.send(:update_data_file, 'existing', properties, [])
      }.to output(/Updated Data model/).to_stdout

      content = File.read(existing_path)
      expect(content).to include('var new: String = "Value"')
    end

    it 'preserves existing struct name casing' do
      # Create existing file with specific casing
      existing_path = File.join(data_dir, 'MyCustomViewData.swift')
      File.write(existing_path, "struct MyCustomViewData {\n}")

      properties = [{ 'name' => 'title', 'class' => 'String', 'defaultValue' => 'Test' }]

      updater.send(:update_data_file, 'my_custom_view', properties, [])

      content = File.read(existing_path)
      expect(content).to include('struct MyCustomViewData')
    end
  end

  # The data-default face resolves strings under the layout's OWN sections
  # (process_json_file announces the layout, the same per-file channel the
  # view converter uses) and never warns: a defaultValue can be sentinel
  # vocabulary (a DateSelectBox's "today") whose collision with some
  # section's key must not gate the build. Before the announcement, every
  # data-default lookup ran with no namespace context — an own-section key
  # emitted the bare `.localized()` (raw key as the default) and was
  # misreported as foreign with an empty own list (2026-08-11 filing).
  describe 'data-default string resolution context' do
    let(:updater) { described_class.new }

    before do
      resources_dir = File.join(layouts_dir, 'Resources')
      FileUtils.mkdir_p(resources_dir)
      File.write(File.join(resources_dir, 'strings.json'), JSON.generate({
        'note_input' => { 'register' => 'Register' },
        'venue_detail' => { 'today' => { 'en' => 'Today', 'ja' => '本日' } }
      }))
      File.write(File.join(layouts_dir, 'note_input.json'), JSON.generate({
        'type' => 'View',
        'data' => [
          { 'name' => 'registerButtonLabel', 'class' => 'String', 'defaultValue' => 'register' },
          { 'name' => 'selectedDateValue', 'class' => 'String', 'defaultValue' => 'today' }
        ]
      }))
      allow(SjuiTools::Core::Logger).to receive(:warn)
    end

    after { SjuiTools::SwiftUI::Helpers::StringManagerHelper.current_namespaces = [] }

    it 'resolves an own-section key, keeps a foreign-colliding sentinel literal, and stays silent' do
      expect {
        updater.send(:process_json_file, File.join(layouts_dir, 'note_input.json'))
      }.to output(/Updated Data model/).to_stdout

      content = File.read(File.join(data_dir, 'NoteInputData.swift'))
      expect(content).to include('var registerButtonLabel: String = StringManager.NoteInput.register()')
      expect(content).to include('var selectedDateValue: String = "today".localized()')
      expect(SjuiTools::Core::Logger).not_to have_received(:warn)
    end
  end

  describe '#update_data_models' do
    let(:updater) { described_class.new }

    before do
      # Create a sample JSON file
      File.write(
        File.join(layouts_dir, 'home.json'),
        JSON.generate({
          'type' => 'View',
          'data' => [{ 'name' => 'userName', 'class' => 'String', 'defaultValue' => 'Guest' }],
          'child' => [{ 'type' => 'Label', 'onClick' => 'onTap' }]
        })
      )
    end

    it 'processes JSON files in Layouts directory' do
      expect { updater.update_data_models }.to output(/Updated Data model/).to_stdout

      expect(File.exist?(File.join(data_dir, 'HomeData.swift'))).to be true
    end

    it 'skips Resources directory' do
      resources_dir = File.join(layouts_dir, 'Resources')
      FileUtils.mkdir_p(resources_dir)
      File.write(
        File.join(resources_dir, 'strings.json'),
        '{}'
      )

      expect { updater.update_data_models }.not_to output(/strings.json/).to_stdout
    end
  end

  describe '#process_json_file' do
    let(:updater) { described_class.new }

    it 'processes JSON file and creates data file' do
      json_path = File.join(layouts_dir, 'dashboard.json')
      File.write(json_path, JSON.generate({
        'type' => 'View',
        'data' => [{ 'name' => 'count', 'class' => 'Int', 'defaultValue' => 0 }]
      }))

      expect { updater.send(:process_json_file, json_path) }.to output(/Updated Data model/).to_stdout
    end

    it 'handles invalid JSON gracefully' do
      json_path = File.join(layouts_dir, 'invalid.json')
      File.write(json_path, 'invalid json content')

      expect { updater.send(:process_json_file, json_path) }.to raise_error(JSON::ParserError)
    end
  end

  describe 'format_default_value edge cases' do
    let(:updater) { described_class.new }

    it 'handles empty string' do
      result = updater.send(:format_default_value, '', 'String')
      expect(result).to eq('""')
    end

    it 'handles strings with content' do
      # Non-empty string defaults are routed through StringManager for localization.
      result = updater.send(:format_default_value, 'hello', 'String')
      expect(result).to include('"hello"')
    end

    it 'handles true value' do
      # format_default_value returns the value as-is for non-String types
      result = updater.send(:format_default_value, true, 'Bool')
      expect(result).to eq(true)
    end

    it 'handles false value' do
      # format_default_value returns the value as-is for non-String types
      result = updater.send(:format_default_value, false, 'Bool')
      expect(result).to eq(false)
    end
  end

  describe '#extract_event_bindings' do
    let(:updater) { described_class.new }

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

    it 'extracts event bindings from onToggle alias on Switch (normalized to onValueChange)' do
      json_data = {
        'type' => 'Switch',
        'onToggle' => '@{onAiSearchToggle}'
      }

      result = updater.send(:extract_event_bindings, json_data)
      expect(result['onAiSearchToggle']).to eq({ component: 'Switch', attribute: 'onValueChange' })
    end

    it 'extracts event bindings from onToggle alias on Toggle (normalized to onValueChange)' do
      json_data = {
        'type' => 'Toggle',
        'onToggle' => '@{onAiSearchToggle}'
      }

      result = updater.send(:extract_event_bindings, json_data)
      expect(result['onAiSearchToggle']).to eq({ component: 'Toggle', attribute: 'onValueChange' })
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
    let(:updater) { described_class.new }

    before do
      SjuiTools::Core::TypeConverter.clear_type_mapping_cache
    end

    it 'converts Event type to tuple type based on event binding' do
      json_data = {
        'type' => 'View',
        'data' => [
          { 'name' => 'onToggle', 'class' => '((Event) -> Void)?' }
        ],
        'child' => {
          'type' => 'Switch',
          'onValueChange' => '@{onToggle}'
        }
      }

      event_bindings = updater.send(:extract_event_bindings, json_data)
      result = updater.send(:extract_data_properties, json_data, [], event_bindings)

      expect(result.length).to eq(1)
      # Event should be converted to (String, Bool) for Switch.onValueChange in SwiftUI
      expect(result[0]['class']).to eq('((String, Bool) -> Void)?')
    end

    it 'converts Event type for Button onClick' do
      json_data = {
        'type' => 'View',
        'data' => [
          { 'name' => 'handleTap', 'class' => '((Event) -> Void)?' }
        ],
        'child' => {
          'type' => 'Button',
          'onClick' => '@{handleTap}'
        }
      }

      event_bindings = updater.send(:extract_event_bindings, json_data)
      result = updater.send(:extract_data_properties, json_data, [], event_bindings)

      expect(result.length).to eq(1)
      # Event should be converted to (String, Void) for Button.onClick in SwiftUI
      expect(result[0]['class']).to eq('((String, Void) -> Void)?')
    end

    it 'converts Event type for TextField onTextChange' do
      json_data = {
        'type' => 'View',
        'data' => [
          { 'name' => 'onTextUpdate', 'class' => '((Event) -> Void)?' }
        ],
        'child' => {
          'type' => 'TextField',
          'onTextChange' => '@{onTextUpdate}'
        }
      }

      event_bindings = updater.send(:extract_event_bindings, json_data)
      result = updater.send(:extract_data_properties, json_data, [], event_bindings)

      expect(result.length).to eq(1)
      # Event should be converted to (String, String) for TextField.onTextChange in SwiftUI
      expect(result[0]['class']).to eq('((String, String) -> Void)?')
    end

    it 'leaves non-Event types unchanged' do
      json_data = {
        'type' => 'View',
        'data' => [
          { 'name' => 'onToggle', 'class' => '((Bool) -> Void)?' }
        ],
        'child' => {
          'type' => 'Switch',
          'onValueChange' => '@{onToggle}'
        }
      }

      event_bindings = updater.send(:extract_event_bindings, json_data)
      result = updater.send(:extract_data_properties, json_data, [], event_bindings)

      expect(result.length).to eq(1)
      # Non-Event type should remain unchanged
      expect(result[0]['class']).to eq('((Bool) -> Void)?')
    end

    it 'handles unbound Event type (no conversion)' do
      json_data = {
        'type' => 'View',
        'data' => [
          { 'name' => 'unboundHandler', 'class' => '((Event) -> Void)?' }
        ]
      }

      event_bindings = updater.send(:extract_event_bindings, json_data)
      result = updater.send(:extract_data_properties, json_data, [], event_bindings)

      expect(result.length).to eq(1)
      # Unbound Event type should remain unchanged
      expect(result[0]['class']).to eq('((Event) -> Void)?')
    end
  end

  describe '#ensure_unique_layout_basenames! (parity with rjui-cell-data-model-name-collision-across-screens)' do
    let(:updater) { described_class.new }

    it 'aborts when two layouts share a basename across subdirectories' do
      files = ['/x/Layouts/dashboard/breakdown_row.json', '/x/Layouts/sales/breakdown_row.json']
      expect { updater.send(:ensure_unique_layout_basenames!, files) }
        .to raise_error(SystemExit)
        .and output(/duplicate layout file name.*breakdown_row\.json/m).to_stderr
    end

    it 'stays silent for unique basenames' do
      files = ['/x/Layouts/dashboard/breakdown_row.json', '/x/Layouts/sales/sales_breakdown_row.json']
      expect { updater.send(:ensure_unique_layout_basenames!, files) }.not_to raise_error
    end
  end
end
