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
  end
end
