# frozen_string_literal: true

require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

# fontScaling / maxFontScale in sjui's codegen (ticket sjui-label-font-size-ignores-dynamic-type, ruling 2026-11-13):
# a text component that declares either carries `.fontScaling(_:maxFontScale:)`, which SwiftJsonUI reads from the
# environment for every font the component draws; one that declares neither carries nothing (the app default
# applies). Fonts the generator sets go through `.sjuiFont(FontSpec(...))` (the provider, at the rule's size).
RSpec.describe 'sjui fontScaling / maxFontScale' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emit(json)
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter({ 'id' => 'x' }.merge(json), 0).convert.to_s
  end

  TEXT = {
    'Label' => { 'text' => 'a', 'fontSize' => 13 },
    'Button' => { 'text' => 'a', 'fontSize' => 13 },
    'TextField' => { 'text' => '@{t}', 'fontSize' => 13 },
    'TextView' => { 'text' => '@{t}', 'fontSize' => 13 },
    'SelectBox' => { 'fontSize' => 13 },
    'Switch' => { 'text' => 'a', 'fontSize' => 13 },
    'CheckBox' => { 'text' => 'a', 'fontSize' => 13 },
    'Radio' => { 'text' => 'a', 'fontSize' => 13 },
    'IconLabel' => { 'text' => 'a', 'fontSize' => 13 }
  }.freeze

  it 'each text component carries the declaration it makes, and nothing without one' do
    TEXT.each do |type, base|
      plain = emit(base.merge('type' => type))
      expect(plain).not_to include('.fontScaling('), type
      expect(emit(base.merge('type' => type, 'fontScaling' => false)))
        .to include('.fontScaling(false, maxFontScale: nil)'), type
      expect(emit(base.merge('type' => type, 'maxFontScale' => 1.5)))
        .to include('.fontScaling(nil, maxFontScale: CGFloat(1.5))'), type
      expect(emit(base.merge('type' => type, 'fontScaling' => true, 'maxFontScale' => 2)))
        .to include('.fontScaling(true, maxFontScale: CGFloat(2))'), type
    end
  end

  it 'a component without text does not carry it' do
    expect(emit('type' => 'View', 'fontScaling' => false)).not_to include('.fontScaling(')
  end

  it 'the generator sets its fonts through sjuiFont, and a bound Label size adds no fixed font' do
    expect(emit('type' => 'TextField', 'text' => '@{t}', 'fontSize' => 13)).to include('.sjuiFont(FontSpec(')
    label = emit('type' => 'Label', 'text' => 'a', 'fontSize' => '@{size}')
    expect(label).not_to include('.font(.system(size:')
    expect(label).not_to include('resolveFont(')
  end

  it 'type-checks against the library declarations', :swift_compile do
    stubs = <<~SWIFT
      // SwiftJsonUI FontScaling.swift / FontSpec.swift (feature/font-scaling), the public declarations used.
      struct FontSpec {
          init(family: String? = nil, weight: Font.Weight? = nil, size: CGFloat? = nil, italic: Bool = false) {}
      }
      extension View {
          func sjuiFont(_ spec: FontSpec) -> some View { self }
          func fontScaling(_ scaling: Bool?, maxFontScale: CGFloat? = nil) -> some View { self }
      }
    SWIFT
    codes = [
      emit('type' => 'Label', 'text' => 'a', 'fontSize' => 13, 'fontScaling' => false),
      emit('type' => 'Label', 'text' => 'a', 'fontSize' => 13, 'maxFontScale' => 1.5)
    ]
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}", stubs: stubs)).to compile_as_swift
  end
end
