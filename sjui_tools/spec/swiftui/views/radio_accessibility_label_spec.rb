# frozen_string_literal: true

require 'swiftui/converter_factory'

# A radio's accessible name must be its own text, not its glyph's.
#
# `radio` is listed in CERTAIN_ACCESSIBILITY_ELEMENT_TYPES — the generator
# treats it as a LEAF element when it reasons about containers — but it is
# emitted as `HStack { Image(systemName:); Text }`, which is two accessibility
# elements. The identifier then lands on a container whose accessibility
# resolves to its first child, so the radio's label read as the SF Symbol's
# name: `circle`, or `largecircle.fill.circle` when selected.
#
# Found by the codegen conformance host running assertable fixtures for the
# first time: `Radio/text__static` and `Radio/text__binding` both expected
# `Conformance Text` and observed a value beginning `ci`. The dynamic face
# passed both, because it forms the element explicitly
# (`RadioConverter.swift`: `.accessibilityElement(children: .ignore)` then
# `.accessibilityLabel(text.dynamicLocalized())`). The two faces disagreed and
# the dynamic one was right.
#
# Consumer exposure when this was written: 77 `Radio` declarations carrying
# `text`/`label` across two consumer trees, every one of them announcing its
# glyph's name to a screen reader.
RSpec.describe 'Radio accessibility label' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all)  { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emit(component)
    out = SjuiTools::SwiftUI::ConverterFactory.new.create_converter(component).convert
    out.is_a?(Array) ? out.join("\n") : out.to_s
  end

  it 'names a statically-texted radio by its text' do
    code = emit({ 'type' => 'Radio', 'id' => 'target', 'text' => 'Conformance Text' })
    expect(code).to include('.accessibilityElement(children: .ignore)')
    expect(code).to include('.accessibilityLabel("Conformance Text")')
  end

  it 'names a bound-text radio by the binding, not the glyph' do
    code = emit({ 'type' => 'Radio', 'id' => 'target', 'text' => '@{boundText}' })
    expect(code).to include('.accessibilityElement(children: .ignore)')
    expect(code).to match(/\.accessibilityLabel\(\(?data\.boundText/)
  end

  it 'prefers `label` over `text`, as the rest of the converter does' do
    code = emit({ 'type' => 'Radio', 'id' => 'target',
                  'label' => 'From label', 'text' => 'From text' })
    expect(code).to include('.accessibilityLabel("From label")')
    expect(code).not_to include('.accessibilityLabel("From text")')
  end

  it 'leaves a text-less radio alone' do
    # Control. With nothing to name it by, forming the element would hide the
    # glyph without putting anything in its place — worse than the default.
    code = emit({ 'type' => 'Radio', 'id' => 'target' })
    expect(code).not_to include('.accessibilityElement(children: .ignore)')
    expect(code).not_to include('.accessibilityLabel(')
  end

  it 'still emits the glyph and the identifier' do
    # The gate above would also pass if the radio stopped rendering.
    code = emit({ 'type' => 'Radio', 'id' => 'target', 'text' => 'Pick me' })
    expect(code).to include('Image(systemName:')
    expect(code).to include('.accessibilityIdentifier("target")')
    expect(code).to include('Text("Pick me")')
  end
end
