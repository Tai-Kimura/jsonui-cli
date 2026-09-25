# frozen_string_literal: true

require 'json'
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

# lib/swiftui/views/modifier_order.json is the order this generator emits
# SwiftUI modifiers in, written out for SwiftJsonUI: its Dynamic runtime ties
# DynamicModifierHelper.standardOrder to a byte-for-byte copy of this file, and
# its CI compares the copy with this file at the pinned jsonui-cli ref. Nothing
# else keeps the file true, so this spec holds it to the constant the bag is
# emitted from and to code the converters actually generate.
RSpec.describe 'swiftui/views/modifier_order.json' do
  let(:doc) { JSON.parse(File.read(File.expand_path('../../../lib/swiftui/views/modifier_order.json', __dir__))) }

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emitted(component)
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter(component).convert.to_s
  end

  # Every modifier line, in emission order.
  def modifiers(code)
    code.lines.map(&:strip).grep(/\A\.[A-Za-z]/)
  end

  it 'lists the bag in the order ModifierBag emits it' do
    expect(doc['bag']).to eq(SjuiTools::SwiftUI::Views::ModifierBag::MODIFIER_ORDER.map(&:to_s))
  end

  it 'lists what is written after the bag: the identifier, then .disabled outside it' do
    expect(doc['after_bag']).to eq(%w[accessibility_identifier disabled])
    code = emitted({ 'type' => 'Image', 'id' => 'probe', 'srcName' => 'star', 'width' => 40, 'height' => 40,
                     'indexAbove' => 'x', 'enabled' => false })
    # :z_index and :disabled are the bag's last two registered keys here;
    # the two after them are not the bag's.
    expect(modifiers(code).last(4).map { |l| l[/\A\.[A-Za-z]+/] }).to eq(%w[.zIndex .disabled .accessibilityIdentifier .disabled])
    expect(compilable_view(code)).to compile_as_swift
  end

  it 'says :padding carries padding, then insets — and the generated code agrees' do
    expect(doc['shared_slots']).to eq('padding' => %w[padding insets])
    code = emitted({ 'type' => 'Image', 'id' => 'probe', 'srcName' => 'star', 'width' => 40, 'height' => 40,
                     'padding' => 4, 'insets' => [3] })
    lines = modifiers(code)
    padding = lines.index('.padding(4)')
    insets = lines.index('.padding(3)')
    frame = lines.index { |l| l.start_with?('.frame(width:') }
    expect([padding, insets, frame]).to all(be_a(Integer))
    expect(padding).to be < insets
    expect(insets).to be < frame
    expect(compilable_view(code)).to compile_as_swift
  end
end
