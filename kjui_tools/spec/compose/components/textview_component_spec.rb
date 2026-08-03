# frozen_string_literal: true

require 'compose/components/textview_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'

RSpec.describe KjuiTools::Compose::Components::TextViewComponent do
  let(:required_imports) { Set.new }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
    # Clear data definitions before each test
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  describe '.generate' do
    it 'generates basic CustomTextField component' do
      json_data = { 'type' => 'TextView' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('CustomTextField(')
      expect(required_imports).to include(:custom_textfield)
    end

    # flexible: the declared height is the growth FLOOR (heightIn(min)),
    # never a fixed .height() — with a numeric width, build_size used to
    # leak `.height(N)` ahead of the bound and pin the box (parity family
    # TextView/flexible__true d=9).
    it 'emits only heightIn(min) for a flexible editor with numeric width and height' do
      json_data = { 'type' => 'TextView', 'width' => 200, 'height' => 100, 'flexible' => true }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.heightIn(min = 100.dp)')
      expect(result).not_to include('.height(100.dp)')
    end

    it 'generates TextField with text value' do
      json_data = { 'type' => 'TextView', 'text' => 'Hello World' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('initialText = "Hello World"')
    end

    it 'generates TextField with data binding' do
      json_data = { 'type' => 'TextView', 'text' => '@{comment}' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('initialText = data.comment')
      expect(result).to include('viewModel.updateData(mapOf("comment" to newValue))')
    end

    it 'generates TextField with data binding with null coalescing' do
      json_data = { 'type' => 'TextView', 'text' => '@{comment ?? }' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('initialText = data.comment')
    end

    it 'generates TextField with onTextChange handler' do
      json_data = { 'type' => 'TextView', 'onTextChange' => 'handleTextChange' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('data.handleTextChange?.invoke()')
    end

    it 'generates TextField with empty initial state when no handler' do
      json_data = { 'type' => 'TextView' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('initialText = ""')
    end

    it 'generates TextField with placeholder' do
      json_data = { 'type' => 'TextView', 'placeholder' => 'Enter text here' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('placeholder = { Text("Enter text here") }')
    end

    it 'generates TextField with hint as placeholder' do
      json_data = { 'type' => 'TextView', 'hint' => 'Type something' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('placeholder = { Text("Type something") }')
    end

    it 'generates TextField with cornerRadius' do
      json_data = { 'type' => 'TextView', 'cornerRadius' => 12 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('shape = RoundedCornerShape(12.dp)')
      expect(required_imports).to include(:shape)
    end

    it 'generates TextField with background color' do
      json_data = { 'type' => 'TextView', 'background' => '#FFFFFF' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('backgroundColor =')
    end

    it 'generates TextField with highlightBackground' do
      json_data = { 'type' => 'TextView', 'highlightBackground' => '#007AFF' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('highlightBackgroundColor =')
    end

    it 'generates TextField with borderColor' do
      json_data = { 'type' => 'TextView', 'borderColor' => '#CCCCCC' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('borderColor =')
    end

    it 'sets isOutlined to true' do
      json_data = { 'type' => 'TextView' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('isOutlined = true')
    end

    it 'generates TextField with maxLines' do
      json_data = { 'type' => 'TextView', 'maxLines' => 5 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('maxLines = 5')
    end

    it 'generates TextField with default maxLines as Int.MAX_VALUE' do
      json_data = { 'type' => 'TextView' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('maxLines = Int.MAX_VALUE')
    end

    it 'sets singleLine to false for multi-line' do
      json_data = { 'type' => 'TextView' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('singleLine = false')
    end

    it 'generates TextField with fontSize routed through FontSpec resolve' do
      json_data = { 'type' => 'TextView', 'fontSize' => 16 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Configuration.Font.resolve(FontSpec(')
      expect(result).to include('size = 16.sp')
      expect(result).to match(/textStyle = TextStyle\(.*fontSize = \(resolved_textview\d+\.size \?: TextUnit\.Unspecified\)/)
      expect(required_imports).to include(:text_style)
    end

    it 'generates TextField with fontColor' do
      json_data = { 'type' => 'TextView', 'fontColor' => '#333333' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('textStyle = TextStyle(')
      expect(result).to include('color =')
    end

    it 'generates TextField with both fontSize and fontColor' do
      json_data = { 'type' => 'TextView', 'fontSize' => 14, 'fontColor' => '#000000' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('textStyle = TextStyle(')
      expect(result).to include('size = 14.sp')
      expect(result).to match(/fontSize = \(resolved_textview\d+\.size \?: TextUnit\.Unspecified\)/)
      expect(result).to include('color =')
    end

    it 'generates TextField with returnKeyType Done' do
      json_data = { 'type' => 'TextView', 'returnKeyType' => 'Done' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done)')
      expect(required_imports).to include(:ime_action)
    end

    it 'generates TextField with returnKeyType Next' do
      json_data = { 'type' => 'TextView', 'returnKeyType' => 'Next' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('ImeAction.Next')
    end

    it 'generates TextField with returnKeyType Default' do
      json_data = { 'type' => 'TextView', 'returnKeyType' => 'Default' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('ImeAction.Default')
    end

    it 'generates TextField with unknown returnKeyType as Default' do
      json_data = { 'type' => 'TextView', 'returnKeyType' => 'Unknown' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('ImeAction.Default')
    end

    it 'generates TextField with enabled true' do
      json_data = { 'type' => 'TextView', 'enabled' => true }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('enabled = true')
    end

    it 'generates TextField with enabled false' do
      json_data = { 'type' => 'TextView', 'enabled' => false }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('enabled = false')
    end

    it 'generates TextField with enabled data binding' do
      json_data = { 'type' => 'TextView', 'enabled' => '@{isEditable}' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('enabled = data.isEditable')
    end

    context 'with margins' do
      it 'generates CustomTextFieldWithMargins when margins present' do
        json_data = { 'type' => 'TextView', 'margins' => [10, 20, 30, 40] }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('CustomTextFieldWithMargins(')
        expect(required_imports).to include(:box)
      end

      it 'generates with boxModifier for margins' do
        json_data = { 'type' => 'TextView', 'margins' => [10, 20, 30, 40] }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('boxModifier = Modifier')
      end

      it 'generates with textFieldModifier' do
        json_data = { 'type' => 'TextView', 'margins' => [10] }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('textFieldModifier = Modifier')
      end

      it 'handles topMargin' do
        json_data = { 'type' => 'TextView', 'topMargin' => 20 }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('CustomTextFieldWithMargins(')
      end

      it 'handles bottomMargin' do
        json_data = { 'type' => 'TextView', 'bottomMargin' => 20 }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('CustomTextFieldWithMargins(')
      end

      it 'handles leftMargin' do
        json_data = { 'type' => 'TextView', 'leftMargin' => 20 }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('CustomTextFieldWithMargins(')
      end

      it 'handles rightMargin' do
        json_data = { 'type' => 'TextView', 'rightMargin' => 20 }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('CustomTextFieldWithMargins(')
      end
    end

    context 'with width' do
      it 'uses fillMaxWidth by default' do
        json_data = { 'type' => 'TextView' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.fillMaxWidth()')
      end

      it 'uses fillMaxWidth for matchParent' do
        json_data = { 'type' => 'TextView', 'width' => 'matchParent' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.fillMaxWidth()')
      end

      it 'uses specific width when provided' do
        json_data = { 'type' => 'TextView', 'width' => 200 }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.width(200.dp)')
      end
    end

    context 'with height' do
      it 'uses default height of 120dp' do
        json_data = { 'type' => 'TextView' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.height(120.dp)')
      end

      it 'uses fillMaxHeight for matchParent' do
        json_data = { 'type' => 'TextView', 'height' => 'matchParent' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.fillMaxHeight()')
      end

      it 'uses wrapContentHeight for wrapContent' do
        json_data = { 'type' => 'TextView', 'height' => 'wrapContent' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.wrapContentHeight()')
      end

      it 'uses specific height when provided' do
        json_data = { 'type' => 'TextView', 'height' => 200 }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.height(200.dp)')
      end
    end

    context 'with margins and height options' do
      it 'handles matchParent height with margins' do
        json_data = { 'type' => 'TextView', 'margins' => [10], 'height' => 'matchParent' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.fillMaxHeight()')
      end

      it 'handles wrapContent height with margins' do
        json_data = { 'type' => 'TextView', 'margins' => [10], 'height' => 'wrapContent' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.wrapContentHeight()')
      end

      it 'handles specific height with margins' do
        json_data = { 'type' => 'TextView', 'margins' => [10], 'height' => 150 }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.height(150.dp)')
      end

      it 'handles specific width with margins' do
        json_data = { 'type' => 'TextView', 'margins' => [10], 'width' => 300 }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('textFieldModifier')
      end
    end
  end

  describe '.process_data_binding' do
    it 'quotes non-binding text' do
      result = described_class.send(:process_data_binding, 'Hello')
      expect(result).to eq('"Hello"')
    end

    it 'converts binding to data accessor' do
      result = described_class.send(:process_data_binding, '@{myValue}')
      expect(result).to eq('data.myValue')
    end

    it 'handles binding with null coalescing' do
      result = described_class.send(:process_data_binding, '@{value ?? default}')
      expect(result).to eq('data.value')
    end

    it 'handles empty string' do
      result = described_class.send(:process_data_binding, '')
      expect(result).to eq('""')
    end
  end

  describe '.extract_variable_name' do
    it 'extracts variable from binding' do
      result = described_class.send(:extract_variable_name, '@{user.name}')
      expect(result).to eq('name')
    end

    it 'returns value for non-binding text' do
      result = described_class.send(:extract_variable_name, 'plain text')
      expect(result).to eq('value')
    end

    it 'returns value for nil' do
      result = described_class.send(:extract_variable_name, nil)
      expect(result).to eq('value')
    end
  end

  describe '.quote' do
    it 'escapes quotes' do
      result = described_class.send(:quote, 'Hello "World"')
      expect(result).to eq('"Hello \\"World\\""')
    end

    it 'escapes newlines' do
      result = described_class.send(:quote, "Hello\nWorld")
      expect(result).to eq('"Hello\\nWorld"')
    end

    it 'escapes carriage returns' do
      result = described_class.send(:quote, "Hello\rWorld")
      expect(result).to eq('"Hello\\rWorld"')
    end

    it 'escapes tabs' do
      result = described_class.send(:quote, "Hello\tWorld")
      expect(result).to eq('"Hello\\tWorld"')
    end

    it 'escapes backslashes' do
      result = described_class.send(:quote, 'Hello\\World')
      expect(result).to eq('"Hello\\\\World"')
    end
  end

  describe '.indent' do
    it 'returns text unchanged for level 0' do
      result = described_class.send(:indent, 'text', 0)
      expect(result).to eq('text')
    end

    it 'adds indentation for level 1' do
      result = described_class.send(:indent, 'text', 1)
      expect(result).to eq('    text')
    end

    it 'adds indentation for level 2' do
      result = described_class.send(:indent, 'text', 2)
      expect(result).to eq('        text')
    end

    it 'handles multi-line text' do
      result = described_class.send(:indent, "line1\nline2", 1)
      expect(result).to eq("    line1\n    line2")
    end

    it 'preserves empty lines' do
      result = described_class.send(:indent, "line1\n\nline2", 1)
      expect(result).to eq("    line1\n\n    line2")
    end
  end

  describe 'event handler invocation' do
    it 'generates invoke() without arguments when handler type is () -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onTextChange' => { 'name' => 'onTextChange', 'class' => '(() -> Unit)?' }
      }

      json_data = {
        'type' => 'TextView',
        'id' => 'commentField',
        'text' => '@{comment}',
        'onTextChange' => '@{onTextChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onTextChange?.invoke()')
      expect(result).not_to include('invoke("commentField"')
    end

    it 'generates invoke(viewId, value) when handler type is (Event) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onTextChange' => { 'name' => 'onTextChange', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'TextView',
        'id' => 'commentField',
        'text' => '@{comment}',
        'onTextChange' => '@{onTextChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onTextChange?.invoke("commentField", newValue)')
    end

    it 'generates invoke(viewId, value) when handler type is (String, String) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onTextChange' => { 'name' => 'onTextChange', 'class' => '((String, String) -> Unit)?' }
      }

      json_data = {
        'type' => 'TextView',
        'id' => 'noteField',
        'onTextChange' => '@{onTextChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onTextChange?.invoke("noteField", newValue)')
    end

    it 'includes both data binding and handler invocation when both exist' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onTextChange' => { 'name' => 'onTextChange', 'class' => '((String, String) -> Unit)?' }
      }

      json_data = {
        'type' => 'TextView',
        'id' => 'commentField',
        'text' => '@{comment}',
        'onTextChange' => '@{onTextChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('viewModel.updateData(mapOf("comment" to newValue))')
      expect(result).to include('data.onTextChange?.invoke("commentField", newValue)')
    end

    it 'uses default textview id when no id specified' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onTextChange' => { 'name' => 'onTextChange', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'TextView',
        'onTextChange' => '@{onTextChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onTextChange?.invoke("textview", newValue)')
    end
  end
  # Focus-state binding — same contract as TextFieldComponent
  # (kjui-textfield-isfocused-focus-binding-not-generated, extended to TextView).
  describe 'focus-state binding (data.<id>IsFocused)' do
    it 'emits FocusRequester + LaunchedEffect + onFocusChanged for an id-bearing TextView' do
      json_data = { 'type' => 'TextView', 'id' => 'note_input' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('val focusRequester_note_input = remember { FocusRequester() }')
      expect(result).to include('LaunchedEffect(data.noteInputIsFocused) { if (data.noteInputIsFocused) { focusRequester_note_input.requestFocus(); keyboardController_note_input?.show() } }')
      expect(result).to include('.focusRequester(focusRequester_note_input)')
      expect(result).to include('.onFocusChanged { if (it.isFocused != data.noteInputIsFocused) viewModel.updateData(mapOf("noteInputIsFocused" to it.isFocused)) }')
      expect(required_imports).to include(:focus_requester)
      expect(required_imports).to include(:focus_changed)
      expect(required_imports).to include(:software_keyboard_controller)
    end

    it 'wires the focus binding on the margins (Box-wrapped) variant too' do
      json_data = { 'type' => 'TextView', 'id' => 'memo_area', 'topMargin' => 8 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('CustomTextFieldWithMargins(')
      expect(result).to include('.focusRequester(focusRequester_memo_area)')
      expect(result).to include('.onFocusChanged { if (it.isFocused != data.memoAreaIsFocused)')
    end

    it 'emits no focus binding for an id-less TextView' do
      json_data = { 'type' => 'TextView' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).not_to include('IsFocused')
      expect(result).not_to include('FocusRequester()')
    end
  end
end

# `hintAttributes` is the object form of the flat `hint*` keys, and the object
# wins per key — the precedence the SwiftUI converter uses. Only lineHeight was
# honoured here before, so a hint colour or size was silently dropped.
RSpec.describe KjuiTools::Compose::Components::TextViewComponent, 'hintAttributes' do
  let(:required_imports) { Set.new }

  # See the note in text_component_spec: data_definitions is a leaked global.
  before { KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {} }

  def field(extra)
    described_class.generate(
      { 'type' => 'TextView', 'id' => 'note', 'text' => '@{note}', 'hint' => 'Write here' }.merge(extra),
      0, required_imports
    )
  end

  it 'styles the placeholder from the object form' do
    result = field('hintAttributes' => { 'fontColor' => '#999999', 'fontSize' => 14, 'font' => 'bold' })
    expect(result).to match(/color = Color\(.*999999/)
    expect(result).to include('fontSize = 14.sp')
    expect(result).to include('fontWeight = FontWeight.Bold')
  end

  it 'still honours the flat keys' do
    result = field('hintColor' => '#999999', 'hintFontSize' => 14)
    expect(result).to match(/color = Color\(.*999999/)
    expect(result).to include('fontSize = 14.sp')
  end

  it 'lets the object win per key' do
    result = field('hintColor' => '#111111', 'hintAttributes' => { 'fontColor' => '#999999' })
    expect(result).to match(/color = Color\(.*999999/)
    expect(result).not_to include('111111')
  end

  # Compose has no multiplier, so it resolves against the hint's own size.
  it 'resolves lineHeightMultiple against the hint size' do
    expect(field('hintAttributes' => { 'fontSize' => 14, 'lineHeightMultiple' => 1.4 }))
      .to include('lineHeight = 19.6.sp')
  end

  # 19.599999999999998.sp is float noise, not a measurement.
  it 'rounds the resolved line height' do
    expect(field('hintFontSize' => 14, 'hintLineHeightMultiple' => 1.4)).not_to include('19.5999')
  end

  it 'keeps the one-liner when nothing styles the hint' do
    expect(field({})).to include('placeholder = { Text("Write here") },')
  end

  # Regression: sjui-kjui-textview-enabled-binding-gaps-after-common-enabled-fix
  # (follow-through) — the tail chunks prefixed ",\n" while the args before
  # them carried their own trailing comma, so any shape without fontColor
  # (no textStyle to absorb the comma) plus enabled/keyboardType emitted
  # `singleLine = false,,` — broken Kotlin.
  describe 'argument separators' do
    it 'emits the enabled param without doubling the comma when textStyle is absent' do
      result = field('enabled' => '@{isInputEnabled}')
      expect(result).to include('enabled = data.isInputEnabled')
      expect(result).not_to include(',,')
    end

    it 'emits keyboardOptions without doubling the comma when textStyle is absent' do
      result = field('keyboardType' => 'email')
      expect(result).to include('keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email)')
      expect(result).not_to include(',,')
    end

    it 'keeps valid separators when fontColor routes through textStyle' do
      result = field('fontColor' => '#FFFFFF', 'enabled' => '@{isInputEnabled}')
      expect(result).to include('enabled = data.isInputEnabled')
      expect(result).not_to include(',,')
    end
  end
end
