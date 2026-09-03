# frozen_string_literal: true

require 'json'
require 'compose/components/collection_component'
require 'compose/helpers/modifier_builder'

# Ruling (2026-09-03): a flow Collection with `lazy` in effect scrolls
# vertically inside its own bounds; `lazy: "none"` only wraps and the parent
# must scroll. sjui's default-lazy flow arm and iOS Dynamic already emit a
# ScrollView; this codegen emitted a bare FlowRow on every `lazy` value, so
# the same JSON scrolled on iOS and did not on Android — the cross-platform
# residue the parity ticket ended on.
#
# "Its own bounds" is literal. Compose throws (`Vertically scrollable
# component was measured with an infinity maximum height constraints`) when
# the node is measured with no max height — a wrapContent flow inside a
# LazyColumn cell or a scrolling sheet, which the corpus did not hold when the
# first arm shipped and a consumer's tree did. So the modifier is emitted only
# when the node's height is finite by its own declaration: a number, or a
# maxHeight. wrapContent and matchParent stay with the parent.
#
# `lazy` values come from attribute_definitions.json rather than a list here,
# so a value added to the SSoT is covered without anyone extending this file.
RSpec.describe KjuiTools::Compose::Components::CollectionComponent do
  DEFS = JSON.parse(
    File.read(File.expand_path('../../../lib/core/attribute_definitions.json', __dir__))
  ).freeze
  LAZY_VALUES = ((DEFS.dig('Collection', 'lazy', 'enum') || []) + [nil]).uniq.freeze
  SCROLL = '.verticalScroll(rememberScrollState())'

  def build(layout:, lazy:, height: 100, extra: {})
    json = { 'type' => 'Collection', 'id' => 'target', 'layout' => layout, 'width' => 150,
             'sections' => [{ 'cell' => 'probe_cell' }], 'items' => '@{items}' }
    json['height'] = height unless height.nil?
    json['lazy'] = lazy if lazy
    json.merge!(extra)
    imports = Set.new
    [described_class.generate(json, 0, imports), imports]
  end

  it 'has more than one lazy value to enumerate, or it measures nothing' do
    expect(LAZY_VALUES.size).to be >= 4
  end

  describe 'a self-bounded flow scrolls unless lazy is "none"' do
    LAZY_VALUES.each do |lazy|
      it "lazy=#{lazy || '(default)'}, height 100" do
        code, imports = build(layout: 'flow', lazy: lazy)
        if lazy == 'none'
          expect(code).not_to include(SCROLL)
          expect(imports).not_to include(:vertical_scroll)
        else
          expect(code).to include(SCROLL)
          expect(imports).to include(:vertical_scroll)
        end
      end
    end
  end

  describe 'its own bounds are literal' do
    # (height, extra attrs, scrolls?) — the crash shapes are the ones that
    # must NOT scroll, and each names why in its label.
    [
      [100, {}, true, 'a numeric height is a bound of its own'],
      ['100', {}, true, 'a numeric string is still a number'],
      ['wrapContent', { 'maxHeight' => 200 }, true, 'maxHeight bounds a wrapping height'],
      ['wrapContent', {}, false, 'wrapContent has no bounds: measured with infinite max height under a scrolling parent'],
      ['matchParent', {}, false, 'matchParent borrows the parent bounds, which the static emit cannot see'],
      [nil, {}, false, 'an undeclared height is not a bound'],
      ['@{h}', {}, false, 'a bound height is unknown here'],
    ].each do |height, extra, scrolls, why|
      it "height=#{height.inspect} #{extra.keys.join(',')}: #{why}" do
        code, imports = build(layout: 'flow', lazy: nil, height: height, extra: extra)
        if scrolls
          expect(code).to include(SCROLL)
          expect(imports).to include(:vertical_scroll)
        else
          expect(code).not_to include(SCROLL)
          expect(imports).not_to include(:vertical_scroll)
        end
      end
    end

    it 'lazy:"none" never scrolls, bounded or not' do
      code, = build(layout: 'flow', lazy: 'none', height: 100, extra: { 'maxHeight' => 200 })
      expect(code).not_to include(SCROLL)
    end
  end

  describe 'what the modifier sits on' do
    # Order is the contract: the size is the viewport and the background
    # paints it; the content scrolls inside. A scroll placed before the size
    # would scroll the viewport itself.
    it 'comes after the size and background, on the FlowRow' do
      code, = build(layout: 'flow', lazy: nil, extra: { 'background' => '#DDDDDD' })
      flow = code.index('FlowRow(')
      scroll = code.index(SCROLL)
      expect(flow).to be < scroll
      size_or_bg = [code.index('.width('), code.index('.height('), code.index('.background(')].compact.max
      expect(size_or_bg).not_to be_nil
      expect(size_or_bg).to be < scroll
    end
  end

  describe 'the other layouts are untouched' do
    # Their scrolling comes from the Lazy containers they already emit; adding
    # a second scroll modifier there would nest two scrollables.
    %w[vertical horizontal].each do |layout|
      it "#{layout} emits no verticalScroll modifier" do
        code, imports = build(layout: layout, lazy: nil)
        expect(code).not_to include(SCROLL)
        expect(imports).not_to include(:vertical_scroll)
      end
    end
  end

  describe 'the cell addresses survive' do
    # b7124797 gave the flow arm its testTag; the scroll modifier must not
    # displace it.
    it 'still tags every cell' do
      code, = build(layout: 'flow', lazy: nil)
      expect(code).to include('testTag("target_item_')
    end
  end
end
