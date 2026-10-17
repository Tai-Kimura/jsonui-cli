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
    converter = factory.create_converter(component, 0, nil, factory)
    out = converter.convert.to_s
    @declarations = Array(converter.state_variables)
    out
  end

  # The setter the control writes through: it stores the edit, then calls
  # the handler on the main queue's next turn — only the last edit of a
  # burst (the node's generation, a `@State` of the view), only if the
  # value is still the one it wrote, and only if the burst did not end where
  # it began; a value the field did not write restarts the burst
  # (UserEditBindingHelper).
  def setter_calling(binding, handler, generation = 'textEdit_0')
    "SwiftUI.Binding(get: { #{binding}.wrappedValue }, set: { newValue in " \
      "let edit = #{generation}; let before = #{binding}.wrappedValue; let changed = before != newValue; " \
      "#{binding}.wrappedValue = newValue; " \
      'if changed { if edit.start == nil || before != edit.last { edit.start = before }; edit.last = newValue; ' \
      'edit.number += 1; let number = edit.number; ' \
      'DispatchQueue.main.async { guard edit.number == number else { return }; let start = edit.start; edit.start = nil; ' \
      "guard #{binding}.wrappedValue == newValue, newValue != start else { return }; #{handler} } } })"
  end

  # The node's generation, declared in the view (named by position — a
  # component that was not stamped is at "0").
  def generation_declared(declarations, name = 'textEdit_0')
    expect(declarations).to include(
      SjuiTools::SwiftUI::Views::UserEditBindingHelper::GENERATION_CLASS,
      "@State private var #{name} = UserEditGeneration()"
    )
  end

  let(:handler) { 'data.onEmailChange?("email_field", newValue)' }

  describe 'TextField over a data binding' do
    let(:out) do
      declare('onEmailChange' => '(String, String) -> Void')
      emit('type' => 'TextField', 'id' => 'email_field', 'text' => '@{email}', 'onTextChange' => '@{onEmailChange}')
    end

    it 'hands the field a binding whose setter calls the handler' do
      expect(out).to include("TextField(\"\", text: #{setter_calling('$data.email', handler)})")
      generation_declared(@declarations)
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
      'let before = $data.code.wrappedValue; let changed = before != String(newValue.prefix(6)); ' \
      '$data.code.wrappedValue = newValue; ',
      'let start = edit.start; edit.start = nil; let newValue = String(newValue.prefix(6)); ' \
      'guard String($data.code.wrappedValue.prefix(6)) == newValue, newValue != start.map({ String($0.prefix(6)) }) ' \
      'else { return }; data.h?(newValue) } } })'
    )
    generation_declared(@declarations)
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
    # Two nodes: in a layout their positions differ; these were not stamped.
    local = emit('type' => 'TextField', 'id' => 'target', 'onTextChange' => '@{h}').gsub('textEdit_0', 'textEdit_1')
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
          #{SjuiTools::SwiftUI::Views::UserEditBindingHelper::GENERATION_CLASS}
          @State private var textEdit_0 = UserEditGeneration()
          @State private var textEdit_1 = UserEditGeneration()
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
  # in the shapes the deferred call has to get right, with the handler shape
  # most screens use, `data.x = newValue`. The program waits for the main
  # queue to empty (markers, not a fixed sleep), so a slow machine cannot
  # turn "not called yet" into "not called".
  #
  # race — a key event landing between two deferred calls:
  #   delete -> "strin" (A queued); next key event queued; delete -> "stri"
  #   (B queued). 1.9.35 ran A with its "strin", the write-back put the field
  #   back, and one delete was lost (final "stri", three deletes leave "str").
  # vm — a programmatic change while a call is queued: no call.
  # back — "x" -> "xy" -> "x" in one turn: no net change, no call (1.9.36
  #   called with "x"; Android compares with the data and does not).
  # twice — "" -> "a" -> "" -> "a" in one turn: one call (1.9.36 called
  #   twice: the first call's "a" matched the current value by chance).
  # vmMid — "string" -> "stringd", the view model writes "strin", then
  #   "string": a change from "strin", one call (review S17: 0 when the
  #   start stayed at the burst's first value).
  # twoA / twoB — two instances of the view, one edit each in one turn:
  #   one call each (review S13: a state shared by view type dropped A's).
  it 'a burst calls once, with the latest value, and only if it changed the value', :swift_compile do
    declare('onNoteTextChange' => '(String, String) -> Void')
    out = emit('type' => 'TextView', 'id' => 'note_text_field', 'text' => '@{noteText}',
               'onTextChange' => '@{onNoteTextChange}')
    expr = out.lines.map(&:strip).find { |l| l.start_with?('text: SwiftUI.Binding(') }
    expect(expr).not_to be_nil
    expr = expr.delete_prefix('text: ').delete_suffix(',')
    generation_declared(@declarations)
    program = <<~SWIFT
      import SwiftUI
      #{SjuiTools::SwiftUI::Views::UserEditBindingHelper::GENERATION_CLASS}
      struct TestData {
          var noteText = ""
          var onNoteTextChange: ((String, String) -> Void)?
      }
      final class Store { var data = TestData() }
      /// One instance of the generated view: its data, and its generation
      /// (a `@State` in the view; a stored instance here, outside SwiftUI).
      struct EmittedHost {
          @SwiftUI.Binding var data: TestData
          private let textEdit_0 = UserEditGeneration()
          var field: SwiftUI.Binding<String> { #{expr} }
      }
      /// Runs the main queue until it is empty: a marker queued behind
      /// everything, three times (a block may queue another).
      func settle() {
          for _ in 0..<3 {
              var done = false
              DispatchQueue.main.async { done = true }
              while !done { _ = RunLoop.main.run(mode: .default, before: Date().addingTimeInterval(0.01)) }
          }
      }
      /// A store with the write-back handler, recording its calls.
      final class Recorder {
          let store = Store()
          var calls: [String] = []
          var staleWrites = 0
          init(seed: String) {
              store.data.noteText = seed
              store.data.onNoteTextChange = { [unowned self] _, value in
                  self.calls.append(value)
                  if value != self.store.data.noteText { self.staleWrites += 1 }
                  self.store.data.noteText = value
              }
          }
          func host() -> EmittedHost {
              EmittedHost(data: SwiftUI.Binding(get: { self.store.data }, set: { self.store.data = $0 }))
          }
          var line: String { "final=\\(store.data.noteText) calls=\\(calls) stale=\\(staleWrites)" }
      }
      func scenario(_ name: String, seed: String, _ edits: (SwiftUI.Binding<String>, Store) -> Void) {
          let r = Recorder(seed: seed)
          let host = r.host()
          edits(host.field, r.store)
          settle()
          print("RESULT \\(name) \\(r.line)")
      }
      func delete(_ f: SwiftUI.Binding<String>) { f.wrappedValue = String(f.wrappedValue.dropLast()) }
      scenario("race", seed: "string") { f, _ in
          delete(f)
          DispatchQueue.main.async { delete(f) }
          delete(f)
      }
      scenario("vm", seed: "string") { f, store in
          delete(f)
          store.data.noteText = "from the view model"
      }
      scenario("back", seed: "x") { f, _ in
          f.wrappedValue = "xy"
          f.wrappedValue = "x"
      }
      scenario("twice", seed: "") { f, _ in
          f.wrappedValue = "a"
          f.wrappedValue = ""
          f.wrappedValue = "a"
      }
      scenario("typed", seed: "") { f, _ in
          f.wrappedValue = "a"
          settle()
          f.wrappedValue = "ab"
      }
      // S17 — the view model writes between two edits of one burst; the
      // last edit is a change from what the view model wrote, and calls.
      scenario("vmMid", seed: "string") { f, store in
          f.wrappedValue = "stringd"
          store.data.noteText = "strin"
          f.wrappedValue = "string"
      }
      // S13 — two instances of one view (two cells of one template, each
      // with its own data), each edited in the same turn: each calls.
      do {
          let a = Recorder(seed: "string"), b = Recorder(seed: "string")
          let hostA = a.host(), hostB = b.host()
          hostA.field.wrappedValue = "string1"
          hostB.field.wrappedValue = "string2"
          settle()
          print("RESULT twoA \\(a.line)")
          print("RESULT twoB \\(b.line)")
      }
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
      expect(ran.lines.grep(/^RESULT /).map(&:strip)).to eq([
        'RESULT race final=str calls=["str"] stale=0',
        'RESULT vm final=from the view model calls=[] stale=0',
        'RESULT back final=x calls=[] stale=0',
        'RESULT twice final=a calls=["a"] stale=0',
        'RESULT typed final=ab calls=["a", "ab"] stale=0',
        'RESULT vmMid final=string calls=["string"] stale=0',
        'RESULT twoA final=string1 calls=["string1"] stale=0',
        'RESULT twoB final=string2 calls=["string2"] stale=0'
      ])
    end
  end
end
