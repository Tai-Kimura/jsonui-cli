# frozen_string_literal: true

require 'swiftui/views/label_converter'

RSpec.describe SjuiTools::SwiftUI::Views::LabelConverter do
  # Disable validation for converter tests (tested separately)
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'with simple label' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => 'Hello World'
        }
      end

      it 'generates PartialAttributedText view' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('PartialAttributedText(')
        expect(code).to include('"Hello World"')
      end

      it 'generates compilable Swift code', :swift_compile do
        converter = described_class.new(component)
        code = converter.convert

        # Wrap in a valid SwiftUI view context
        full_code = <<~SWIFT
          struct TestView: View {
              var body: some View {
                  #{code}
              }
          }
        SWIFT

        expect(full_code).to compile_as_swift
      end
    end

    context 'with fontSize and fontColor' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => 'Styled Text',
          'fontSize' => 18,
          'fontColor' => '#FF0000'
        }
      end

      it 'includes fontSize parameter' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('fontSize: 18')
      end

      it 'includes fontColor parameter' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('fontColor:')
      end

      it 'generates compilable Swift code', :swift_compile do
        converter = described_class.new(component)
        code = converter.convert

        full_code = <<~SWIFT
          struct TestView: View {
              var body: some View {
                  #{code}
              }
          }
        SWIFT

        expect(full_code).to compile_as_swift
      end
    end

    context 'with textAlign' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => 'Centered',
          'textAlign' => 'center'
        }
      end

      it 'converts textAlign to SwiftUI alignment' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('textAlignment: .center')
      end
    end

    context 'with lines limit' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => 'Long text',
          'lines' => 2
        }
      end

      it 'adds lineLimit parameter' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('lineLimit: 2')
      end
    end

    context 'with lineBreakMode' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => 'Truncated text',
          'lineBreakMode' => 'Tail'
        }
      end

      it 'adds truncationMode modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.truncationMode(.tail)')
      end
    end

    context 'with underline and strikethrough' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => 'Decorated',
          'underline' => true,
          'strikethrough' => true
        }
      end

      it 'includes text decorations' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('underline: true')
        expect(code).to include('strikethrough: true')
      end
    end

    context 'with the styled (object) face' do
      it 'draws the line for a styled face that names a line style' do
        code = described_class.new(
          'type' => 'Label',
          'text' => 'Decorated',
          'underline' => { 'lineStyle' => 'Single', 'color' => '#FF0000' },
          'strikethrough' => { 'lineStyle' => 'Double' }
        ).convert

        expect(code).to include('underline: true')
        expect(code).to include('strikethrough: true')
      end

      # The object face's CONTENTS. Both faces used to emit the same bare
      # `underline: true`, so a styled declaration and a plain `true` were
      # byte-identical — the presence-only row in codegen_effect.json. The
      # library grew the receiving parameters in SwiftJsonUI 0fc5231.
      it 'carries lineStyle, colour and lineOffset into the decoration' do
        code = described_class.new(
          'type' => 'Label',
          'text' => 'Decorated',
          'underline' => { 'lineStyle' => 'Single', 'color' => '#FF0000', 'lineOffset' => 2 },
          'strikethrough' => { 'lineStyle' => 'Thick' }
        ).convert

        expect(code).to include('underlineDecoration: TextDecoration(lineStyle: .single,')
        expect(code).to include('lineOffset: 2)')
        expect(code).to include('strikethroughDecoration: TextDecoration(lineStyle: .thick)')
      end

      # `lineOffset` is declared on underline only.
      it 'does not invent a lineOffset for strikethrough' do
        code = described_class.new(
          'type' => 'Label', 'text' => 'x',
          'strikethrough' => { 'lineStyle' => 'Single', 'lineOffset' => 9 }
        ).convert

        expect(code).to include('strikethroughDecoration: TextDecoration(lineStyle: .single)')
      end

      it 'leaves the boolean face without a decoration' do
        code = described_class.new(
          'type' => 'Label', 'text' => 'x', 'underline' => true, 'strikethrough' => true
        ).convert

        expect(code).to include('underline: true')
        expect(code).not_to include('Decoration')
      end

      # `None` is the declared spelling for "no line" in the lineStyle enum.
      # Every read site tested the face for truthiness, and an object is
      # truthy, so this asked for the line it exists to suppress.
      it 'draws no line for lineStyle None' do
        code = described_class.new(
          'type' => 'Label',
          'text' => 'Plain',
          'underline' => { 'lineStyle' => 'None' },
          'strikethrough' => { 'lineStyle' => 'none' }
        ).convert

        expect(code).not_to include('underline: true')
        expect(code).not_to include('strikethrough: true')
      end
    end

    context 'with autoShrink' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => 'Auto shrink text',
          'autoShrink' => true,
          'minimumScaleFactor' => 0.7
        }
      end

      it 'adds minimumScaleFactor modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.minimumScaleFactor(0.7)')
      end
    end

    context 'with partialAttributes' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => 'Hello World',
          'partialAttributes' => [
            {
              'fontColor' => '#FF0000',
              'range' => [0, 5]
            }
          ]
        }
      end

      it 'includes partialAttributes array' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('partialAttributes:')
        expect(code).to include('PartialAttribute(')
        expect(code).to include('range: 0..<5')
      end

      it 'generates compilable Swift code', :swift_compile do
        converter = described_class.new(component)
        code = converter.convert

        full_code = <<~SWIFT
          struct TestView: View {
              var body: some View {
                  #{code}
              }
          }
        SWIFT

        expect(full_code).to compile_as_swift
      end
    end

    context 'with background and cornerRadius' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => 'Styled',
          'background' => '#007AFF',
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

    context 'with padding and margins' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => 'Spaced',
          'paddingTop' => 8,
          'paddingBottom' => 8,
          'topMargin' => 16
        }
      end

      it 'applies padding' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.padding(.top, 8)')
        expect(code).to include('.padding(.bottom, 8)')
      end
    end

    context 'with alpha/opacity' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => 'Transparent',
          'alpha' => 0.5
        }
      end

      it 'adds opacity modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.opacity(0.5)')
      end
    end

    context 'with hidden' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => 'Hidden',
          'hidden' => true
        }
      end

      it 'adds hidden modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.opacity(0).accessibilityHidden(true)')
      end
    end

    context 'with linkable' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => 'Visit https://example.com',
          'linkable' => true
        }
      end

      it 'adds linkable parameter' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('linkable: true')
      end
    end
  end

  describe 'font variants' do
    it 'handles bold font style' do
      component = { 'type' => 'Label', 'text' => 'Bold', 'font' => 'bold' }
      converter = described_class.new(component)
      code = converter.convert
      expect(code).to include('PartialAttributedText')
    end
  end

  describe 'text binding' do
    it 'handles binding expression' do
      component = { 'type' => 'Label', 'text' => '@{userName}' }
      converter = described_class.new(component)
      code = converter.convert
      expect(code).to include('data.userName')
    end
  end

  describe 'lines = 0' do
    it 'sets nil lineLimit for unlimited lines' do
      component = { 'type' => 'Label', 'text' => 'Unlimited', 'lines' => 0 }
      converter = described_class.new(component)
      code = converter.convert
      expect(code).to include('lineLimit: nil')
    end
  end

  describe 'lineBreakMode variations' do
    it 'handles Head truncation' do
      component = { 'type' => 'Label', 'text' => 'Text', 'lineBreakMode' => 'Head' }
      converter = described_class.new(component)
      code = converter.convert
      expect(code).to include('.truncationMode(.head)')
    end

    it 'handles Middle truncation' do
      component = { 'type' => 'Label', 'text' => 'Text', 'lineBreakMode' => 'Middle' }
      converter = described_class.new(component)
      code = converter.convert
      expect(code).to include('.truncationMode(.middle)')
    end
  end

  describe 'textAlign variations' do
    it 'handles left alignment' do
      component = { 'type' => 'Label', 'text' => 'Left', 'textAlign' => 'left' }
      converter = described_class.new(component)
      code = converter.convert
      expect(code).to include('textAlignment: .leading')
    end

    it 'handles right alignment' do
      component = { 'type' => 'Label', 'text' => 'Right', 'textAlign' => 'right' }
      converter = described_class.new(component)
      code = converter.convert
      expect(code).to include('textAlignment: .trailing')
    end
  end

  describe 'partialAttributes with underline object' do
    it 'handles underline style' do
      component = {
        'type' => 'Label',
        'text' => 'Underlined Text',
        'partialAttributes' => [
          {
            'underline' => { 'lineStyle' => 'Single', 'color' => '#FF0000' },
            'range' => [0, 10]
          }
        ]
      }
      converter = described_class.new(component)
      code = converter.convert
      expect(code).to include('PartialAttribute(')
      expect(code).to include('underline: true')
    end

    it 'draws no line for a partial whose lineStyle is None' do
      code = described_class.new(
        'type' => 'Label',
        'text' => 'Underlined Text',
        'partialAttributes' => [
          { 'underline' => { 'lineStyle' => 'None' }, 'range' => [0, 10] }
        ]
      ).convert

      expect(code).to include('PartialAttribute(')
      expect(code).not_to include('underline: true')
    end
  end

  describe 'partialAttributes with text range' do
    it 'handles text-based range' do
      component = {
        'type' => 'Label',
        'text' => 'Hello World',
        'partialAttributes' => [
          {
            'fontColor' => '#FF0000',
            'range' => { 'text' => 'Hello' }
          }
        ]
      }
      converter = described_class.new(component)
      code = converter.convert
      expect(code).to include('PartialAttribute(')
    end
  end

  describe 'complex component compilation', :swift_compile do
    it 'compiles label with all common attributes' do
      component = {
        'type' => 'Label',
        'text' => 'Complete Label',
        'fontSize' => 16,
        'fontColor' => '#333333',
        'textAlign' => 'center',
        'lines' => 2,
        'lineBreakMode' => 'Tail',
        'underline' => true,
        'background' => '#F5F5F5',
        'cornerRadius' => 4,
        'paddingTop' => 8,
        'paddingBottom' => 8,
        'paddingLeft' => 12,
        'paddingRight' => 12,
        'alpha' => 0.9
      }

      converter = described_class.new(component)
      code = converter.convert

      full_code = <<~SWIFT
        struct TestView: View {
            var body: some View {
                #{code}
            }
        }
      SWIFT

      expect(full_code).to compile_as_swift
    end

    # Both were read by nobody on the SwiftUI path: a label with a shadow
    # rendered flat, and highlightAttributes was dropped entirely.
    describe 'textShadow' do
      it 'maps the object form onto .shadow' do
        code = described_class.new({
          'type' => 'Label', 'text' => 'Hi',
          'textShadow' => { 'color' => '#333333', 'blur' => 3, 'offset' => [1, 2] }
        }).convert
        expect(code).to include('radius: 3, x: 1, y: 2')
      end

      it 'accepts the bare colour form the attribute also declares' do
        code = described_class.new(
          { 'type' => 'Label', 'text' => 'Hi', 'textShadow' => '#333333' }
        ).convert
        expect(code).to include('.shadow(color:')
      end

      it 'emits nothing when absent' do
        code = described_class.new({ 'type' => 'Label', 'text' => 'Hi' }).convert
        expect(code).not_to include('.shadow(')
      end
    end

    describe 'highlightAttributes / highlightColor' do
      it 'carries every declared key into TextHighlightAttributes' do
        code = described_class.new({
          'type' => 'Label', 'text' => 'Hi', 'fontSize' => 14, 'selected' => '@{isChosen}',
          'highlightAttributes' => {
            'font' => 'Helvetica', 'fontSize' => 20, 'fontColor' => '#FF0000',
            'lineHeightMultiple' => 1.5, 'textAlign' => 'Center'
          }
        }).convert

        expect(code).to include('fontFamily: "Helvetica"')
        expect(code).to include('fontSize: 20.0')
        expect(code).to include('lineHeightMultiple: 1.5')
        expect(code).to include('textAlignment: .center')
        expect(code).to include('isHighlighted: data.isChosen')
      end

      # UIKit: `UIFont(name:size:) ?? (name == "bold" ? boldSystemFont : ...)`
      it 'maps the literal font name "bold" to a weight, not a family' do
        code = described_class.new({
          'type' => 'Label', 'text' => 'Hi', 'selected' => true,
          'highlightAttributes' => { 'font' => 'bold' }
        }).convert

        expect(code).to include('fontWeight: .bold')
        expect(code).not_to include('fontFamily: "bold"')
      end

      # Argument labels must appear in the struct's declaration order or the
      # generated Swift will not compile.
      it 'emits the fields in TextHighlightAttributes declaration order' do
        code = described_class.new({
          'type' => 'Label', 'text' => 'Hi', 'selected' => true,
          'highlightAttributes' => {
            'font' => 'Helvetica', 'fontSize' => 20, 'fontColor' => '#FF0000',
            'lineHeightMultiple' => 1.5, 'textAlign' => 'Right'
          }
        }).convert
        call = code[/TextHighlightAttributes\((.*)\)/, 1]

        # Argument boundaries only — nested calls carry labels of their own
        # (`getColor(for:)`), which are not arguments of this initializer.
        expect(call.scan(/(?:\A|, )(\w+):/).flatten)
          .to eq(%w[fontFamily fontSize fontColor lineHeightMultiple textAlignment])
      end

      it 'drives the swap from selected rather than from a press' do
        code = described_class.new({
          'type' => 'Label', 'text' => 'Hi', 'selected' => true,
          'highlightAttributes' => { 'fontColor' => '#FF0000' }
        }).convert

        expect(code).to include('isHighlighted: true')
        expect(code).not_to include('.onLongPressGesture')
      end

      it 'treats an unselected label as showing its base styling' do
        code = described_class.new({
          'type' => 'Label', 'text' => 'Hi',
          'highlightAttributes' => { 'fontColor' => '#FF0000' }
        }).convert
        expect(code).to include('isHighlighted: false')
      end

      it 'falls back to highlightColor, which used to emit only a comment' do
        code = described_class.new({
          'type' => 'Label', 'text' => 'Hi', 'selected' => true, 'highlightColor' => '#00FF00'
        }).convert

        expect(code).to include('highlightAttributes: TextHighlightAttributes(fontColor:')
        expect(code).not_to include('// highlightColor')
      end

      # SJUILabel: `if !attr["highlightAttributes"].isEmpty ... else if highlightColor`
      it 'prefers highlightAttributes and falls through when it has no usable key' do
        both = described_class.new({
          'type' => 'Label', 'text' => 'Hi', 'selected' => true,
          'highlightAttributes' => { 'fontColor' => '#FF0000' }, 'highlightColor' => '#00FF00'
        }).convert
        expect(both).to include('"#FF0000"')
        expect(both).not_to include('"#00FF00"')

        empty = described_class.new({
          'type' => 'Label', 'text' => 'Hi', 'selected' => true,
          'highlightAttributes' => {}, 'highlightColor' => '#00FF00'
        }).convert
        expect(empty).to include('"#00FF00"')
      end

      it 'emits nothing when neither is present' do
        code = described_class.new({ 'type' => 'Label', 'text' => 'Hi' }).convert
        expect(code).not_to include('TextHighlightAttributes')
        expect(code).not_to include('isHighlighted:')
      end
    end

    # A String weight is only accepted by the convenience initializer, which
    # does not take partialAttributes; the combination used to generate
    # "cannot convert value of type 'String' to expected argument type
    # 'Font.Weight'".
    describe 'fontWeight alongside partialAttributes' do
      let(:partials) { [{ 'range' => [0, 1], 'fontColor' => '#FF0000' }] }

      it 'emits a Font.Weight when partialAttributes are present' do
        code = described_class.new({
          'type' => 'Label', 'text' => 'Hi', 'fontWeight' => 'semibold',
          'partialAttributes' => partials
        }).convert

        expect(code).to include('fontWeight: .semibold')
        expect(code).not_to include('fontWeight: "semibold"')
      end

      it 'also converts the font:"bold" spelling' do
        code = described_class.new({
          'type' => 'Label', 'text' => 'Hi', 'font' => 'bold', 'partialAttributes' => partials
        }).convert

        expect(code).to include('fontWeight: .bold')
        expect(code).not_to include('fontWeight: "bold"')
      end

      it 'keeps the string form when there are no partialAttributes' do
        code = described_class.new({
          'type' => 'Label', 'text' => 'Hi', 'fontWeight' => 'bold'
        }).convert
        expect(code).to include('fontWeight: "bold"')
      end

      it 'keeps the string form when partialAttributes is present but empty' do
        code = described_class.new({
          'type' => 'Label', 'text' => 'Hi', 'fontWeight' => 'bold', 'partialAttributes' => []
        }).convert
        expect(code).to include('fontWeight: "bold"')
      end
    end
  end
end
