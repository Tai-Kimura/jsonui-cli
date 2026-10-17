# frozen_string_literal: true

require 'swiftui/views/base_view_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require 'swiftui/views/color_helper'
require_relative '../../support/emitted_swift'
require 'open3'
require 'tmpdir'

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
  # — and only if the value is still the one this edit wrote (a later edit
  # makes the call stale; UserEditBindingHelper).
  def setter_calling(binding, handler)
    "SwiftUI.Binding(get: { #{binding}.wrappedValue }, set: { newValue in " \
      "let changed = #{binding}.wrappedValue != newValue; #{binding}.wrappedValue = newValue; " \
      "if changed { DispatchQueue.main.async { guard #{binding}.wrappedValue == newValue else { return }; " \
      "#{handler} } } })"
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
      'if changed { DispatchQueue.main.async { let newValue = String(newValue.prefix(6)); ' \
      'guard String($data.code.wrappedValue.prefix(6)) == newValue else { return }; data.h?(newValue) } } })'
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
  # Run, not only type-checked: the emitted setter in a program that types
  # the way the race in ticket sjui-ontextchange-deferred-handler-replays-
  # stale-value needs — a key event landing between two deferred calls —
  # with the handler shape most screens use, `data.x = newValue`.
  #
  #   delete              -> "strin", call A queued
  #   (next key event queued here)
  #   delete              -> "stri",  call B queued
  #   queue: A, key, B
  #
  # 1.9.35 ran A with its own "strin": the write-back put the field back to
  # "strin", the next delete started from there and one delete was lost
  # (final "stri", where three deletes leave "str"). Now A and B find the
  # value moved on and drop; the key's own call writes the latest value.
  it 'a deferred call that a later edit overtook is dropped, so a write-back handler loses no edit', :swift_compile do
    declare('onNoteTextChange' => '(String, String) -> Void')
    out = emit('type' => 'TextView', 'id' => 'note_text_field', 'text' => '@{noteText}',
               'onTextChange' => '@{onNoteTextChange}')
    expr = out.lines.map(&:strip).find { |l| l.start_with?('text: SwiftUI.Binding(') }
    expect(expr).not_to be_nil
    expr = expr.delete_prefix('text: ').delete_suffix(',')
    program = <<~SWIFT
      import SwiftUI
      struct TestData {
          var noteText = "string"
          var onNoteTextChange: ((String, String) -> Void)?
      }
      final class Store { var data = TestData() }
      struct EmittedHost {
          @SwiftUI.Binding var data: TestData
          var field: SwiftUI.Binding<String> { #{expr} }
      }
      let store = Store()
      var calls: [String] = []
      var staleWrites = 0
      store.data.onNoteTextChange = { _, value in
          calls.append(value)
          if value != store.data.noteText { staleWrites += 1 }
          store.data.noteText = value
      }
      let host = EmittedHost(data: SwiftUI.Binding(get: { store.data }, set: { store.data = $0 }))
      func delete() { let f = host.field; f.wrappedValue = String(f.wrappedValue.dropLast()) }
      delete()
      DispatchQueue.main.async { delete() }
      delete()
      RunLoop.main.run(until: Date().addingTimeInterval(0.3))
      // A programmatic change while a call is queued: the call is stale too.
      delete()
      store.data.noteText = "from the view model"
      RunLoop.main.run(until: Date().addingTimeInterval(0.3))
      print("RESULT final=\\(store.data.noteText) calls=\\(calls) stale=\\(staleWrites)")
    SWIFT
    if (reason = SwiftCompiler.unavailable_reason)
      skip "#{reason}; this example runs where the SwiftUI SDK is present"
    end
    Dir.mktmpdir('sjui_otc_run') do |dir|
      src = File.join(dir, 'main.swift')
      bin = File.join(dir, 'main')
      File.write(src, program)
      sdk = `xcrun --show-sdk-path 2>/dev/null`.strip
      built, status = Open3.capture2e('swiftc', *(sdk.empty? ? [] : ['-sdk', sdk]), src, '-o', bin)
      expect(status).to be_success, built
      ran, status = Open3.capture2e(bin)
      expect(status).to be_success, ran
      expect(ran).to include('RESULT final=from the view model calls=["str"] stale=0')
    end
  end
end
