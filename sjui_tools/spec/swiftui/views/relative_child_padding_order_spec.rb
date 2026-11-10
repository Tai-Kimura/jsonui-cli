# frozen_string_literal: true

require 'spec_helper'
require 'json'
require 'tmpdir'
require 'fileutils'
require 'swiftui/json_to_swiftui_converter'
require_relative '../../support/emitted_swift'

# A child of a relative container is drawn with the modifiers its own
# converter orders, as anywhere else (ticket
# sjui-relative-child-padding-background-outside-border).
#
# A child with both a padding and a background had the two taken out and put
# back after everything its converter drew, so they landed outside its
# corner radius, border, tap gesture and accessibility identifier: on a card
# with paddings 12, a background, a border and cornerRadius 12, the border
# hugged the content and the background spread square around it (client
# 26111100, iOS; android drew it right). Measured 2026-11-11 on 10 shapes,
# a relative child against the same View under a vertical parent: 8 drew
# differently in ios codegen, none in ios dynamic.
RSpec.describe SjuiTools::SwiftUI::JsonToSwiftUIConverter, 'a relative child with a padding and a background' do
  include EmittedSwift

  let(:converter) { described_class.new }
  let(:temp_dir) { File.realpath(Dir.mktmpdir('relative_child_padding_order')) }

  before { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }

  after do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
    FileUtils.rm_rf(temp_dir)
  end

  let(:card) do
    { 'type' => 'View', 'id' => 'card', 'width' => 160, 'height' => 'wrapContent', 'orientation' => 'horizontal',
      'paddings' => 12, 'background' => '#FFE8C0', 'borderWidth' => 2, 'borderColor' => '#AA6600', 'cornerRadius' => 12,
      'onClick' => '@{onTap}',
      'child' => [{ 'type' => 'View', 'id' => 'pic', 'width' => 40, 'height' => 40 }] }
  end

  def emit(parent)
    file = File.join(temp_dir, "l#{rand(1 << 30)}.json")
    File.write(file, JSON.generate(parent))
    code, _actions, _state, _children, funcs = converter.convert_json_to_view(file)
    ([code] + Array(funcs)).join("\n")
  end

  def relative(child)
    emit('type' => 'View', 'id' => 'frame', 'width' => 200, 'height' => 120,
         'child' => [child, { 'type' => 'View', 'id' => 'q', 'width' => 16, 'height' => 16, 'alignRight' => true }])
  end

  def vertical(child)
    emit('type' => 'View', 'id' => 'frame', 'width' => 200, 'height' => 120, 'orientation' => 'vertical', 'child' => [child])
  end

  # The card's own modifier lines, in order: from its HStack to its identifier.
  def card_modifiers(code)
    lines = code.lines.map(&:strip)
    last = lines.index('.accessibilityIdentifier("card")')
    first = lines[0..last].rindex { |l| l.start_with?('HStack') || l.start_with?('WeightedHStack') }
    lines[first..last].select { |l| l.start_with?('.') && !l.start_with?('.frame(width: 40') }
  end

  it 'pads and fills the card inside its corner radius, border and identifier' do
    mods = card_modifiers(relative(card))
    index = ->(prefix) { mods.index { |m| m.start_with?(prefix) } }
    expect(index['.padding(12)']).to be < index['.background(']
    expect(index['.background(']).to be < index['.cornerRadius(12)']
    expect(index['.cornerRadius(12)']).to be < index['.accessibilityIdentifier("card")']
    expect(mods.last).to eq('.accessibilityIdentifier("card")')
  end

  it 'draws the card with the modifiers it has under a vertical parent' do
    expect(card_modifiers(relative(card))).to eq(card_modifiers(vertical(card)))
  end

  { 'paddings [v, h]' => [12, 6], 'paddings [t, r, b, l]' => [12, 6, 4, 20] }.each do |label, paddings|
    it "keeps the order with #{label}" do
      child = card.merge('paddings' => paddings)
      expect(card_modifiers(relative(child))).to eq(card_modifiers(vertical(child)))
    end
  end

  it 'keeps the order inside a visibility wrapper' do
    child = card.merge('visibility' => '@{cardVis}')
    expect(card_modifiers(relative(child))).to eq(card_modifiers(vertical(child)))
  end

  it 'type-checks' do
    code = relative(card.merge('visibility' => '@{cardVis}'))
    stubs = <<~SWIFT
      struct RelativePositionConstraint {
          enum ConstraintType: String {
              case alignTop, alignBottom, alignLeft, alignRight, above, below, leftOf, rightOf, centerVertical, centerHorizontal
              case parentTop, parentBottom, parentLeft, parentRight, parentCenterHorizontal, parentCenterVertical, parentCenter
          }
          init(type: ConstraintType, targetId: String) {}
      }
      enum RelativeSizeMode { case matchParent, wrapContent, fixed(CGFloat) }
      struct RelativeChildConfig {
          init(id: String, view: AnyView, constraints: [RelativePositionConstraint] = [], margins: EdgeInsets = .init(),
               size: CGSize? = nil, widthMode: RelativeSizeMode = .wrapContent, heightMode: RelativeSizeMode = .wrapContent,
               isGone: Bool = false) {}
      }
      struct RelativePositionContainer: View {
          init(children: [RelativeChildConfig], alignment: Alignment = .topLeading, backgroundColor: Color? = nil,
               parentPadding: EdgeInsets = .init(), containerWidthMode: RelativeSizeMode = .wrapContent,
               containerHeightMode: RelativeSizeMode = .wrapContent) {}
          var body: some View { EmptyView() }
      }
      struct VisibilityWrapper<Content: View>: View {
          init(_ visibilityString: String?, @ViewBuilder content: () -> Content) {}
          var body: some View { EmptyView() }
      }
    SWIFT
    expect(compilable_view(code, data: ['var cardVis: String? = nil', 'var onTap: (() -> Void)? = nil'], stubs: stubs))
      .to compile_as_swift.with_imports('SwiftUI')
  end
end
