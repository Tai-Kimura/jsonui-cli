# frozen_string_literal: true

require 'swiftui/views/textfield_converter'

RSpec.describe SjuiTools::SwiftUI::Views::TextFieldConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'with basic text field' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Enter text',
          'text' => '@{inputText}'
        }
      end

      it 'generates TextField view' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('TextField(')
        expect(code).to include('Enter text')
      end

      it 'uses binding for text' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('text:')
      end
    end

    context 'with placeholder alias' do
      let(:component) do
        {
          'type' => 'TextField',
          'placeholder' => 'Placeholder text'
        }
      end

      it 'uses placeholder as hint' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Placeholder text')
      end
    end

    context 'with password input' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Password',
          'input' => 'password',
          'text' => '@{password}'
        }
      end

      it 'adds default keyboard type' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.keyboardType(.default)')
      end
    end

    context 'with secure field' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Password',
          'secure' => true,
          'text' => '@{password}'
        }
      end

      it 'generates SecureField' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('SecureField(')
      end
    end

    context 'with borderStyle roundedRect' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Test',
          'borderStyle' => 'roundedRect'
        }
      end

      it 'adds roundedBorder textFieldStyle' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.textFieldStyle(.roundedBorder)')
      end
    end

    context 'with borderStyle none' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Test',
          'borderStyle' => 'none'
        }
      end

      it 'adds plain textFieldStyle' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.textFieldStyle(.plain)')
      end
    end

    context 'with email input type' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Email',
          'input' => 'email'
        }
      end

      it 'adds emailAddress keyboard type' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.keyboardType(.emailAddress)')
      end
    end

    context 'with number input type' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Number',
          'input' => 'number'
        }
      end

      it 'adds numberPad keyboard type' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.keyboardType(.numberPad)')
      end
    end

    context 'with decimal input type' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Decimal',
          'input' => 'decimal'
        }
      end

      it 'adds decimalPad keyboard type' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.keyboardType(.decimalPad)')
      end
    end

    context 'with URL input type' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'URL',
          'input' => 'URL'
        }
      end

      it 'adds URL keyboard type' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.keyboardType(.URL)')
      end
    end

    context 'with returnKeyType Done' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Test',
          'returnKeyType' => 'Done'
        }
      end

      it 'adds done submitLabel' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.submitLabel(.done)')
      end
    end

    context 'with returnKeyType Search' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Test',
          'returnKeyType' => 'Search'
        }
      end

      it 'adds search submitLabel' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.submitLabel(.search)')
      end
    end

    context 'with fontColor' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Test',
          'fontColor' => '#333333'
        }
      end

      it 'adds foregroundColor modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.foregroundColor(')
      end
    end

    context 'with fontSize' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Test',
          'fontSize' => 16
        }
      end

      it 'adds font modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.font(')
      end
    end

    context 'with contentType email' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Email',
          'contentType' => 'email'
        }
      end

      it 'adds emailAddress textContentType' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.textContentType(.emailAddress)')
      end
    end

    context 'with contentType username' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Username',
          'contentType' => 'username'
        }
      end

      it 'adds username textContentType' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.textContentType(.username)')
      end
    end

    # Regression: sjui-textfield-contenttype-newpassword-not-mapped — the
    # declared SSoT attribute was silently degraded to .none.
    context 'with contentType newPassword' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'New password',
          'contentType' => 'newPassword'
        }
      end

      it 'adds newPassword textContentType' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.textContentType(.newPassword)')
      end
    end

    context 'with contentType oneTimeCode' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Code',
          'contentType' => 'oneTimeCode'
        }
      end

      it 'adds oneTimeCode textContentType' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.textContentType(.oneTimeCode)')
      end
    end

    context 'with unknown contentType' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'X',
          'contentType' => 'notARealType'
        }
      end

      it 'warns instead of silently dropping to .none' do
        converter = described_class.new(component)
        expect { converter.convert }.to output(/unknown contentType 'notARealType'/).to_stdout
      end
    end

    context 'with disabled state' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Test',
          'enabled' => false
        }
      end

      it 'adds disabled modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.disabled(true)')
      end

      # The bound form is covered by TextFieldBindingHandler, not this
      # converter — pinned here so the TextView gap
      # (sjui-kjui-textview-enabled-binding-gaps-after-common-enabled-fix)
      # can't silently reappear on TextField.
      it 'inverts a bound enabled (via the binding handler)' do
        code = described_class.new({
          'type' => 'TextField', 'hint' => 'Test', 'enabled' => '@{isInputEnabled}'
        }).convert
        expect(code).to include('.disabled(!data.isInputEnabled)')
      end
    end

    context 'with background and cornerRadius' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Test',
          'background' => '#F5F5F5',
          'cornerRadius' => 8
        }
      end

      it 'adds background modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.background(')
      end

      it 'adds cornerRadius modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.cornerRadius(8)')
      end
    end

    context 'with border' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Test',
          'borderWidth' => 1,
          'borderColor' => '#CCCCCC',
          'cornerRadius' => 8
        }
      end

      it 'adds overlay with RoundedRectangle stroke' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.overlay(')
        expect(code).to include('RoundedRectangle')
        expect(code).to include('.stroke(')
      end
    end

    context 'with caretAttributes' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Test',
          'caretAttributes' => {
            'fontColor' => '#007AFF'
          }
        }
      end

      # Modern SwiftUI uses .tint() for caret / accent color.
      it 'adds tint modifier for caret color' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.tint(')
      end
    end

    context 'with textPaddingLeft' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Test',
          'textPaddingLeft' => 16
        }
      end

      it 'adds leading padding' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.padding(.leading, 16)')
      end
    end

    context 'with shadow' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Test',
          'shadow' => {
            'radius' => 4,
            'offsetX' => 0,
            'offsetY' => 2,
            'color' => '#000000'
          }
        }
      end

      it 'adds shadow modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.shadow(')
      end
    end

    # Regression: sjui-textfield-onsubmit-not-exposed.
    # JSON `onSubmit` was not honored — only `nextFocus` triggered a
    # .onSubmit { } block. Now `onSubmit` (binding form `@{handler}` or
    # raw method name `handler`) emits the SwiftUI .onSubmit closure,
    # mirroring kjui's KeyboardActions.onDone/onGo/onSearch/onSend wiring.
    context 'with onSubmit binding handler' do
      let(:component) do
        {
          'type' => 'TextField',
          'id' => 'search_field',
          'hint' => 'Search',
          'text' => '@{searchText}',
          'onSubmit' => '@{onAddTap}'
        }
      end

      it 'emits .onSubmit { data.onAddTap?() }' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.onSubmit {')
        expect(code).to include('data.onAddTap?()')
      end
    end

    context 'with onSubmit raw method name (non-binding)' do
      let(:component) do
        {
          'type' => 'TextField',
          'id' => 'search_field',
          'hint' => 'Search',
          'text' => '@{searchText}',
          'onSubmit' => 'submitNewTag'
        }
      end

      it 'emits .onSubmit { data.submitNewTag?() }' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.onSubmit {')
        expect(code).to include('data.submitNewTag?()')
      end
    end

    context 'with onSubmit and no id' do
      let(:component) do
        {
          'type' => 'TextField',
          'hint' => 'Search',
          'onSubmit' => '@{onAddTap}'
        }
      end

      it 'still emits .onSubmit even without an id' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.onSubmit {')
        expect(code).to include('data.onAddTap?()')
      end
    end

    context 'with nextFocus only (no onSubmit)' do
      let(:component) do
        {
          'type' => 'TextField',
          'id' => 'first_field',
          'hint' => 'First',
          'text' => '@{firstText}',
          'nextFocus' => 'second_field'
        }
      end

      it 'emits .onSubmit { } that chains focus to nextFocus field' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.onSubmit {')
        expect(code).to include('data.firstFieldIsFocused = false')
        expect(code).to include('data.secondFieldIsFocused = true')
        expect(code).not_to match(/data\.\w+\?\(\)/)
      end
    end

    context 'with both nextFocus and onSubmit (combined)' do
      let(:component) do
        {
          'type' => 'TextField',
          'id' => 'first_field',
          'hint' => 'First',
          'text' => '@{firstText}',
          'nextFocus' => 'second_field',
          'onSubmit' => '@{onAddTap}'
        }
      end

      it 'emits a single .onSubmit { } that runs focus chain then onSubmit handler' do
        converter = described_class.new(component)
        code = converter.convert

        # Single .onSubmit block (no duplicate)
        expect(code.scan('.onSubmit {').size).to eq(1)
        # Focus chain present
        expect(code).to include('data.firstFieldIsFocused = false')
        expect(code).to include('data.secondFieldIsFocused = true')
        # onSubmit handler present
        expect(code).to include('data.onAddTap?()')
      end
    end

    context 'with neither nextFocus nor onSubmit' do
      let(:component) do
        {
          'type' => 'TextField',
          'id' => 'search_field',
          'hint' => 'Search',
          'text' => '@{searchText}'
        }
      end

      it 'does NOT emit .onSubmit { } block' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).not_to include('.onSubmit {')
      end
    end

    # All of these are declared, honoured by Compose and/or web, and were read
    # by nobody here — a field declared with them silently did nothing on iOS.
    describe 'focus handlers' do
      it 'fires onFocus and onBlur from the FocusState change' do
        code = described_class.new({
          'type' => 'TextField', 'id' => 'email', 'text' => '@{email}',
          'onFocus' => 'handleFocus', 'onBlur' => 'handleBlur'
        }).convert

        expect(code).to include('if newValue {')
        expect(code).to include('data.handleFocus?()')
        expect(code).to include('data.handleBlur?()')
      end

      it 'treats the UIKit names as the same two moments' do
        code = described_class.new({
          'type' => 'TextField', 'id' => 'email', 'text' => '@{email}',
          'onBeginEditing' => 'began', 'onEndEditing' => 'ended'
        }).convert

        expect(code).to include('data.began?()')
        expect(code).to include('data.ended?()')
      end

      it 'still declares the FocusState when there is no id' do
        code = described_class.new({
          'type' => 'TextField', 'text' => '@{email}', 'onFocus' => 'handleFocus'
        }).convert

        expect(code).to include('.focused($fieldIsFocused)')
      end
    end

    describe 'input traits' do
      it 'maps autocapitalizationType onto textInputAutocapitalization' do
        code = described_class.new({
          'type' => 'TextField', 'autocapitalizationType' => 'words'
        }).convert
        expect(code).to include('.textInputAutocapitalization(.words)')
      end

      it 'maps autocorrectionType no onto autocorrectionDisabled(true)' do
        code = described_class.new({
          'type' => 'TextField', 'autocorrectionType' => 'no'
        }).convert
        expect(code).to include('.autocorrectionDisabled(true)')
      end

      it 'applies fieldPadding' do
        code = described_class.new({ 'type' => 'TextField', 'fieldPadding' => 12 }).convert
        expect(code).to include('.padding(12)')
      end
    end

    describe 'maxLength' do
      it 'truncates on change, since SwiftUI TextField has no length limit' do
        code = described_class.new({
          'type' => 'TextField', 'text' => '@{email}', 'maxLength' => 10
        }).convert

        expect(code).to include('newValue.count > 10')
        expect(code).to include('String(newValue.prefix(10))')
      end

      it 'emits nothing without a binding to write back to' do
        code = described_class.new({
          'type' => 'TextField', 'text' => 'static', 'maxLength' => 10
        }).convert

        expect(code).not_to include('prefix(10)')
      end
    end

    # clearButtonMode — SwiftUI has no clear button, so the library supplies the
    # overlay and the converter decides whether and how it applies.
    describe 'clearButtonMode' do
      def field(extra)
        described_class.new({ 'type' => 'TextField', 'id' => 'email', 'text' => '@{email}' }.merge(extra)).convert
      end

      it 'passes the mode and the text binding to clear' do
        expect(field('clearButtonMode' => 'always'))
          .to include('.textFieldClearButton(mode: .always, text: $data.email)')
      end

      it 'feeds the focus state to the editing-sensitive modes' do
        expect(field('clearButtonMode' => 'whileEditing'))
          .to include('.textFieldClearButton(mode: .whileEditing, text: $data.email, isEditing: emailIsFocused)')
        expect(field('clearButtonMode' => 'unlessEditing'))
          .to include('isEditing: emailIsFocused')
      end

      it 'omits the editing flag where it cannot change the outcome' do
        expect(field('clearButtonMode' => 'always')).not_to include('isEditing:')
      end

      it 'accepts the snake_case spelling' do
        expect(field('clearButtonMode' => 'while_editing')).to include('mode: .whileEditing')
      end

      it 'emits nothing for never' do
        expect(field('clearButtonMode' => 'never')).not_to include('textFieldClearButton')
      end

      it 'emits nothing for an unrecognised mode rather than guessing one' do
        expect(field('clearButtonMode' => 'sometimes')).not_to include('textFieldClearButton')
      end

      it 'emits nothing when absent' do
        expect(field({})).not_to include('textFieldClearButton')
      end

      # whileEditing needs a focus state even on a field that has no id and no
      # focus handlers — but nothing to sync, so no onChange closure.
      it 'creates the focus state a bare field would not otherwise have' do
        converter = described_class.new({
          'type' => 'TextField', 'text' => '@{email}', 'clearButtonMode' => 'whileEditing'
        })
        code = converter.convert

        expect(converter.state_variables).to include('@FocusState private var fieldIsFocused: Bool')
        expect(code).to include('.focused($fieldIsFocused)')
        expect(code).to include('isEditing: fieldIsFocused')
        # Nothing to sync, so the closure would have had an empty body.
        expect(code).not_to include('.onChange(of: fieldIsFocused)')
      end

      it 'leaves a bare field alone for modes that do not read focus' do
        converter = described_class.new({
          'type' => 'TextField', 'text' => '@{email}', 'clearButtonMode' => 'always'
        })
        code = converter.convert

        expect(converter.state_variables).to be_empty
        expect(code).not_to include('.focused(')
      end
    end
  end
end
