# frozen_string_literal: true

require 'swiftui/json_to_swiftui_converter'
require 'core/stage_failures'
require_relative '../support/emitted_swift'

# TextField and TextView keyboard and length attributes take a binding
# (attribute_definitions, 2.5.61). Before, a bound `input` drew
# `.keyboardType(.default)`, a bound `returnKeyType` `.submitLabel(.done)`,
# a bound `autocapitalizationType` nothing at all, and a bound `maxLength`
# wrote `newValue.count > @{limit}` into the Swift, which does not build.
# A bound enum now carries the same table the literal path reads, keyed by
# the declared spellings; a bound maxLength is an Int read on each edit.
RSpec.describe 'sjui: TextField / TextView keyboard and length attributes take a binding' do
  include EmittedSwift

  let(:converter) { SjuiTools::SwiftUI::JsonToSwiftUIConverter.new }
  let(:dir) { Dir.mktmpdir('text_input_traits') }

  before { JsonUI::StageFailures.clear! }
  after { FileUtils.rm_rf(dir) }

  def data_section
    [
      { 'name' => 'text', 'class' => 'String' }, { 'name' => 'keyboard', 'class' => 'String' },
      { 'name' => 'submit', 'class' => 'String' }, { 'name' => 'caps', 'class' => 'String' },
      { 'name' => 'correction', 'class' => 'String' }, { 'name' => 'limit', 'class' => 'Int' }
    ]
  end

  def convert(children)
    path = File.join(dir, 'probe.json')
    File.write(path, JSON.generate('type' => 'View', 'data' => data_section, 'child' => children))
    converter.convert_json_to_view(path).first.to_s
  end

  let(:field) do
    { 'type' => 'TextField', 'text' => '@{text}', 'input' => '@{keyboard}',
      'returnKeyType' => '@{submit}', 'autocapitalizationType' => '@{caps}',
      'autocorrectionType' => '@{correction}', 'maxLength' => '@{limit}' }
  end

  it 'reads each bound value at run time through the literal path\'s table' do
    code = convert([field])
    # `?? ""` / `?? 0` where the data section leaves the property Optional.
    key = ->(name) { "\\]\\[\\(data\\.#{name}( \\?\\? \"\")?\\)\\]" }
    expect(code).to include('.keyboardType((["default": UIKeyboardType.default,', '"number": .numberPad')
    expect(code).to match(/#{key.('keyboard')} \?\? \.default\)\)/)
    expect(code).to include('.submitLabel((["Done": SubmitLabel.done,', '"Next": .next')
    expect(code).to match(/#{key.('submit')} \?\? \.done\)\)/)
    expect(code).to include('.textInputAutocapitalization((["none": TextInputAutocapitalization.never,', '"words": .words')
    expect(code).to match(/#{key.('caps')}\)\)/)
    expect(code).to include('.autocorrectionDisabled((["default": false,', '"no": true')
    expect(code).to match(/#{key.('correction')} \?\? false\)\)/)
    expect(code).to match(/let limit = Int\(data\.limit( \?\? 0)?\)/)
    expect(code).to include('if limit > 0 && newValue.count > limit {',
                            'data.text = String(newValue.prefix(limit))')
    expect(code).not_to include('@{')
  end

  it 'leaves the literal forms as they were' do
    code = convert([{ 'type' => 'TextField', 'text' => '@{text}', 'input' => 'number', 'returnKeyType' => 'Next',
                      'autocapitalizationType' => 'words', 'autocorrectionType' => 'no', 'maxLength' => 8 }])
    expect(code).to include('.keyboardType(.numberPad)', '.submitLabel(.next)', '.textInputAutocapitalization(.words)',
                            '.autocorrectionDisabled(true)', 'if newValue.count > 8 {')
  end

  # 0 is no limit. A written 0 cut every edit to the empty string here;
  # Compose already skipped it.
  it 'treats a written maxLength of 0 as no limit' do
    code = convert([{ 'type' => 'TextField', 'text' => '@{text}', 'maxLength' => 0 }])
    expect(code).not_to include('newValue.count > 0', 'prefix(0)')
  end

  it 'reads a bound TextView input, keyboardType and returnKeyType' do
    code = convert([{ 'type' => 'TextView', 'text' => '@{text}', 'input' => '@{keyboard}' },
                    { 'type' => 'TextView', 'text' => '@{text}', 'keyboardType' => '@{keyboard}', 'returnKeyType' => '@{submit}' }])
    expect(code).to match(/\]\[\(data\.keyboard( \?\? "")?\)\] \?\? \.default\)\)/)
    expect(code).to include('"numberPad": .decimalPad', '"Next": .next')
    expect(code).to match(/\]\[\(data\.submit( \?\? "")?\)\] \?\? \.return\)\)/)
    expect(code).not_to include('@{')
  end

  # This machine's swiftc type-checks against the macOS SDK, which has
  # neither UIKeyboardType nor TextInputAutocapitalization. Their iOS
  # declarations, transcribed (UIKit UITextInputTraits.h; SwiftUI
  # View.keyboardType(_:) / textInputAutocapitalization(_:)), so the
  # dictionaries, the Optional and the Int are checked as iOS reads them.
  def ios_input_stubs
    <<~SWIFT
    #if os(macOS)
    enum UIKeyboardType: Int {
        case `default`, asciiCapable, numbersAndPunctuation, URL, numberPad, phonePad, namePhonePad,
             emailAddress, decimalPad, twitter, webSearch, asciiCapableNumberPad
    }
    struct TextInputAutocapitalization {
        static let never = TextInputAutocapitalization()
        static let words = TextInputAutocapitalization()
        static let sentences = TextInputAutocapitalization()
        static let characters = TextInputAutocapitalization()
    }
    extension View {
        func keyboardType(_ type: UIKeyboardType) -> some View { self }
        func textInputAutocapitalization(_ autocapitalization: TextInputAutocapitalization?) -> some View { self }
    }
      #endif
    SWIFT
  end

  # The bound TextField, type-checked over the data's declared types.
  it 'compiles' do
    code = convert([field])
    body = code.lines.map { |l| "        #{l}" }.join
    swift = <<~SWIFT
      #{EmittedSwift::LIBRARY_STUBS}
      #{ios_input_stubs}
      struct TestData {
          var text: String = ""
          var keyboard: String = ""
          var submit: String = ""
          var caps: String = ""
          var correction: String = ""
          var limit: Int = 0
      }
      struct EmittedHost: View {
          @Binding var data: TestData
          var body: some View {
      #{body}
          }
      }
    SWIFT
    expect(swift).to compile_as_swift.with_imports('SwiftUI')
  end
end
