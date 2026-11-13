# frozen_string_literal: true

require 'swiftui/converter_factory'
require_relative '../../support/swift_compiler'

# The chosen radio reads "selected" to a screen reader.
#
# The state was only the glyph's picture (`largecircle.fill.circle` against
# `circle`): the single radio is one element with its label and no trait, and
# a group's option is its glyph and its label inside the `.contain` group, so
# VoiceOver read a chosen and an unchosen radio the same (ticket
# sjui-radio-checkbox-selected-state-not-read). Android (RadioButton(selected=))
# and web (a native input) carried the state already.
#
# Not chosen adds nothing — the accessibilitySelected attribute's `false` is
# the same. The group's option stays its glyph and its label (tests reach the
# option by its text), so the trait goes on the label; the dynamic face does
# the same (RadioConverter.swift).
RSpec.describe 'Radio selected state for a screen reader' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all)  { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emit(component)
    out = SjuiTools::SwiftUI::ConverterFactory.new.create_converter(component).convert
    out.is_a?(Array) ? out.join("\n") : out.to_s
  end

  def host(code, data:, state: '')
    <<~SWIFT
      #{EmittedSwift::LIBRARY_STUBS}
      struct TestData { #{data} }
      struct EmittedHost: View {
          @State var data = TestData()
          #{state}
          var body: some View {
      #{code.lines.map { |l| "        #{l}" }.join}
          }
      }
    SWIFT
  end

  it 'a single radio is selected exactly when its group holds its value' do
    code = emit({ 'type' => 'Radio', 'id' => 'r', 'text' => 'One', 'group' => 'g' })
    expect(code).to include('.accessibilityAddTraits((selectedG == "r") ? .isSelected : [])')
  end

  it 'a single radio with a value is selected by that value' do
    code = emit({ 'type' => 'Radio', 'id' => 'r', 'text' => 'One', 'group' => 'g', 'value' => 'v1' })
    expect(code).to include('.accessibilityAddTraits((selectedG == "v1") ? .isSelected : [])')
  end

  it 'a text-less single radio carries the state too (it has no element of its own; the glyph reads it)' do
    code = emit({ 'type' => 'Radio', 'id' => 'r', 'group' => 'g' })
    expect(code).to include('.accessibilityAddTraits((selectedG == "r") ? .isSelected : [])')
  end

  it "each written option's label is selected when the selection is that option" do
    code = emit({ 'type' => 'Radio', 'id' => 'r', 'items' => %w[a b], 'selectedValue' => '@{sel}' })
    expect(code).to include('.accessibilityAddTraits(data.sel == "a" ? .isSelected : [])')
    expect(code).to include('.accessibilityAddTraits(data.sel == "b" ? .isSelected : [])')
  end

  it "a bound list's option label is selected by the item" do
    code = emit({ 'type' => 'Radio', 'id' => 'r', 'items' => '@{options}', 'selectedValue' => '@{sel}' })
    expect(code).to include('.accessibilityAddTraits(data.sel == item ? .isSelected : [])')
  end

  it 'the group is still one element that contains its options' do
    # The option is not folded into one element: that would drop its label as
    # a static text, which the probes and tests reach it by.
    code = emit({ 'type' => 'Radio', 'id' => 'r', 'items' => %w[a b] })
    expect(code).to include('.accessibilityElement(children: .contain)')
    expect(code.scan('.accessibilityElement(').size).to eq(1)
  end

  it 'a single radio compiles with the trait', :swift_compile do
    skip("swiftc: #{SwiftCompiler.unavailable_reason}") if SwiftCompiler.unavailable_reason
    code = emit({ 'type' => 'Radio', 'id' => 'r', 'text' => 'One', 'group' => 'g' })
    expect(host(code, data: 'var unused = 0', state: '@State var selectedG: String = ""')).to compile_as_swift
  end

  it 'a bound group compiles with the trait', :swift_compile do
    skip("swiftc: #{SwiftCompiler.unavailable_reason}") if SwiftCompiler.unavailable_reason
    code = emit({ 'type' => 'Radio', 'id' => 'r', 'items' => '@{options}', 'selectedValue' => '@{sel}' })
    expect(host(code, data: 'var options: [String] = ["a"]; var sel: String = ""')).to compile_as_swift
  end
end
