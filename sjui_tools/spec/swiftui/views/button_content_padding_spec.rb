# frozen_string_literal: true

require 'swiftui/views/button_converter'
require_relative '../../support/emitted_swift'

# A Button's padding is its content padding. StateAwareButtonView pads its
# label inside its background and border (`padding:`), as KotlinJsonUI's
# contentPadding does. Until jsonui-cli 1.9.14 sjui entered its per-edge
# branch only on leftPadding / rightPadding / paddingTop / paddingBottom.
# A Button with the canonical paddingLeft / paddingRight alone emitted no
# padding, and a consumer's label ran to its border (ticket
# sjui-button-drops-padding-left-right). `padding`, paddingStart /
# paddingEnd and topPadding / bottomPadding were never read. A four-value
# `paddings` put its right value on the leading edge, where SwiftJsonUI
# Dynamic (edgeInsetsFromArray) and Compose read [top, right, bottom, left].
#
# The drawn arm is ButtonPaddingProbeUITests in SwiftJsonUI's ConformanceHost.
# It checks that each wrapContent Button grows by its padding against an
# unpadded control. Measured 2026-10-04 (iOS 26.5, Xcode 26.6):
# - v1.9.13: +0 for paddingLeft / Right 22, `padding` 10 and paddingStart /
#   End; +4 of 7 for topPadding 3 with paddingBottom 4.
# - This tree: every Button grows by its padding on the generated half.
# - Dynamic: the same, before this change too.
RSpec.describe SjuiTools::SwiftUI::Views::ButtonConverter do
  include EmittedSwift

  def insets(extra)
    node = { 'type' => 'Button', 'id' => 'b', 'text' => 'Go' }.merge(extra)
    described_class.new(node).convert.to_s.lines.map(&:strip).grep(/\Apadding: EdgeInsets/)
  end

  def edge_insets(top, leading, bottom, trailing)
    ["padding: EdgeInsets(top: #{top}, leading: #{leading}, bottom: #{bottom}, trailing: #{trailing}),"]
  end

  it 'paddingLeft / paddingRight alone (the ticket\'s shape)' do
    expect(insets('paddingLeft' => 22, 'paddingRight' => 22)).to eq(edge_insets(0, 22, 0, 22))
  end

  it 'the declared aliases, as before' do
    expect(insets('leftPadding' => 22, 'rightPadding' => 22)).to eq(edge_insets(0, 22, 0, 22))
    expect(insets('topPadding' => 3, 'bottomPadding' => 4)).to eq(edge_insets(3, 0, 4, 0))
  end

  it 'paddingStart / paddingEnd, before paddingLeft / paddingRight' do
    expect(insets('paddingStart' => 5, 'paddingLeft' => 9, 'paddingEnd' => 6, 'paddingRight' => 9)).to eq(edge_insets(0, 5, 0, 6))
  end

  it '`padding` and `paddings`: one value, [vertical, horizontal], [top, right, bottom, left]' do
    expect(insets('padding' => 10)).to eq(edge_insets(10, 10, 10, 10))
    expect(insets('paddings' => [4, 8])).to eq(edge_insets(4, 8, 4, 8))
    expect(insets('paddings' => [1, 2, 3, 4])).to eq(edge_insets(1, 4, 3, 2))
  end

  it 'a fractional value as declared, and a bound edge from the data' do
    expect(insets('paddingLeft' => 22.5)).to eq(edge_insets(0, 22.5, 0, 0))
    expect(insets('paddingLeft' => '@{pad}').first).to include('leading: CGFloat(data.pad ?? 0)')
  end

  it 'no padding declared: no padding argument (control)' do
    expect(insets({})).to eq([])
  end

  # StateAwareButtonView's initializer, transcribed from SwiftJsonUI 10.29.5
  # (Classes/SwiftUI/Components/StateAwareButtonView.swift): only the
  # labels these emits pass, in the library's order. A transcription, not a
  # compile against the library.
  it 'type-checks the padding argument', :swift_compile do
    stub = <<~SWIFT
      struct StateAwareButtonView: View {
          init(text: String, action: @escaping () -> Void, padding: EdgeInsets? = nil, isEnabled: Bool = true) {}
          var body: some View { EmptyView() }
      }
    SWIFT
    codes = [{ 'paddingLeft' => 22, 'paddingRight' => 22 }, { 'padding' => 10 }, { 'paddings' => [1, 2, 3, 4] },
             { 'paddingStart' => 5, 'paddingEnd' => 6 }, { 'paddingLeft' => 22.5 }].map do |extra|
      described_class.new({ 'type' => 'Button', 'text' => 'Go' }.merge(extra)).convert
    end
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}", stubs: stub)).to compile_as_swift
  end
end
