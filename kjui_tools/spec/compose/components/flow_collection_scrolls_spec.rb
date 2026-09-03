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
# maxHeight. wrapContent stays with the parent; matchParent and a bound
# height defer to the device (BoxWithConstraints), where the parent is
# visible — the arm the dynamic renderer takes for them.
#
# `lazy` values come from attribute_definitions.json rather than a list here,
# so a value added to the SSoT is covered without anyone extending this file.
RSpec.describe KjuiTools::Compose::Components::CollectionComponent do
  DEFS = JSON.parse(
    File.read(File.expand_path('../../../lib/core/attribute_definitions.json', __dir__))
  ).freeze
  LAZY_VALUES = ((DEFS.dig('Collection', 'lazy', 'enum') || []) + [nil]).uniq.freeze
  SCROLL = '.verticalScroll(rememberScrollState())'
  BOX = 'BoxWithConstraints('
  GUARD = 'if (constraints.hasBoundedHeight)'

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
      [nil, {}, false, 'an undeclared height is wrapContent by default: not a bound, and the parent scrolls'],
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
        # The static arms never defer to the device.
        expect(code).not_to include(BOX)
      end
    end

    it 'lazy:"none" never scrolls, bounded or not' do
      code, = build(layout: 'flow', lazy: 'none', height: 100, extra: { 'maxHeight' => 200 })
      expect(code).not_to include(SCROLL)
    end
  end

  describe 'matchParent asks the parent, on the device' do
    # The static emit cannot see the parent, and the parent decides whether
    # a matchParent flow has bounds to scroll inside. KotlinJsonUI's dynamic
    # renderer (db891a9) resolves exactly this shape with BoxWithConstraints
    # — scroll only when the box was measured with a bounded height — so
    # under a finite parent the same JSON scrolled there and not here. This
    # arm emits the same box: the node's own modifiers on it, a FlowRow
    # inside that fills and scrolls only when `constraints.hasBoundedHeight`.
    it 'emits BoxWithConstraints with the scroll behind hasBoundedHeight' do
      code, imports = build(layout: 'flow', lazy: nil, height: 'matchParent')
      expect(code).to include(BOX)
      expect(code).to include(GUARD)
      expect(code).to include(SCROLL)
      expect(imports).to include(:box_with_constraints, :vertical_scroll)
      # the guard is what the scroll hangs on: same line
      guarded = code.lines.find { |l| l.include?(GUARD) }
      expect(guarded).to include(SCROLL)
      expect(guarded).to include('Modifier.fillMaxSize()')
      expect(guarded).to include('else Modifier.fillMaxWidth()')
    end

    it 'puts the node on the box and the content padding on the FlowRow' do
      code, = build(layout: 'flow', lazy: nil, height: 'matchParent',
                    extra: { 'background' => '#DDDDDD', 'padding' => 4 })
      box = code.index(BOX)
      flow = code.index('FlowRow(')
      expect(box).to be < flow
      %w[.testTag("target") .fillMaxHeight() .background(].each do |on_box|
        expect(code.index(on_box)).to be > box
        expect(code.index(on_box)).to be < flow
      end
      expect(code.index('.padding(4.dp)')).to be > flow
    end

    it 'closes the box after the FlowRow (balanced braces)' do
      code, = build(layout: 'flow', lazy: nil, height: 'matchParent')
      expect(code.count('{')).to eq(code.count('}'))
      expect(code.rstrip).to end_with("}\n}")
    end

    LAZY_VALUES.each do |lazy|
      it "lazy=#{lazy || '(default)'}: the box arm follows lazy like the static arm" do
        code, imports = build(layout: 'flow', lazy: lazy, height: 'matchParent')
        if lazy == 'none'
          expect(code).not_to include(BOX)
          expect(code).not_to include(SCROLL)
          expect(imports).not_to include(:box_with_constraints)
        else
          expect(code).to include(BOX)
          expect(code).to include(GUARD)
        end
      end
    end

    it 'a bound height takes the box arm: unknown here, a number on the device' do
      # build_size emits `requiredHeight(data.h?.dp ?: 0.dp)` for it, so the
      # box is bounded at runtime whatever the parent does — the same
      # resolution the dynamic renderer gives a bound height.
      code, imports = build(layout: 'flow', lazy: nil, height: '@{h}')
      expect(code).to include(BOX)
      expect(code).to include(GUARD)
      expect(code).to include('.requiredHeight((data.h?.dp ?: 0.dp))')
      expect(imports).to include(:box_with_constraints)
      expect(code.index('.requiredHeight(')).to be < code.index('FlowRow(')
    end

    it 'an undeclared height does not take the box arm' do
      code, imports = build(layout: 'flow', lazy: nil, height: nil)
      expect(code).not_to include(BOX)
      expect(code).not_to include(SCROLL)
      expect(imports).not_to include(:box_with_constraints)
    end

    it 'a self-bounded matchParent (maxHeight) keeps the static modifier' do
      code, imports = build(layout: 'flow', lazy: nil, height: 'matchParent', extra: { 'maxHeight' => 200 })
      expect(code).to include(SCROLL)
      expect(code).not_to include(BOX)
      expect(imports).not_to include(:box_with_constraints)
    end

    it 'still tags every cell' do
      code, = build(layout: 'flow', lazy: nil, height: 'matchParent')
      expect(code).to include('testTag("target_item_')
    end
  end

  describe 'the overflow is laid out — clipping is clipToBounds\' to decide (51-E)' do
    # attribute_semantics.clipToBounds (2026-08-07): default false, absent
    # means no clip, hit testing follows clipping. FlowRow does not lay out
    # the rows past its max height, so a lazy:"none" flow in a fixed box drew
    # three rows and nothing below on Android while iOS and web drew six past
    # the box. The FlowRow is measured unbounded and aligned over the box —
    # the last modifier on it, after size, background, scroll and padding,
    # where KotlinJsonUI's dynamic renderer applies the same.
    UNBOUNDED = '.wrapContentHeight(Alignment.Top, unbounded = true)'

    it 'a lazy:"none" flow in a fixed box lays every row out past the box' do
      code, imports = build(layout: 'flow', lazy: 'none', height: 100, extra: { 'background' => '#DDDDDD', 'padding' => 4 })
      expect(code).to include(UNBOUNDED)
      expect(imports).to include(:alignment)
      last_modifier = code.index(UNBOUNDED)
      # A numeric height is emitted as requiredHeight (build_size).
      %w[.requiredHeight( .background( .padding(].each do |earlier|
        expect(code.index(earlier)).not_to be_nil
        expect(code.index(earlier)).to be < last_modifier
      end
      expect(code.index('FlowRow(')).to be < last_modifier
      expect(last_modifier).to be < code.index('horizontalArrangement')
    end

    LAZY_VALUES.each do |lazy|
      it "lazy=#{lazy || '(default)'}: the scrolling arms carry it too, after the scroll" do
        code, = build(layout: 'flow', lazy: lazy, height: 100)
        expect(code).to include(UNBOUNDED)
        expect(code.index(SCROLL)).to be < code.index(UNBOUNDED) if code.include?(SCROLL)
      end
    end

    it 'the matchParent box arm applies it on the inner FlowRow, after the guard' do
      code, = build(layout: 'flow', lazy: nil, height: 'matchParent')
      expect(code).to include(UNBOUNDED)
      expect(code.index(GUARD)).to be < code.index(UNBOUNDED)
      expect(code.index(UNBOUNDED)).to be < code.index('horizontalArrangement')
    end

    it 'never uses the deprecated FlowRow overflow parameter' do
      code, = build(layout: 'flow', lazy: 'none', height: 100)
      expect(code).not_to include('FlowRowOverflow')
      expect(code).not_to include('overflow =')
    end

    %w[vertical horizontal].each do |layout|
      it "#{layout} is untouched" do
        code, = build(layout: layout, lazy: 'none', height: 100)
        expect(code).not_to include(UNBOUNDED)
      end
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
