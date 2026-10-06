# frozen_string_literal: true

require 'swiftui/views/view_converter'
require 'swiftui/views/safeareaview_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

# An empty View (no children) is drawn as the SwiftJsonUI Dynamic runtime
# draws it — DynamicViewContainer.emptyContent:
#
#   background (no gradient)                     -> Rectangle / PressedFill
#   an axis sized and not 0, a weight, a gradient -> Color.clear
#   a margin                                      -> Color.clear, 0 x 0
#   otherwise                                     -> EmptyView (0 x 0)
#
# and an empty SafeAreaView is EmptyView whatever it declares
# (DynamicSafeAreaViewContainer). Until jsonui-cli 1.9.18 codegen made a
# Color.clear for any width / height KEY — `"width": "wrapContent"` and
# `"width": 0` included — and Color.clear takes all the space it is offered:
# measured on iOS 26.5, an empty `wrapContent` View with margins drew
# 370 x 314.3 where Dynamic drew nothing and Android 0 (ticket sjui-codegen-
# an-empty-view-fills-the-offered-space-and-its-id-box-includes-the-margin).
# A gradient-only empty View went the other way: EmptyView here, painted by
# Dynamic.
#
# The background row is unchanged (Dynamic fills the same way; a separate
# ruling). So is a View with one axis sized and the other wrapContent: Dynamic
# makes it Color.clear too.
RSpec.describe 'sjui codegen: an empty View draws what Dynamic draws' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emit(node)
    factory = SjuiTools::SwiftUI::ConverterFactory.new
    factory.create_converter(node, 0, nil, factory).convert.to_s
  end

  # The first line is the base view the converter chose.
  def base(node) = emit(node).lines.first.strip

  CASES = {
    # EmptyView: nothing gives it a size, so it is 0 x 0.
    'nothing declared' => [{}, 'EmptyView()'],
    'width wrapContent' => [{ 'width' => 'wrapContent' }, 'EmptyView()'],
    'both wrapContent, margins 0' => [{ 'width' => 'wrapContent', 'height' => 'wrapContent', 'topMargin' => 0, 'leftMargin' => 0 }, 'EmptyView()'],
    'width 0' => [{ 'width' => 0 }, 'EmptyView()'],
    'height "0"' => [{ 'height' => '0' }, 'EmptyView()'],
    'weight 0' => [{ 'weight' => 0 }, 'EmptyView()'],
    # Color.clear: a spacer.
    'width 8' => [{ 'width' => 8 }, 'Color.clear'],
    'height matchParent' => [{ 'height' => 'matchParent' }, 'Color.clear'],
    'a bound width' => [{ 'width' => '@{w}' }, 'Color.clear'],
    'weight 1, nothing sized' => [{ 'weight' => 1 }, 'Color.clear'],
    'widthWeight 1' => [{ 'widthWeight' => 1 }, 'Color.clear'],
    'a gradient only' => [{ 'gradient' => ['#FF0000', '#0000FF'] }, 'Color.clear'],
    # A margin: a box of 0 that the margin pads. EmptyView took its margin
    # with it on iOS, and the next child sat 12pt too high (ticket ios-an-
    # empty-views-margin-vanishes-with-it; user ruling 2026-10-07: the margin
    # stays, as on Android and web).
    'both wrapContent, with margins' => [{ 'width' => 'wrapContent', 'height' => 'wrapContent', 'topMargin' => 12, 'leftMargin' => 16 }, 'Color.clear'],
    'width 0, topMargin 12' => [{ 'width' => 0, 'height' => 0, 'topMargin' => 12 }, 'Color.clear'],
    'a bound margin' => [{ 'topMargin' => '@{m}' }, 'Color.clear'],
    'margins [0]' => [{ 'margins' => [0] }, 'EmptyView()'],
    'margins [4]' => [{ 'margins' => [4] }, 'Color.clear'],
    # Unchanged: the background row.
    'a background, wrapContent' => [{ 'background' => '#FF0000', 'width' => 'wrapContent' }, 'Rectangle()']
  }.freeze

  CASES.each do |label, (attrs, expected)|
    it "#{label} -> #{expected}" do
      expect(base({ 'type' => 'View' }.merge(attrs))).to eq(expected)
    end
  end

  it 'an empty View with a margin is sized 0, and the margin pads it' do
    out = emit({ 'type' => 'View', 'width' => 'wrapContent', 'height' => 'wrapContent', 'topMargin' => 12 })
    expect(out.lines[1].strip).to eq('.frame(width: 0, height: 0)')
    expect(out).to include('.padding(.top, 12)')
  end

  it 'an empty SafeAreaView is EmptyView whatever it declares' do
    expect(base({ 'type' => 'SafeAreaView', 'width' => 100, 'height' => 50 })).to eq('EmptyView()')
    expect(base({ 'type' => 'SafeAreaView', 'background' => '#FF0000' })).to eq('EmptyView()')
  end

  it 'a View with children is not touched (control)' do
    out = emit({ 'type' => 'View', 'width' => 'wrapContent', 'child' => [{ 'type' => 'Label', 'text' => 'a' }] })
    expect(out).not_to include('EmptyView()')
    expect(out).not_to start_with('Color.clear')
  end

  it 'every case compiles' do
    nodes = CASES.values.map { |(attrs, _)| { 'type' => 'View' }.merge(attrs) } +
            [{ 'type' => 'SafeAreaView', 'width' => 100 }, { 'type' => 'SafeAreaView', 'background' => '#FF0000' }]
    codes = nodes.map { |n| emit(n) }
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}", data: ['var w: CGFloat = 10', 'var m: CGFloat = 4'])).to compile_as_swift
  end
end
