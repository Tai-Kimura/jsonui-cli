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
    'both wrapContent, with margins' => [{ 'width' => 'wrapContent', 'height' => 'wrapContent', 'topMargin' => 12, 'leftMargin' => 16 }, 'EmptyView()'],
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
    # Unchanged: the background row.
    'a background, wrapContent' => [{ 'background' => '#FF0000', 'width' => 'wrapContent' }, 'Rectangle()']
  }.freeze

  CASES.each do |label, (attrs, expected)|
    it "#{label} -> #{expected}" do
      expect(base({ 'type' => 'View' }.merge(attrs))).to eq(expected)
    end
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
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}", data: ['var w: CGFloat = 10'])).to compile_as_swift
  end
end
