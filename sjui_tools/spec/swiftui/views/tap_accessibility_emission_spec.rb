# frozen_string_literal: true

require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'
require 'core/tap_accessibility'
require 'json'

# What sjui emits for each tap shape, driven by shared/core's vectors: one
# `.accessibilityAddTraits(.isButton)` per button or combine, one
# `.accessibilityElement(children: .combine)` per combine, and no `.contain`
# on a combined tappable (its identifier lands on the one element). Measured
# on a simulator (XCUITest elementType, 2026-09-25): the emitted View was
# `other`, the Image `image`; `.combine` + `.isButton` is a `button`.
RSpec.describe 'sjui tap accessibility emission' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  include EmittedSwift

  # The emitted modifiers type-check as SwiftUI, around the view each shape is
  # emitted on (an Image child keeps the fragment free of library types).
  {
    'a leaf Image becomes a button' => { 'type' => 'Image', 'id' => 't', 'src' => 'icon', 'onClick' => '@{onOpen}' },
    'a View holding an Image becomes one button' => {
      'type' => 'View', 'id' => 't', 'onClick' => '@{onOpen}',
      'child' => [{ 'type' => 'Image', 'id' => 'i', 'src' => 'icon' }]
    }
  }.each do |name, layout|
    it "#{name}, and the emitted Swift compiles" do
      JsonUIShared::TapAccessibility.annotate!(layout)
      code = SjuiTools::SwiftUI::ConverterFactory.new.create_converter(layout).convert
      expect(code).to include('.accessibilityAddTraits(.isButton)')
      expect(compilable_view(code, data: ['var onOpen: (() -> Void)? = nil'])).to compile_as_swift
    end
  end

  # With one accessible child, `.combine` took the child's identifier away
  # (XCUITest: the child's id found 0 times); the id path's anchor, placed
  # BEFORE `.combine`, keeps it (found once). Two children need no anchor.
  it 'a combined tap with one child carries the anchor before .combine' do
    layout = { 'type' => 'View', 'id' => 't', 'onClick' => '@{onOpen}',
               'child' => [{ 'type' => 'Label', 'id' => 'l', 'text' => 'x' }] }
    JsonUIShared::TapAccessibility.annotate!(layout)
    code = SjuiTools::SwiftUI::ConverterFactory.new.create_converter(layout).convert
    anchor = code.index('.accessibilityElement(children: .ignore)')
    expect(anchor).not_to be_nil
    expect(anchor).to be < code.index('.accessibilityElement(children: .combine)')
  end

  # An id-less combined tap took its children's identifiers as its own
  # (XCUITest, iOS 26.5 and 18.6, 2026-09-25): one child's id was found twice
  # — on the button and on the child — and two children's were joined
  # ("a-b") on the button. With an explicit empty identifier after `.combine`
  # every id is found exactly once and the button stays one element; a
  # container with an id gets that id on the button instead, so no empty one.
  {
    'one child with an id' => [{ 'type' => 'Label', 'id' => 'l', 'text' => 'x' }],
    'one child without an id' => [{ 'type' => 'Label', 'text' => 'x' }],
    'two children' => [{ 'type' => 'Label', 'id' => 'l', 'text' => 'x' }, { 'type' => 'Label', 'id' => 'm', 'text' => 'y' }]
  }.each do |name, children|
    it "an id-less combined tap (#{name}) keeps its own empty identifier, and compiles" do
      layout = { 'type' => 'View', 'onClick' => '@{onOpen}', 'child' => children }
      JsonUIShared::TapAccessibility.annotate!(layout)
      code = SjuiTools::SwiftUI::ConverterFactory.new.create_converter(layout).convert
      combine = code.index('.accessibilityElement(children: .combine)')
      empty = code.index('.accessibilityIdentifier("")')
      expect(combine).not_to be_nil
      expect(empty).not_to be_nil
      expect(empty).to be > combine
      expect(code.scan('.accessibilityIdentifier("")').size).to eq(1)
      expect(compilable_view(code, data: ['var onOpen: (() -> Void)? = nil'])).to compile_as_swift
    end

    it "a combined tap with its own id (#{name}) carries that id, not an empty one" do
      layout = { 'type' => 'View', 'id' => 't', 'onClick' => '@{onOpen}', 'child' => children }
      JsonUIShared::TapAccessibility.annotate!(layout)
      code = SjuiTools::SwiftUI::ConverterFactory.new.create_converter(layout).convert
      expect(code).not_to include('.accessibilityIdentifier("")')
      expect(code.index('.accessibilityIdentifier("t")')).to be > code.index('.accessibilityElement(children: .combine)')
    end
  end

  it 'a combined tap with two children carries no anchor' do
    layout = { 'type' => 'View', 'id' => 't', 'onClick' => '@{onOpen}',
               'child' => [{ 'type' => 'Label', 'id' => 'l', 'text' => 'x' },
                           { 'type' => 'Label', 'id' => 'm', 'text' => 'y' }] }
    JsonUIShared::TapAccessibility.annotate!(layout)
    code = SjuiTools::SwiftUI::ConverterFactory.new.create_converter(layout).convert
    expect(code).to include('.accessibilityElement(children: .combine)')
    expect(code).not_to include('.accessibilityElement(children: .ignore)')
  end

  # sjui-label-drops-a-selector-onclick-tap: a Label reads the onclick
  # selector the way every converter does (base's register_click_lines).
  it 'a Label taps through the onclick selector' do
    layout = { 'type' => 'Label', 'id' => 't', 'text' => 'Open', 'onclick' => 'open' }
    JsonUIShared::TapAccessibility.annotate!(layout)
    code = SjuiTools::SwiftUI::ConverterFactory.new.create_converter(layout).convert
    expect(code).to include('.onTapGesture {')
    expect(code).to include('data.open?()')
  end

  # An empty or blank handler names no method (TapAccessibility.handler?): no
  # tap, and the Swift compiles. They emitted `.onTapGesture { data.?() }` —
  # not Swift (ticket kjui-empty-onclick-emits-invalid-kotlin, all three
  # codegens). A blank element of an array is dropped from the calls; a blank
  # onClick leaves the tap to onclick.
  image = { 'type' => 'Image', 'id' => 'i', 'src' => 'icon' }
  {
    '"onClick": ""' => [{ 'onClick' => '' }, false],
    '"onClick": "   "' => [{ 'onClick' => '   ' }, false],
    '"onClick": "@{}"' => [{ 'onClick' => '@{}' }, false],
    '"onclick": ""' => [{ 'onclick' => '' }, false],
    '"onclick": "   "' => [{ 'onclick' => '   ' }, false],
    '"onclick": []' => [{ 'onclick' => [] }, false],
    '"onclick": ["", " "]' => [{ 'onclick' => ['', ' '] }, false],
    '"onclick": ["", "onOpen"]' => [{ 'onclick' => ['', 'onOpen'] }, true],
    '"onClick": "", "onclick": "onOpen"' => [{ 'onClick' => '', 'onclick' => 'onOpen' }, true]
  }.each do |name, (handler, taps)|
    it "#{name} #{taps ? 'taps onOpen once' : 'is no tap'}, and the emitted Swift compiles" do
      layout = { 'type' => 'View', 'id' => 't', 'child' => [image.dup] }.merge(handler)
      JsonUIShared::TapAccessibility.annotate!(layout)
      code = SjuiTools::SwiftUI::ConverterFactory.new.create_converter(layout).convert
      expect(code.scan('.onTapGesture').size).to eq(taps ? 1 : 0)
      expect(code.scan(/data\.\w+\?\(\)/)).to eq(taps ? ['data.onOpen?()'] : [])
      expect(compilable_view(code, data: ['var onOpen: (() -> Void)? = nil'])).to compile_as_swift
    end
  end

  vectors_path = File.expand_path('../../../../shared/core/tap_accessibility_vectors.json', __dir__)
  next unless File.exist?(vectors_path)

  # A tap exactly where the rule reads a handler (TapAccessibility.handler?
  # on either spelling), on every vector: a Button's tap is its action and a
  # statically disabled view gets none, as register_click_lines says.
  it 'emits a tap exactly where the rule reads a handler' do
    checked = 0
    JSON.parse(File.read(vectors_path))['cases'].each do |vector|
      layout = JSON.parse(JSON.generate(vector['layout']))
      want = 0
      JsonUIShared::TapAccessibility.walk(layout) do |node|
        next if node['type'] == 'Button' || node['enabled'] == false

        checked += 1 if JsonUIShared::TapAccessibility::TAP_KEYS.any? { |key| node.key?(key) }
        want += 1 if JsonUIShared::TapAccessibility::TAP_KEYS.any? { |key| JsonUIShared::TapAccessibility.handler?(node[key]) }
      end
      JsonUIShared::TapAccessibility.annotate!(layout)
      code = SjuiTools::SwiftUI::ConverterFactory.new.create_converter(layout).convert
      expect(code.scan('.onTapGesture').size).to eq(want), "#{vector['name']}:\n#{code}"
    end
    expect(checked).to be >= 12
  end

  JSON.parse(File.read(vectors_path))['cases'].each do |vector|
    it vector['name'] do
      layout = JSON.parse(JSON.generate(vector['layout']))
      JsonUIShared::TapAccessibility.annotate!(layout)
      code = SjuiTools::SwiftUI::ConverterFactory.new.create_converter(layout).convert
      shapes = vector['shapes'].values
      expect(code.scan('.accessibilityAddTraits(.isButton)').size).to eq(shapes.count { |s| %w[button combine].include?(s) })
      expect(code.scan('.accessibilityElement(children: .combine)').size).to eq(shapes.count('combine'))
      root = vector['shapes'][layout['id']]
      expect(code).not_to include('.accessibilityElement(children: .contain)') if root == 'combine'
    end
  end
end
