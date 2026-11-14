# frozen_string_literal: true

require 'json'
require 'compose/components/collection_component'
require 'compose/helpers/modifier_builder'

# Test drivers address a Collection's cells as `{collectionId}_item_{index}` —
# `tapItem` and `waitFor` resolve nothing else. Whether a cell HAD that address
# depended on the Collection's `layout`: the rule was written inline in seven
# arms and simply absent from two, so `tapItem` worked on a vertical Collection
# and failed on a flow one. `layout` says how cells are arranged. It should not
# decide whether a test can reach them.
#
# Reported for `layout: "flow"`. Counting the arms found a second one with the
# same gap that nobody had hit yet — the non-lazy horizontal Row
# (`lazy: "none"` + `layout: "horizontal"`).
#
# The combinations come from `attribute_definitions.json`, not from a list
# here, so a value added to the SSoT is covered without anyone remembering to
# extend this file. And the property is phrased so it needs no knowledge of
# which combinations are legal: IF an arm emits a cell, that cell carries an
# address.
module CollectionCellsAreAddressableSpec
  DEFS = JSON.parse(
    File.read(File.expand_path('../../../lib/core/attribute_definitions.json', __dir__))
  ).freeze
end

RSpec.describe KjuiTools::Compose::Components::CollectionComponent do

  def self.declared(attr)
    (CollectionCellsAreAddressableSpec::DEFS.dig('Collection', attr, 'enum') || []).uniq
  end

  # Canonical spellings only — the alias spellings route to the same arm and
  # `collection_component_spec` already pins that they do.
  LAYOUTS = (declared('layout') - %w[Flow LeftAligned leftAligned]).freeze
  LAZY = declared('lazy').freeze

  def build(layout:, lazy:, paging:)
    json = {
      'type' => 'Collection', 'id' => 'target',
      'sections' => [{ 'cell' => 'probe_cell' }],
      'items' => '@{items}',
    }
    json['layout'] = layout if layout
    json['lazy'] = lazy if lazy
    json['paging'] = true if paging
    described_class.generate(json, 0, Set.new)
  end

  # A cell is emitted iff the arm calls the cell composable.
  def emits_cell?(code)
    code.include?('ProbeCellView(')
  end

  describe 'every arm that emits a cell gives it an address' do
    it 'covers more than one combination, or it is measuring nothing' do
      expect(LAYOUTS.size).to be >= 3
      expect(LAZY.size).to be >= 3
    end

    LAYOUTS.each do |layout|
      LAZY.each do |lazy|
        [false, true].each do |paging|
          label = "layout=#{layout} lazy=#{lazy}#{paging ? ' paging' : ''}"
          it label do
            code = build(layout: layout, lazy: lazy, paging: paging)
            next unless emits_cell?(code)

            expect(code).to include('testTag("target_item_'),
                            "#{label} emits a cell with no _item_ address"
          end
        end
      end
    end
  end

  describe 'the two arms the report and the sweep found' do
    # Named on their own so a failure says which shape broke rather than
    # leaving the reader to decode a parameterised label.
    it 'flow' do
      expect(build(layout: 'flow', lazy: nil, paging: false))
        .to include('testTag("target_item_')
    end

    it 'non-lazy horizontal Row' do
      expect(build(layout: 'horizontal', lazy: 'none', paging: false))
        .to include('testTag("target_item_')
    end

    it 'vertical — the control, addressable before this change too' do
      expect(build(layout: 'vertical', lazy: nil, paging: false))
        .to include('testTag("target_item_')
    end
  end

  # A cell's address counts the cells of the drawn sections before its own
  # (2.5.39, the orchestrator's ruling (a2), ticket jui-collection-item-
  # identifier-repeats-per-section): until then a second section's cells took
  # `_item_0`, `_item_1`, ... again — the first section's ids — on every route
  # but the pager. Section 0's cells keep `cellIndex`; section 1's add section
  # 0's count, read from the list hoisted before the Collection. The run-based
  # specs (collection_flow_sections, collection_section_grid,
  # collection_scroll_to_cell) read the n each route draws; this sweep keeps
  # every combination the SSoT declares on the rule.
  describe 'a second section continues the first section\'s count' do
    def build_two(layout:, lazy:, paging:, columns:)
      json = {
        'type' => 'Collection', 'id' => 'target',
        'sections' => [{ 'cell' => 'a_cell' }, { 'cell' => 'b_cell' }],
        'items' => '@{items}',
      }
      json['layout'] = layout if layout
      json['lazy'] = lazy if lazy
      json['paging'] = true if paging
      json['columns'] = columns if columns
      described_class.generate(json, 0, Set.new)
    end

    # The testTag of the view call each `<Name>View(` opens.
    def tags_after(code, view)
      code.scan(/#{view}\(.*?testTag\("target_item_(.*?)"\)/m).flatten
    end

    LAYOUTS.each do |layout|
      LAZY.each do |lazy|
        [false, true].each do |paging|
          [nil, 2].each do |columns|
            label = "layout=#{layout} lazy=#{lazy}#{paging ? ' paging' : ''}#{columns ? " columns=#{columns}" : ''}"
            it label do
              code = build_two(layout: layout, lazy: lazy, paging: paging, columns: columns)
              second = tags_after(code, 'BCellView')
              next if second.empty? # this route draws the first section only

              tags_after(code, 'ACellView').each { |tag| expect(%w[$cellIndex $page]).to include(tag), "#{label}: #{tag}" }
              second.each do |tag|
                expect(['$page', '${(cellCounts_target.getOrNull(0) ?: 0) + cellIndex}']).to include(tag), "#{label}: #{tag}"
              end
              if second.any? { |tag| tag.include?('cellCounts_target') }
                expect(code).to match(/\Aval cellCounts_target = data\.items\??\.sections(?:\.orEmpty\(\))?\.map \{ it\.cells\?\.data\?\.size \?: 0 \}\n/), code
              end
            end
          end
        end
      end
    end

    it 'a Collection of one section reads no count and hoists none' do
      code = build(layout: 'vertical', lazy: nil, paging: false)
      expect(code).not_to include('cellCounts_')
      expect(code).to include('testTag("target_item_$cellIndex")')
    end

    it 'the class-list shape (no sections) adds the data sections before the cell\'s own' do
      code = described_class.generate({ 'type' => 'Collection', 'id' => 'target', 'items' => '@{items}',
                                        'cellClasses' => ['a_cell'], 'lazy' => 'none' }, 0, Set.new)
      expect(code).to match(/\Aval cellCounts_target = data\.items\??\.sections(?:\.orEmpty\(\))?\.map \{ it\.cells\?\.data\?\.size \?: 0 \}\n/), code
      expect(code).to include('testTag("target_item_${cellCounts_target.take(sectionIndex).sum() + cellIndex}")'), code
    end
  end

  describe 'the rule lives in one place' do
    # The gap was two arms forgetting a line that seven others carried. A
    # tenth arm should inherit it rather than have to remember it.
    #
    # These three go red on the helper being ABSENT, not on a cell losing its
    # address — they witness the consolidation, not the defect. Counted apart
    # from the arms above for that reason: an implementation that added the
    # helper and called it from nowhere would satisfy them.
    it 'is emitted through the shared helper' do
      expect(described_class).to respond_to(:cell_test_tag_modifier)
    end

    it 'still omits the tag when the Collection has no id to build one from' do
      expect(described_class.cell_test_tag_modifier(nil, 'cellIndex', 0))
        .to eq('modifier = Modifier')
    end

    it 'keeps a caller-supplied modifier chain after the tag' do
      expect(described_class.cell_test_tag_modifier('c', 'page', 0, '.fillMaxSize()'))
        .to include('testTag("c_item_$page").fillMaxSize()')
    end
  end
end
