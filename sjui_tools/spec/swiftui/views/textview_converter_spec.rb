# frozen_string_literal: true

require 'swiftui/views/textview_converter'

RSpec.describe SjuiTools::SwiftUI::Views::TextViewConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'with binding text' do
      let(:component) { { 'type' => 'TextView', 'id' => 'notes', 'text' => '@{noteText}' } }

      it 'generates TextViewWithPlaceholder with binding' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('TextViewWithPlaceholder(')
        expect(code).to include('text: $data.noteText')
      end
    end

    context 'without binding text' do
      let(:component) { { 'type' => 'TextView', 'id' => 'editor' } }

      it 'creates state variable fallback' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('TextViewWithPlaceholder(')
        # The fallback is a view-local @State variable (injected by
        # update_generated_body), so the reference is the bare name — a
        # `data.` prefix points at a property the Data model never grows
        # (uncompilable; caught by the codegen parity host, 2026-08-02).
        expect(code).to include('text: $editorText')
        expect(converter.state_variables).to include(
          '@State private var editorText: String = ""'
        )
      end
    end

    context 'with hint' do
      let(:component) { { 'type' => 'TextView', 'text' => '@{content}', 'hint' => 'Enter your message' } }

      it 'includes hint parameter' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('hint:')
      end
    end

    context 'with placeholder (fallback to hint)' do
      let(:component) { { 'type' => 'TextView', 'text' => '@{content}', 'placeholder' => 'Type here...' } }

      it 'uses placeholder as hint when hint is not specified' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('hint:')
        expect(code).to include('Type here...')
      end
    end

    context 'with both hint and placeholder' do
      let(:component) { { 'type' => 'TextView', 'text' => '@{content}', 'hint' => 'Primary hint', 'placeholder' => 'Fallback placeholder' } }

      it 'uses hint over placeholder' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Primary hint')
        expect(code).not_to include('Fallback placeholder')
      end
    end

    context 'with hintAttributes' do
      let(:component) do
        {
          'type' => 'TextView',
          'text' => '@{content}',
          'hintAttributes' => {
            'fontColor' => '#888888',
            'font' => 'Helvetica',
            'fontSize' => 14,
            'lineHeightMultiple' => 1.5
          }
        }
      end

      it 'includes hintColor from attributes' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('hintColor:')
      end

      it 'includes hintFont from attributes' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('hintFont: "Helvetica"')
      end

      it 'includes hintFontSize from attributes' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('hintFontSize: 14')
      end

      it 'includes hintLineHeightMultiple from attributes' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('hintLineHeightMultiple: 1.5')
      end
    end

    context 'with individual hint properties' do
      let(:component) do
        {
          'type' => 'TextView',
          'text' => '@{content}',
          'hintColor' => '#666666',
          'hintFont' => 'Arial',
          'hintFontSize' => 12,
          'hintLineHeightMultiple' => 1.2
        }
      end

      it 'includes individual hint properties' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('hintColor:')
        expect(code).to include('hintFont: "Arial"')
        expect(code).to include('hintFontSize: 12')
        expect(code).to include('hintLineHeightMultiple: 1.2')
      end
    end

    context 'with hideOnFocused false' do
      let(:component) { { 'type' => 'TextView', 'text' => '@{x}', 'hideOnFocused' => false } }

      it 'includes hideOnFocused parameter' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('hideOnFocused: false')
      end
    end

    context 'with font properties' do
      let(:component) do
        {
          'type' => 'TextView',
          'text' => '@{x}',
          'fontSize' => 16,
          'fontColor' => '#333333',
          'font' => 'Georgia'
        }
      end

      it 'includes fontSize' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('fontSize: 16')
      end

      it 'includes fontColor' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('fontColor:')
      end

      it 'includes fontName' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('fontName: "Georgia"')
      end
    end

    context 'with background and cornerRadius' do
      let(:component) do
        {
          'type' => 'TextView',
          'text' => '@{x}',
          'background' => '#FFFFFF',
          'cornerRadius' => 8
        }
      end

      it 'includes backgroundColor' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('backgroundColor:')
      end

      it 'includes cornerRadius' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('cornerRadius: 8')
      end
    end

    context 'with containerInset' do
      it 'handles single value' do
        component = { 'type' => 'TextView', 'text' => '@{x}', 'containerInset' => 10 }
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('containerInset: EdgeInsets(top: 10, leading: 10, bottom: 10, trailing: 10)')
      end

      it 'handles array with 1 value' do
        component = { 'type' => 'TextView', 'text' => '@{x}', 'containerInset' => [8] }
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('containerInset: EdgeInsets(top: 8, leading: 8, bottom: 8, trailing: 8)')
      end

      it 'handles array with 2 values' do
        component = { 'type' => 'TextView', 'text' => '@{x}', 'containerInset' => [8, 16] }
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('containerInset: EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16)')
      end

      it 'handles array with 4 values' do
        component = { 'type' => 'TextView', 'text' => '@{x}', 'containerInset' => [5, 10, 15, 20] }
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('containerInset: EdgeInsets(top: 5, leading: 10, bottom: 15, trailing: 20)')
      end
    end

    context 'with flexible' do
      let(:component) { { 'type' => 'TextView', 'text' => '@{x}', 'flexible' => true } }

      it 'includes flexible parameter' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('flexible: true')
      end
    end

    context 'with minHeight and maxHeight' do
      let(:component) do
        {
          'type' => 'TextView',
          'text' => '@{x}',
          'flexible' => true,
          'minHeight' => 100,
          'maxHeight' => 300
        }
      end

      it 'includes minHeight parameter' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('minHeight: 100')
      end

      it 'includes maxHeight parameter' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('maxHeight: 300')
      end

      it 'applies frame modifier for flexible' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.frame(minHeight: 100, maxHeight: 300)')
      end
    end

    context 'with border' do
      let(:component) do
        {
          'type' => 'TextView',
          'text' => '@{x}',
          'borderWidth' => 1,
          'borderColor' => '#CCCCCC',
          'cornerRadius' => 4
        }
      end

      it 'applies overlay with stroke' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.overlay(')
        expect(code).to include('RoundedRectangle(cornerRadius: 4)')
        expect(code).to include('.stroke(')
        expect(code).to include('lineWidth: 1')
      end
    end

    context 'with alpha and hidden' do
      let(:component) do
        {
          'type' => 'TextView',
          'text' => '@{x}',
          'alpha' => 0.8,
          'hidden' => true
        }
      end

      it 'applies opacity modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.opacity(0.8)')
      end

      it 'applies hidden modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.opacity(0).accessibilityHidden(true)')
      end
    end

    context 'with opacity instead of alpha' do
      let(:component) { { 'type' => 'TextView', 'text' => '@{x}', 'opacity' => 0.5 } }

      it 'applies opacity modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.opacity(0.5)')
      end
    end
  end
  # Focus-state binding — TextField parity: an id-bearing TextView binds
  # data.<id>IsFocused into TextViewWithPlaceholder (isFocused: param,
  # SwiftJsonUI v10.3.0+) so a ViewModel can drive focus.
  describe 'focus-state binding (data.<id>IsFocused)' do
    it 'passes the isFocused binding for an id-bearing TextView' do
      converter = described_class.new({ 'type' => 'TextView', 'id' => 'note_input', 'text' => '@{note}' })
      code = converter.convert
      expect(code).to include('isFocused: $data.noteInputIsFocused')
    end

    it 'emits no isFocused binding for an id-less TextView' do
      converter = described_class.new({ 'type' => 'TextView', 'text' => '@{note}' })
      code = converter.convert
      expect(code).not_to include('isFocused:')
    end

    # Regression: isFocused is the LAST init parameter in the library, and
    # Swift requires call-site argument order to match the declaration.
    # Emitting it right after text: broke compilation whenever hint etc.
    # followed ("argument 'hint' must precede argument 'isFocused'").
    it 'emits isFocused after hint (declaration order)' do
      converter = described_class.new({
        'type' => 'TextView', 'id' => 'note_input', 'text' => '@{note}', 'hint' => 'placeholder'
      })
      code = converter.convert
      expect(code.index('hint:')).to be < code.index('isFocused:')
    end

    it 'emits isFocused as the last argument, after maxHeight, without a trailing comma' do
      converter = described_class.new({
        'type' => 'TextView', 'id' => 'note_input', 'text' => '@{note}',
        'hint' => 'placeholder', 'fontSize' => 15, 'minHeight' => 24, 'maxHeight' => 100
      })
      code = converter.convert
      expect(code.index('maxHeight: 100,')).to be < code.index('isFocused:')
      expect(code).to match(/isFocused: \$data\.noteInputIsFocused\s*\)/)
    end

    # A read-only TextView was fully editable on iOS: both attributes are
    # declared and honoured elsewhere, and neither was read here.
    describe 'editable / keyboardType' do
      it 'disables the editor when editable is false' do
        code = described_class.new({ 'type' => 'TextView', 'editable' => false }).convert
        expect(code).to include('.disabled(true)')
      end

      it 'inverts a bound editable' do
        code = described_class.new({ 'type' => 'TextView', 'editable' => '@{canEdit}' }).convert
        expect(code).to include('.disabled(!(')
      end

      it 'leaves an editable TextView alone' do
        code = described_class.new({ 'type' => 'TextView', 'editable' => true }).convert
        expect(code).not_to include('.disabled(')
      end

      it 'maps keyboardType onto the SwiftUI spelling' do
        code = described_class.new({ 'type' => 'TextView', 'keyboardType' => 'email' }).convert
        expect(code).to include('.keyboardType(.emailAddress)')
      end

      it 'ignores an unknown keyboardType rather than emitting bad Swift' do
        code = described_class.new({ 'type' => 'TextView', 'keyboardType' => 'nonsense' }).convert
        expect(code).not_to include('.keyboardType(')
      end
    end

    # Regression: sjui-kjui-textview-enabled-binding-gaps-after-common-enabled-fix
    # — TextView assembles its own modifier set, so the base converter's
    # `enabled` block never ran here and a declared `enabled` emitted nothing.
    describe 'enabled' do
      it 'maps a bound enabled to .disabled with the negated expression' do
        code = described_class.new({ 'type' => 'TextView', 'text' => '@{t}', 'enabled' => '@{isInputEnabled}' }).convert
        expect(code).to include('.disabled(!((data.isInputEnabled ?? false)))')
      end

      it 'maps a literal enabled: false to .disabled(true)' do
        code = described_class.new({ 'type' => 'TextView', 'text' => '@{t}', 'enabled' => false }).convert
        expect(code).to include('.disabled(true)')
      end

      it 'leaves an enabled TextView alone' do
        code = described_class.new({ 'type' => 'TextView', 'text' => '@{t}', 'enabled' => true }).convert
        expect(code).not_to include('.disabled(')
      end

      it 'OR-combines editable and enabled instead of clobbering (register is last-wins)' do
        code = described_class.new({
          'type' => 'TextView', 'text' => '@{t}',
          'editable' => '@{canEdit}', 'enabled' => '@{isOn}'
        }).convert
        expect(code).to include('.disabled(!((data.canEdit ?? false)) || !((data.isOn ?? false)))')
      end
    end
  end
end

