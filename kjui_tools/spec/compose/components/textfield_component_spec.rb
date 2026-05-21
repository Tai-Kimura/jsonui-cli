# frozen_string_literal: true

require 'compose/components/textfield_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'

RSpec.describe KjuiTools::Compose::Components::TextFieldComponent do
  let(:required_imports) { Set.new }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
    # Clear data definitions before each test
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  describe '.generate' do
    it 'generates CustomTextField component' do
      json_data = { 'type' => 'TextField' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('CustomTextField(')
      expect(required_imports).to include(:custom_textfield)
    end

    it 'generates TextField with placeholder' do
      json_data = { 'type' => 'TextField', 'placeholder' => 'Enter text' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('placeholder')
      expect(result).to include('Enter text')
    end

    it 'generates TextField with hint (same as placeholder)' do
      json_data = { 'type' => 'TextField', 'hint' => 'Search...' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('placeholder')
      expect(result).to include('Search...')
    end

    it 'generates TextField with data binding' do
      json_data = { 'type' => 'TextField', 'text' => '@{searchQuery}' }
      result = described_class.generate(json_data, 0, required_imports)
      # Value should be direct data reference (not string interpolation)
      expect(result).to include('initialText = data.searchQuery')
    end

    it 'generates TextField with nested data binding' do
      json_data = { 'type' => 'TextField', 'text' => '@{user.email}' }
      result = described_class.generate(json_data, 0, required_imports)
      # Should use direct data reference for nested properties
      expect(result).to include('initialText = data.user.email')
    end

    it 'generates TextField with data binding and default value' do
      json_data = { 'type' => 'TextField', 'text' => '@{email ?? ""}' }
      result = described_class.generate(json_data, 0, required_imports)
      # Should extract the variable name before ??
      expect(result).to include('initialText = data.email')
    end

    it 'generates secure TextField with isSecure flag' do
      json_data = { 'type' => 'TextField', 'secure' => true }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('isSecure = true')
      expect(required_imports).to include(:secure_text_field)
    end

    it 'generates TextField with cornerRadius' do
      json_data = { 'type' => 'TextField', 'cornerRadius' => 8 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('RoundedCornerShape(8.dp)')
      expect(required_imports).to include(:shape)
    end

    it 'generates TextField with background color' do
      json_data = { 'type' => 'TextField', 'background' => '#FFFFFF' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('backgroundColor')
    end

    it 'generates TextField with highlightBackground' do
      json_data = { 'type' => 'TextField', 'highlightBackground' => '#E0E0E0' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('highlightBackgroundColor')
    end

    it 'generates TextField with borderColor' do
      json_data = { 'type' => 'TextField', 'borderColor' => '#000000' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('borderColor')
      expect(result).to include('isOutlined = true')
    end

    it 'generates outlined TextField' do
      json_data = { 'type' => 'TextField', 'outlined' => true }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('isOutlined = true')
    end

    it 'generates TextField with fontSize routed through FontSpec resolve' do
      json_data = { 'type' => 'TextField', 'fontSize' => 16 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Configuration.Font.resolve(FontSpec(')
      expect(result).to include('size = 16.sp')
      expect(result).to match(/fontSize = \(resolved_textfield\d+\.size \?: TextUnit\.Unspecified\)/)
    end

    it 'generates TextField with fontColor' do
      json_data = { 'type' => 'TextField', 'fontColor' => '#333333' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('textStyle = TextStyle')
      expect(result).to include('color')
    end

    it 'generates TextField with textAlign center' do
      json_data = { 'type' => 'TextField', 'textAlign' => 'center' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('TextAlign.Center')
      expect(required_imports).to include(:text_align)
    end

    it 'generates TextField with textAlign right' do
      json_data = { 'type' => 'TextField', 'textAlign' => 'right' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('TextAlign.End')
    end

    it 'generates TextField with textAlign left' do
      json_data = { 'type' => 'TextField', 'textAlign' => 'left' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('TextAlign.Start')
    end

    it 'generates TextField with onFocus handler' do
      json_data = { 'type' => 'TextField', 'onFocus' => 'handleFocus' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('onFocus = { data.handleFocus?.invoke() }')
    end

    it 'generates TextField with onBlur handler' do
      json_data = { 'type' => 'TextField', 'onBlur' => 'handleBlur' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('onBlur = { data.handleBlur?.invoke() }')
    end

    it 'generates TextField with onBeginEditing handler' do
      json_data = { 'type' => 'TextField', 'onBeginEditing' => 'startEdit' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('onBeginEditing = { data.startEdit?.invoke() }')
    end

    it 'generates TextField with onEndEditing handler' do
      json_data = { 'type' => 'TextField', 'onEndEditing' => 'endEdit' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('onEndEditing = { data.endEdit?.invoke() }')
    end

    it 'generates TextField with email keyboard type' do
      json_data = { 'type' => 'TextField', 'input' => 'email' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('KeyboardType.Email')
      expect(required_imports).to include(:keyboard_type)
    end

    it 'generates TextField with password keyboard type' do
      json_data = { 'type' => 'TextField', 'input' => 'password' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('KeyboardType.Password')
    end

    it 'generates TextField with number keyboard type' do
      json_data = { 'type' => 'TextField', 'input' => 'number' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('KeyboardType.Number')
    end

    it 'generates TextField with decimal keyboard type' do
      json_data = { 'type' => 'TextField', 'input' => 'decimal' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('KeyboardType.Decimal')
    end

    it 'generates TextField with phone keyboard type' do
      json_data = { 'type' => 'TextField', 'input' => 'phone' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('KeyboardType.Phone')
    end

    it 'generates TextField with text keyboard type as default' do
      json_data = { 'type' => 'TextField', 'input' => 'text' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('KeyboardType.Text')
    end

    it 'generates TextField with Done return key' do
      json_data = { 'type' => 'TextField', 'returnKeyType' => 'Done' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('ImeAction.Done')
      expect(required_imports).to include(:ime_action)
    end

    it 'generates TextField with Next return key' do
      json_data = { 'type' => 'TextField', 'returnKeyType' => 'Next' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('ImeAction.Next')
    end

    it 'generates TextField with Search return key' do
      json_data = { 'type' => 'TextField', 'returnKeyType' => 'Search' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('ImeAction.Search')
    end

    it 'generates TextField with Send return key' do
      json_data = { 'type' => 'TextField', 'returnKeyType' => 'Send' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('ImeAction.Send')
    end

    it 'generates TextField with Go return key' do
      json_data = { 'type' => 'TextField', 'returnKeyType' => 'Go' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('ImeAction.Go')
    end

    it 'generates TextField with Default return key' do
      json_data = { 'type' => 'TextField', 'returnKeyType' => 'Default' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('ImeAction.Default')
    end

    it 'generates TextField with onTextChange handler' do
      json_data = { 'type' => 'TextField', 'onTextChange' => 'handleTextChange' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('data.handleTextChange?.invoke()')
    end

    it 'strips @{} binding syntax from onTextChange' do
      json_data = { 'type' => 'TextField', 'onTextChange' => '@{onEmailChange}' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('data.onEmailChange?.invoke()')
      expect(result).not_to include('@{')
    end

    it 'generates TextField with margins using CustomTextFieldWithMargins' do
      json_data = { 'type' => 'TextField', 'margins' => [10, 10, 10, 10] }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('CustomTextFieldWithMargins(')
      expect(result).to include('boxModifier')
      expect(required_imports).to include(:box)
    end

    it 'generates TextField with topMargin' do
      json_data = { 'type' => 'TextField', 'topMargin' => 16 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('CustomTextFieldWithMargins(')
    end

    it 'generates TextField with width and height' do
      json_data = { 'type' => 'TextField', 'width' => 200, 'height' => 50 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.width(200.dp)')
      expect(result).to include('.height(50.dp)')
    end

    it 'generates TextField with styled placeholder' do
      json_data = {
        'type' => 'TextField',
        'placeholder' => 'Hint text',
        'hintColor' => '#999999',
        'hintFontSize' => 14,
        'hintFont' => 'bold'
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('placeholder = { Text(')
      expect(result).to include('14.sp')
      expect(result).to include('FontWeight.Bold')
    end

    # Regression: kjui-textfield-onsubmit-helper-arity-mismatch.
    # `get_event_handler_invocation` requires 3 positional args
    # (handler, view_id, value_expr). The onSubmit binding-form caller
    # was passing only 2, raising `ArgumentError: wrong number of
    # arguments (given 2, expected 3)` mid-build and halting Compose
    # generation for any layout that wires `onSubmit` to a @{handler}.
    # Pass `nil` for value_expr — onSubmit carries no value to forward.
    it 'generates TextField with onSubmit binding (no ArgumentError)' do
      json_data = {
        'type' => 'TextField',
        'id' => 'search_field',
        'onSubmit' => '@{onAddTap}'
      }
      expect {
        described_class.generate(json_data, 0, required_imports)
      }.not_to raise_error
    end

    it 'wires onSubmit binding into KeyboardActions.onDone/onGo/onSearch/onSend' do
      json_data = {
        'type' => 'TextField',
        'id' => 'search_field',
        'onSubmit' => '@{onAddTap}'
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('keyboardActions = KeyboardActions(')
      expect(result).to include('onDone = { data.onAddTap?.invoke() }')
      expect(result).to include('onGo = { data.onAddTap?.invoke() }')
      expect(result).to include('onSearch = { data.onAddTap?.invoke() }')
      expect(result).to include('onSend = { data.onAddTap?.invoke() }')
    end

    it 'wires onSubmit raw method name into KeyboardActions' do
      json_data = {
        'type' => 'TextField',
        'id' => 'search_field',
        'onSubmit' => 'submitNewTag'
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('onDone = { data.submitNewTag?.invoke() }')
    end

    # Regression: kjui-keyboardactions-import-missing.
    # The KeyboardActions emit path must also register the import key
    # so import_manager actually writes the `import …KeyboardActions`
    # line into the generated file. Previously the key was added but
    # absent from IMPORTS_MAP, so it was silently dropped.
    it 'registers :keyboard_actions import key when onSubmit emits' do
      json_data = {
        'type' => 'TextField',
        'id' => 'search_field',
        'onSubmit' => '@{onAddTap}'
      }
      described_class.generate(json_data, 0, required_imports)
      expect(required_imports).to include(:keyboard_actions)
    end

    # Focus chain refactor (paired with kjui-keyboardactions-import-missing).
    # Before: `fieldId` / `nextFocusId` emitted a dead-code reference to a
    # non-existent `FocusManager.requestFocus(...)` helper. After: each
    # `fieldId` field declares its own `FocusRequester` via `remember`,
    # attaches it via the `.focusRequester(...)` modifier, and sibling
    # fields look up the target by `focusRequester_<nextFocusId>`.
    context 'fieldId emits FocusRequester declaration and modifier' do
      let(:json_data) do
        {
          'type' => 'TextField',
          'id' => 'first_input',
          'fieldId' => 'email_field'
        }
      end

      it 'emits `val focusRequester_<fieldId> = remember { FocusRequester() }` before the component call' do
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('val focusRequester_email_field = remember { FocusRequester() }')
      end

      it 'attaches .focusRequester(...) to the component modifier' do
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.focusRequester(focusRequester_email_field)')
      end

      it 'registers the :focus_requester and :remember import keys' do
        described_class.generate(json_data, 0, required_imports)
        expect(required_imports).to include(:focus_requester)
        expect(required_imports).to include(:remember)
      end
    end

    context 'nextFocusId emits FocusRequester.requestFocus() in onNext/onDone' do
      let(:json_data) do
        {
          'type' => 'TextField',
          'id' => 'first_input',
          'nextFocusId' => 'password_field',
          'returnKeyType' => 'Next'
        }
      end

      it 'emits onNext = { focusRequester_<nextFocusId>.requestFocus() }' do
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('onNext = { focusRequester_password_field.requestFocus() }')
        expect(result).to include('onDone = { focusRequester_password_field.requestFocus() }')
      end

      it 'NEVER emits the legacy non-existent FocusManager.requestFocus reference' do
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).not_to include('FocusManager.requestFocus')
      end
    end

    context 'fieldId + nextFocusId + onSubmit combined' do
      let(:json_data) do
        {
          'type' => 'TextField',
          'id' => 'first_input',
          'fieldId' => 'email_field',
          'nextFocusId' => 'password_field',
          'onSubmit' => '@{onSubmitForm}'
        }
      end

      it 'declares its own FocusRequester, references next field, and wires onSubmit handler' do
        result = described_class.generate(json_data, 0, required_imports)
        # own declaration
        expect(result).to include('val focusRequester_email_field = remember { FocusRequester() }')
        # own modifier registration
        expect(result).to include('.focusRequester(focusRequester_email_field)')
        # focus chain to next
        expect(result).to include('focusRequester_password_field.requestFocus()')
        # onSubmit handler still wired into onGo/onSearch/onSend (onDone goes to focus chain when next_focus_id is set)
        expect(result).to include('onGo = { data.onSubmitForm?.invoke() }')
      end
    end
  end

  describe '.extract_variable_name' do
    it 'extracts simple variable name' do
      result = described_class.send(:extract_variable_name, '@{name}')
      expect(result).to eq('name')
    end

    it 'extracts nested variable name' do
      result = described_class.send(:extract_variable_name, '@{user.name}')
      expect(result).to eq('name')
    end

    it 'returns default for nil' do
      result = described_class.send(:extract_variable_name, nil)
      expect(result).to eq('value')
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
  end

  describe 'event handler invocation' do
    it 'generates invoke() without arguments when handler type is () -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onTextChange' => { 'name' => 'onTextChange', 'class' => '(() -> Unit)?' }
      }

      json_data = {
        'type' => 'TextField',
        'id' => 'emailField',
        'text' => '@{email}',
        'onTextChange' => '@{onTextChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onTextChange?.invoke()')
      expect(result).not_to include('invoke("emailField"')
    end

    it 'generates invoke(viewId, value) when handler type is (Event) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onTextChange' => { 'name' => 'onTextChange', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'TextField',
        'id' => 'emailField',
        'text' => '@{email}',
        'onTextChange' => '@{onTextChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onTextChange?.invoke("emailField", newValue)')
    end

    it 'generates invoke(viewId, value) when handler type is (String, String) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onTextChange' => { 'name' => 'onTextChange', 'class' => '((String, String) -> Unit)?' }
      }

      json_data = {
        'type' => 'TextField',
        'id' => 'searchField',
        'onTextChange' => '@{onTextChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onTextChange?.invoke("searchField", newValue)')
    end

    it 'includes both viewModel.updateData and handler invocation when both binding and handler exist' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onTextChange' => { 'name' => 'onTextChange', 'class' => '((String, String) -> Unit)?' }
      }

      json_data = {
        'type' => 'TextField',
        'id' => 'emailField',
        'text' => '@{email}',
        'onTextChange' => '@{onTextChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('viewModel.updateData')
      expect(result).to include('data.onTextChange?.invoke("emailField", newValue)')
    end

    it 'uses default textfield id when no id specified' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onTextChange' => { 'name' => 'onTextChange', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'TextField',
        'onTextChange' => '@{onTextChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onTextChange?.invoke("textfield", newValue)')
    end
  end
end
