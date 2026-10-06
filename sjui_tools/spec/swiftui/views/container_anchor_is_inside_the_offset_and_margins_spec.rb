# frozen_string_literal: true

require 'swiftui/views/view_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

# The 0.5pt anchor against the single-child merge goes inside the offset and
# the margins (the bag's accessibility_anchor slot), the box the conformance
# frame reads. A container's id box is the union of its anchor and its
# content. Written with the identifier, after the margins and the offset, the
# anchor sat at the margin's corner and before the offset: a 100-wide View
# with offsetX 5 and leftMargin 20 in a vertical stack read an id box 105 wide
# from the margin (ticket ios-container-id-box-starts-at-the-anchor-before-
# the-offset; SwiftJsonUI Dynamic's accessibilityAnchor stage, same place).
RSpec.describe 'sjui codegen: the accessibility anchor is inside the offset and the margins' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  ANCHOR_SPEC_ANCHOR = '.frame(width: 0.5, height: 0.5)'

  def emit(node)
    factory = SjuiTools::SwiftUI::ConverterFactory.new
    factory.create_converter(node, 1, nil, factory).convert.to_s
  end

  def at(code, text)
    i = code.index(text)
    raise "#{text} is not in\n#{code}" unless i

    i
  end

  ANCHOR_SPEC_CHILD = [{ 'type' => 'Label', 'text' => 'In' }].freeze
  ANCHOR_SPEC_BOX = { 'type' => 'View', 'orientation' => 'vertical', 'width' => 100, 'height' => 40, 'leftMargin' => 20,
          'topMargin' => 10, 'padding' => 8, 'offsetX' => 5, 'background' => '#FFDD00', 'child' => ANCHOR_SPEC_CHILD }.freeze

  it 'a container with an id: after the background, before the offset and the margins, once' do
    code = emit(ANCHOR_SPEC_BOX.merge('id' => 's_view'))
    expect(code.scan(ANCHOR_SPEC_ANCHOR).size).to eq(1)
    expect(at(code, ANCHOR_SPEC_ANCHOR)).to be > at(code, '.background(')
    expect(at(code, ANCHOR_SPEC_ANCHOR)).to be < at(code, '.offset(x: 5')
    expect(at(code, ANCHOR_SPEC_ANCHOR)).to be < at(code, '.padding(.leading, 20)')
    expect(at(code, '.accessibilityElement(children: .contain)')).to be > at(code, '.padding(.leading, 20)')
  end

  it 'a combined tap: before the offset and the margins, and before .combine, once' do
    code = emit(ANCHOR_SPEC_BOX.merge('id' => 't', 'onClick' => '@{tap}', JsonUIShared::TapAccessibility::SHAPE_KEY => 'combine'))
    expect(code.scan(ANCHOR_SPEC_ANCHOR).size).to eq(1)
    expect(at(code, ANCHOR_SPEC_ANCHOR)).to be < at(code, '.offset(x: 5')
    expect(at(code, ANCHOR_SPEC_ANCHOR)).to be < at(code, '.padding(.leading, 20)')
    expect(at(code, ANCHOR_SPEC_ANCHOR)).to be < at(code, '.accessibilityElement(children: .combine)')
  end

  # The other side of the hazard: two guaranteed children, no anchor.
  it 'a container with two children takes none (control)' do
    code = emit(ANCHOR_SPEC_BOX.merge('id' => 's_view', 'child' => ANCHOR_SPEC_CHILD + ANCHOR_SPEC_CHILD))
    expect(code).not_to include(ANCHOR_SPEC_ANCHOR)
    expect(code).to include('.accessibilityElement(children: .contain)')
  end

  it 'a container without an id takes none (control)' do
    expect(emit(ANCHOR_SPEC_BOX)).not_to include(ANCHOR_SPEC_ANCHOR)
  end

  it 'every case compiles' do
    codes = [ANCHOR_SPEC_BOX.merge('id' => 's_view'),
             ANCHOR_SPEC_BOX.merge('id' => 't', 'onClick' => '@{tap}', JsonUIShared::TapAccessibility::SHAPE_KEY => 'combine')].map { |n| emit(n) }
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}", data: ['var tap: (() -> Void)? = nil'])).to compile_as_swift
  end
end
