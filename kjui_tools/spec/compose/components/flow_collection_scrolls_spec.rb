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
# `lazy` values come from attribute_definitions.json rather than a list here,
# so a value added to the SSoT is covered without anyone extending this file.
RSpec.describe KjuiTools::Compose::Components::CollectionComponent do
  DEFS = JSON.parse(
    File.read(File.expand_path('../../../lib/core/attribute_definitions.json', __dir__))
  ).freeze
  LAZY_VALUES = ((DEFS.dig('Collection', 'lazy', 'enum') || []) + [nil]).uniq.freeze
  SCROLL = '.verticalScroll(rememberScrollState())'

  def build(layout:, lazy:)
    json = { 'type' => 'Collection', 'id' => 'target', 'layout' => layout,
             'sections' => [{ 'cell' => 'probe_cell' }], 'items' => '@{items}' }
    json['lazy'] = lazy if lazy
    imports = Set.new
    [described_class.generate(json, 0, imports), imports]
  end

  it 'has more than one lazy value to enumerate, or it measures nothing' do
    expect(LAZY_VALUES.size).to be >= 4
  end

  describe 'flow scrolls unless lazy is "none"' do
    LAZY_VALUES.each do |lazy|
      it "lazy=#{lazy || '(default)'}" do
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

  describe 'what the modifier sits on' do
    # Order is the contract: the size is the viewport and the background
    # paints it; the content scrolls inside. A scroll placed before the size
    # would scroll the viewport itself.
    it 'comes after the size and background, on the FlowRow' do
      code, = build(layout: 'flow', lazy: nil)
      flow = code.index('FlowRow(')
      scroll = code.index(SCROLL)
      expect(flow).to be < scroll
      size_or_bg = [code.index('.width('), code.index('.height('), code.index('.background(')].compact.max
      expect(size_or_bg).to be < scroll if size_or_bg
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
