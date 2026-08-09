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
      expect(result).to match(/fontSize = \(resolved_textfield\d+\.size \?: LocalTextStyle\.current\.fontSize\)/)
    end

    it 'generates TextField with fontColor' do
      json_data = { 'type' => 'TextField', 'fontColor' => '#333333' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('textStyle = TextStyle')
      expect(result).to include('color')
    end

    # A field with no hint AND no fontColor is the only shape that reaches the
    # Configuration fallback alone: the placeholder branch registers the same
    # import, so every fixture that declared a hint hid this. The generated
    # view then failed to compile — `Unresolved reference 'Configuration'` —
    # and took the whole android-codegen conformance host down with it.
    it 'imports Configuration when the text colour falls back to it' do
      json_data = { 'type' => 'TextField' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Configuration.TextField.defaultTextColor')
      expect(required_imports).to include(:configuration)
    end

    it 'imports Configuration when the font size falls back to it' do
      json_data = { 'type' => 'TextField', 'fontColor' => '#333333' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Configuration.TextField.defaultFontSize.sp')
      expect(required_imports).to include(:configuration)
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

    # inputType is the Android-XML spelling, read only by the frozen XML mode
    # until now — a layout migrated to Compose lost its keyboard silently.
    context 'inputType (XML-mode migration fallback)' do
      it 'maps the XML mapper vocabulary' do
        result = described_class.generate(
          { 'type' => 'TextField', 'inputType' => 'email' }, 0, required_imports
        )
        expect(result).to include('KeyboardType.Email')
        expect(required_imports).to include(:keyboard_type)
      end

      it 'maps the raw android:inputType names the mapper passes through' do
        expect(described_class.generate(
          { 'type' => 'TextField', 'inputType' => 'textPassword' }, 0, required_imports
        )).to include('KeyboardType.Password')
        expect(described_class.generate(
          { 'type' => 'TextField', 'inputType' => 'numberDecimal' }, 0, required_imports
        )).to include('KeyboardType.Decimal')
      end

      it 'falls back to a text keyboard for anything else' do
        expect(described_class.generate(
          { 'type' => 'TextField', 'inputType' => 'textMultiLine' }, 0, required_imports
        )).to include('KeyboardType.Text')
      end

      # `input` is the canonical cross-platform attribute and must win.
      it 'yields to input' do
        result = described_class.generate(
          { 'type' => 'TextField', 'input' => 'phone', 'inputType' => 'email' }, 0, required_imports
        )
        expect(result).to include('KeyboardType.Phone')
        expect(result).not_to include('KeyboardType.Email')
      end

      it 'yields to contentType' do
        result = described_class.generate(
          { 'type' => 'TextField', 'contentType' => 'emailAddress', 'inputType' => 'phone' },
          0, required_imports
        )
        expect(result).to include('KeyboardType.Email')
        expect(result).not_to include('KeyboardType.Phone')
      end
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
      expect(result).to include('.requiredWidth(200.dp)')
      expect(result).to include('.requiredHeight(50.dp)')
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

    # Regression: kjui-textfield-weight-not-fillmaxwidth-inner.
    # `CustomTextFieldWithMargins(boxModifier = Modifier.weight(N), textFieldModifier = Modifier)`
    # leaves the inner BasicTextField at wrap-content — the Box's weighted
    # slot does not propagate as a width/height constraint to its child.
    # The codegen must auto-emit `.fillMaxWidth()` (Row parent) or
    # `.fillMaxHeight()` (Column parent) on textFieldModifier when weight
    # is set and a margin path forces the Box wrapper.
    context 'weighted TextField with margins (forces Box wrap)' do
      it 'emits .fillMaxWidth() on textFieldModifier when weight is set under a Row parent' do
        json_data = {
          'type' => 'TextField',
          'id' => 'search_field',
          'weight' => 1,
          'rightMargin' => 8,
          'text' => '@{searchText}'
        }
        result = described_class.generate(json_data, 0, required_imports, 'Row')
        expect(result).to include('CustomTextFieldWithMargins(')
        expect(result).to include('boxModifier = Modifier')
        expect(result).to include('.weight(1f)')
        expect(result).to include('textFieldModifier = Modifier')
        expect(result).to include('.fillMaxWidth()')
      end

      it 'emits .fillMaxHeight() on textFieldModifier when weight is set under a Column parent' do
        json_data = {
          'type' => 'TextField',
          'id' => 'tall_field',
          'weight' => 1,
          'topMargin' => 8,
          'text' => '@{txt}'
        }
        result = described_class.generate(json_data, 0, required_imports, 'Column')
        expect(result).to include('textFieldModifier = Modifier')
        expect(result).to include('.fillMaxHeight()')
      end

      it 'does NOT duplicate .fillMaxWidth() when width: matchParent is already explicit' do
        # build_size emits .fillMaxWidth() for matchParent; the weight
        # auto-injection must dedupe to a single named modifier rather
        # than producing `.fillMaxWidth().fillMaxWidth()`. The only emit
        # site for `.fillMaxWidth()` in this generator is inside the
        # textFieldModifier chain, so a global single-occurrence check
        # is equivalent to per-chunk dedup verification.
        json_data = {
          'type' => 'TextField',
          'id' => 'sf',
          'weight' => 1,
          'width' => 'matchParent',
          'rightMargin' => 8
        }
        result = described_class.generate(json_data, 0, required_imports, 'Row')
        expect(result.scan('.fillMaxWidth()').size).to eq(1)
      end

      it 'does NOT emit fill modifier when weight is absent (e.g. fixed width field with margins)' do
        json_data = {
          'type' => 'TextField',
          'id' => 'sf',
          'width' => 200,
          'rightMargin' => 8
        }
        result = described_class.generate(json_data, 0, required_imports, 'Row')
        expect(result).not_to include('.fillMaxWidth()')
        expect(result).not_to include('.fillMaxHeight()')
      end

      it 'does NOT emit fill modifier when weight is set but parent is not Row/Column (e.g. nil parent)' do
        # No-op safety: if parent isn't a Row/Column scope, `.weight()`
        # itself wouldn't make sense (build_weight skips it via the
        # truthy parent_orientation guard). Same logic for the inner
        # fill — there's no axis to fill on.
        json_data = {
          'type' => 'TextField',
          'id' => 'sf',
          'weight' => 1,
          'rightMargin' => 8
        }
        result = described_class.generate(json_data, 0, required_imports, nil)
        expect(result).not_to include('.fillMaxWidth()')
        expect(result).not_to include('.fillMaxHeight()')
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

  describe 'id-less state var uniquing' do
    it 'gives two id-less TextFields distinct state vars' do
      json1 = { 'type' => 'TextField', 'text' => 'a' }
      json2 = { 'type' => 'TextField', 'text' => 'b' }
      code1 = described_class.generate(json1, 0, Set.new)
      code2 = described_class.generate(json2, 0, Set.new)
      var1 = code1[/val (textFieldState_\w+)/, 1]
      var2 = code2[/val (textFieldState_\w+)/, 1]
      expect(var1).not_to be_nil
      expect(var2).not_to be_nil
      expect(var1).not_to eq(var2)
    end

    it 'keeps the id-based name when an id is present' do
      json = { 'type' => 'TextField', 'id' => 'email_field', 'text' => 'a' }
      code = described_class.generate(json, 0, Set.new)
      expect(code).to include('val textFieldState_email_field')
    end
  end
  # kjui-textfield-isfocused-focus-binding-not-generated: sjui parity —
  # every TextField with an id gets ViewModel-driven focus wiring.
  describe 'focus-state binding (data.<id>IsFocused)' do
    it 'emits FocusRequester + LaunchedEffect + keyboard show for an id-bearing field' do
      json_data = { 'type' => 'TextField', 'id' => 'two_fa_hidden_input' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('val focusRequester_two_fa_hidden_input = remember { FocusRequester() }')
      expect(result).to include('val keyboardController_two_fa_hidden_input = LocalSoftwareKeyboardController.current')
      expect(result).to include('LaunchedEffect(data.twoFaHiddenInputIsFocused) { if (data.twoFaHiddenInputIsFocused) { focusRequester_two_fa_hidden_input.requestFocus(); keyboardController_two_fa_hidden_input?.show() } }')
      expect(result).to include('.focusRequester(focusRequester_two_fa_hidden_input)')
      expect(required_imports).to include(:focus_requester)
      expect(required_imports).to include(:software_keyboard_controller)
    end

    it 'reports focus changes back into data via viewModel.updateData (two-way)' do
      json_data = { 'type' => 'TextField', 'id' => 'email_field' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.onFocusChanged { if (it.isFocused != data.emailFieldIsFocused) viewModel.updateData(mapOf("emailFieldIsFocused" to it.isFocused)) }')
      expect(required_imports).to include(:focus_changed)
    end

    it 'wires the focus binding on the margins (Box-wrapped) variant too' do
      json_data = { 'type' => 'TextField', 'id' => 'code_field', 'topMargin' => 8 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('CustomTextFieldWithMargins(')
      expect(result).to include('.focusRequester(focusRequester_code_field)')
      expect(result).to include('.onFocusChanged { if (it.isFocused != data.codeFieldIsFocused)')
    end

    it 'shares the requester with the fieldId focus chain (fieldId keeps naming priority)' do
      json_data = { 'type' => 'TextField', 'id' => 'email_field', 'fieldId' => 'email' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('val focusRequester_email = remember { FocusRequester() }')
      expect(result.scan('remember { FocusRequester() }').size).to eq(1)
      expect(result).to include('LaunchedEffect(data.emailFieldIsFocused) { if (data.emailFieldIsFocused) { focusRequester_email.requestFocus()')
    end

    it 'emits no focus binding for an id-less TextField' do
      json_data = { 'type' => 'TextField' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).not_to include('IsFocused')
      expect(result).not_to include('FocusRequester()')
    end
  end
end

RSpec.describe KjuiTools::Compose::Components::TextFieldComponent, 'nextFocus' do
  let(:required_imports) { Set.new }

  def field(extra)
    described_class.generate(
      { 'type' => 'TextField', 'id' => 'email', 'text' => '@{email}' }.merge(extra),
      0, required_imports
    )
  end

  # `nextFocus` is the declared attribute (and what the iOS converter reads);
  # `nextFocusId` is the undeclared legacy spelling this file was written
  # against, so a layout using the declared name got no focus chain at all.
  it 'wires the chain from the declared nextFocus' do
    expect(field('nextFocus' => 'password')).to include('focusRequester_password')
  end

  it 'still accepts the legacy nextFocusId' do
    expect(field('nextFocusId' => 'password')).to include('focusRequester_password')
  end

  it 'prefers the declared name when both are set' do
    result = field('nextFocus' => 'declared', 'nextFocusId' => 'legacy')
    expect(result).to include('focusRequester_declared')
    expect(result).not_to include('focusRequester_legacy')
  end

  it 'emits no chain when neither is set' do
    expect(field({})).not_to include('KeyboardActions')
  end

  # Regression: sjui-kjui-textview-enabled-binding-gaps-after-common-enabled-fix
  # — TextView passed `enabled` through to the composable; TextField never
  # did, so the a11y `disabled()` from the common modifier path claimed a
  # state the input didn't have (typing stayed possible).
  describe 'enabled' do
    it 'forwards a bound enabled to the composable' do
      expect(field('enabled' => '@{isInputEnabled}')).to include('enabled = data.isInputEnabled')
    end

    it 'forwards a literal enabled' do
      expect(field('enabled' => false)).to include('enabled = false')
    end

    it 'emits nothing when undeclared' do
      expect(field({})).not_to include('enabled =')
    end
  end
end
