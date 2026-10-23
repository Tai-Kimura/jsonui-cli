# frozen_string_literal: true

require 'swiftui/views/textfield_converter'
require 'swiftui/views/textview_converter'
require_relative '../../support/emitted_swift'
require_relative '../../support/swift_compiler'

# `autoFocus` (2.3.22, ticket rjui-textfield-autofocus-read-but-not-defined):
# declared on TextField and TextView for every face; on iOS the field's focus
# is set on appear, the next run loop turn.
RSpec.describe 'sjui autoFocus' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def field(extra)
    c = SjuiTools::SwiftUI::Views::TextFieldConverter.new({ 'type' => 'TextField', 'text' => '@{email}' }.merge(extra))
    [c.convert, c.state_variables]
  end

  def text_view(extra)
    c = SjuiTools::SwiftUI::Views::TextViewConverter.new({ 'type' => 'TextView', 'text' => '@{note}' }.merge(extra))
    [c.convert, c.state_variables]
  end

  it 'focuses a TextField with no id through a FocusState of its own' do
    code, states = field('autoFocus' => true)
    expect(states).to include('@FocusState private var field_0IsFocused: Bool')
    expect(code).to include('.focused($field_0IsFocused)')
    expect(code).to include('.onAppear { DispatchQueue.main.async { field_0IsFocused = true } }')
  end

  it "focuses a TextField with an id through the FocusState its data drives" do
    code, = field('id' => 'email_field', 'autoFocus' => true)
    expect(code).to include('.onAppear { DispatchQueue.main.async { emailFieldIsFocused = true } }')
  end

  it 'focuses a TextView with an id through data.<id>IsFocused' do
    code, = text_view('id' => 'note_view', 'autoFocus' => true)
    expect(code).to include('isFocused: $data.noteViewIsFocused')
    expect(code).to include('.onAppear { DispatchQueue.main.async { data.noteViewIsFocused = true } }')
  end

  it 'focuses a TextView with no id through a state of its own' do
    code, states = text_view('autoFocus' => true)
    expect(states).to include('@State private var textView_0IsFocused: Bool = false')
    expect(code).to include('isFocused: $textView_0IsFocused')
    expect(code).to include('.onAppear { DispatchQueue.main.async { textView_0IsFocused = true } }')
  end

  # The emitted modifiers in a view whose data is state (as a screen's is:
  # `data.<id>IsFocused = true` writes it) and whose own state is the
  # converter's state variables. TextViewWithPlaceholder is SwiftJsonUI's; its
  # stub takes the arguments this emits, in the library's order.
  def host(code, states, data)
    <<~SWIFT
      import SwiftUI
      #{EmittedSwift::LIBRARY_STUBS}
      struct TextViewWithPlaceholder: View {
          init(text: Binding<String>, isFocused: Binding<Bool>, accessibilityIdentifier: String? = nil) {}
          var body: some View { EmptyView() }
      }
      struct TestData { #{data.join('; ')} }
      struct EmittedHost: View {
          @State var data = TestData()
          #{states.join("\n    ")}
          var body: some View {
      #{code.lines.map { |l| "        #{l}" }.join}
          }
      }
    SWIFT
  end

  {
    'a TextField with no id' => -> { [*field('autoFocus' => true), ['var email = ""']] },
    'a TextField with an id' => -> { [*field('id' => 'email_field', 'autoFocus' => true), ['var email = ""', 'var emailFieldIsFocused = false']] },
    'a TextView with an id' => -> { [*text_view('id' => 'note_view', 'autoFocus' => true), ['var note = ""', 'var noteViewIsFocused = false']] },
    'a TextView with no id' => -> { [*text_view('autoFocus' => true), ['var note = ""']] }
  }.each do |name, build|
    it "#{name}: the emitted Swift compiles" do
      code, states, data = instance_exec(&build)
      expect(host(code, states, data)).to compile_as_swift
    end
  end

  it 'emits nothing for a field without it' do
    expect(field({}).first).not_to include('.onAppear')
    expect(text_view({}).first).not_to include('.onAppear')
  end
end
