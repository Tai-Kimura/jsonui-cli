# frozen_string_literal: true

require 'swiftui/views/base_view_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require 'swiftui/views/color_helper'
require_relative '../../support/emitted_swift'

# onTextChange is the USER'S stream (ticket
# sjui-ontextchange-fires-on-programmatic-data-change). The generated
# TextField / TextView used to observe the bound value —
#
#     .onChange(of: data.email) { oldValue, newValue in
#         guard oldValue != newValue else { return }
#         data.onEmailChange?("email_field", newValue)
#     }
#
# — which fires for every change of `data.email`, whoever made it: the view
# model's updateData, the test runner's initialState. kjui calls it only when
# the field's text differs from the data (the user typed), web from the
# input's onChange. The handler now runs from the setter of the binding the
# control writes through, and nothing observes the value.
#
# What a compiler cannot see is which writes reach the setter; that is the
# iOS arm (SwiftJsonUI OnTextChangeIsTheUsersStreamTests, and the consumer's
# initialState tests). Here: the wiring, and that it type-checks.
RSpec.describe 'sjui: onTextChange is called for the user\'s edit, not for a change of the value' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }
  after { SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {} }

  def declare(classes)
    SjuiTools::SwiftUI::Views::ColorHelper.data_definitions =
      classes.to_h { |name, klass| [name, { 'name' => name, 'class' => klass }] }
  end

  def emit(component)
    factory = SjuiTools::SwiftUI::ConverterFactory.new
    factory.create_converter(component, 0, nil, factory).convert.to_s
  end

  # The setter the control writes through: it stores the edit, then calls
  # the handler on the main queue's next turn — so a handler that narrows the
  # value and writes it back is a change of its own, which the field follows
  # (UserEditBindingHelper).
  def setter_calling(binding, handler)
    "SwiftUI.Binding(get: { #{binding}.wrappedValue }, set: { newValue in " \
      "let changed = #{binding}.wrappedValue != newValue; #{binding}.wrappedValue = newValue; " \
      "if changed { DispatchQueue.main.async { #{handler} } } })"
  end

  let(:handler) { 'data.onEmailChange?("email_field", newValue)' }

  describe 'TextField over a data binding' do
    let(:out) do
      declare('onEmailChange' => '(String, String) -> Void')
      emit('type' => 'TextField', 'id' => 'email_field', 'text' => '@{email}', 'onTextChange' => '@{onEmailChange}')
    end

    it 'hands the field a binding whose setter calls the handler' do
      expect(out).to include("TextField(\"\", text: #{setter_calling('$data.email', handler)})")
    end

    it 'does not observe the value' do
      expect(out).not_to include('.onChange(of: data.email)')
      expect(out).not_to include('oldValue')
      # The handler is called once, from the setter.
      expect(out.scan(handler).size).to eq(1)
    end
  end

  it 'a TextField with no text binding: the same, over its own @State' do
    declare('h' => '(String) -> Void')
    out = emit('type' => 'TextField', 'id' => 'target', 'onTextChange' => '@{h}')
    expect(out).to include("TextField(\"\", text: #{setter_calling('$targetText', 'data.h?(newValue)')})")
    expect(out).not_to include('.onChange(of: targetText)')
  end

  it 'a bound `secure`: both arms of the run-time pick get the setter' do
    declare('h' => '(String) -> Void')
    out = emit('type' => 'TextField', 'id' => 'p', 'text' => '@{pw}', 'secure' => '@{masked}', 'onTextChange' => '@{h}')
    setter = setter_calling('$data.pw', 'data.h?(newValue)')
    expect(out).to include("SecureField(\"\", text: #{setter})", "TextField(\"\", text: #{setter})")
    expect(out).not_to include('.onChange(of: data.pw)')
  end

  it 'the clear button writes through the setter (tapping it is the user\'s edit); the styled placeholder only reads' do
    declare('h' => '(String) -> Void')
    out = emit('type' => 'TextField', 'id' => 'q', 'text' => '@{query}', 'onTextChange' => '@{h}',
               'clearButtonMode' => 'always', 'hintColor' => '#FF0000', 'hint' => 'Search')
    expect(out).to include(".textFieldClearButton(mode: .always, text: #{setter_calling('$data.query', 'data.h?(newValue)')})")
    expect(out).to include('.styledPlaceholder("Search", text: $data.query, ')
  end

  it 'maxLength: the handler is handed what the field keeps, and an edit the clamp takes back is no edit' do
    declare('h' => '(String) -> Void')
    out = emit('type' => 'TextField', 'id' => 'code', 'text' => '@{code}', 'onTextChange' => '@{h}', 'maxLength' => 6)
    # The edit itself is stored as typed: the clamp below then changes the
    # value, which is what makes the field redraw at 6.
    expect(out).to include(
      'SwiftUI.Binding(get: { $data.code.wrappedValue }, set: { newValue in ' \
      'let changed = $data.code.wrappedValue != String(newValue.prefix(6)); $data.code.wrappedValue = newValue; ' \
      'if changed { DispatchQueue.main.async { let newValue = String(newValue.prefix(6)); data.h?(newValue) } } })'
    )
    # The value's own clamp (a programmatic write longer than the limit)
    # stays, and calls no handler.
    expect(out).to match(/\.onChange\(of: data\.code\) \{ _, newValue in\n\s*if newValue\.count > 6 \{\n\s*data\.code = String\(newValue\.prefix\(6\)\)\n\s*\}\n\s*\}/)
  end

  it 'a TextField without onTextChange keeps the plain binding' do
    out = emit('type' => 'TextField', 'id' => 'plain', 'text' => '@{plain}')
    expect(out).to include('TextField("", text: $data.plain)')
    expect(out).not_to include('SwiftUI.Binding(get:')
  end

  describe 'TextView' do
    it 'over a data binding: the editor\'s text: is the setter, and nothing observes the value' do
      declare('h' => '(String, String) -> Void')
      out = emit('type' => 'TextView', 'id' => 'memo', 'text' => '@{memo}', 'onTextChange' => '@{h}')
      expect(out).to include("text: #{setter_calling('$data.memo', 'data.h?("memo", newValue)')},")
      expect(out).not_to include('.onChange(of: data.memo)')
    end

    it 'over its own @State: the same' do
      declare('h' => '(String) -> Void')
      out = emit('type' => 'TextView', 'id' => 'note', 'onTextChange' => '@{h}')
      expect(out).to include("text: #{setter_calling('$noteText', 'data.h?(newValue)')},")
      expect(out).not_to include('.onChange(of: noteText)')
    end

    it 'without onTextChange keeps the plain binding' do
      out = emit('type' => 'TextView', 'id' => 'plain', 'text' => '@{plain}')
      expect(out).to include('text: $data.plain,')
    end
  end

  # The setter form inside a real `@SwiftUI.Binding var data` view, as the
  # generated view declares it — a fragment in EmittedSwift#compilable_view
  # has no `$data`. TextViewWithPlaceholder is the library's; the field is
  # SwiftUI's own, so it is the one handed to the compiler.
  it 'type-checks in a view whose data is a binding, over data and over @State', :swift_compile do
    declare('onEmailChange' => '(String, String) -> Void', 'h' => '(String) -> Void')
    bound = emit('type' => 'TextField', 'id' => 'email_field', 'text' => '@{email}',
                 'onTextChange' => '@{onEmailChange}', 'maxLength' => 6)
    local = emit('type' => 'TextField', 'id' => 'target', 'onTextChange' => '@{h}')
    field = ->(code) { code.lines.first.strip }
    source = <<~SWIFT
      struct TestData {
          var email: String = ""
          var onEmailChange: ((String, String) -> Void)?
          var h: ((String) -> Void)?
      }
      struct EmittedHost: View {
          @SwiftUI.Binding var data: TestData
          @State private var targetText: String = ""
          var body: some View {
              VStack {
                  #{field.call(bound)}
                  #{field.call(local)}
              }
          }
      }
    SWIFT
    expect(source).to include('SwiftUI.Binding(get: { $data.email.wrappedValue }', 'SwiftUI.Binding(get: { $targetText.wrappedValue }')
    expect(source).to compile_as_swift
  end
end
