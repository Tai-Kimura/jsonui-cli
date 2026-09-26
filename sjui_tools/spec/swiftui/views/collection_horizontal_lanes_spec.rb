# frozen_string_literal: true

require 'swiftui/views/collection_converter'

# A horizontal Collection's lanes and spacing (4f ruling, 2026-09-26; the rule
# SwiftJsonUI Dynamic dde0628 draws, word for word):
# - Lanes: a section has more than one lane when its own `columns`, else the
#   Collection's, is above 1. A bound `columns` keeps the grid even at 1 lane;
#   a section's own count overrides it. Paging is unchanged.
# - Cell order: a column is filled top to bottom, then the next column
#   (LazyHorizontalGrid's order — LazyHGrid's own).
# - Section blocks: each section starts a new column.
# - Spacing, for every horizontal Collection including a single lane: along
#   the scroll axis lineSpacing, else itemSpacing, else 0; between lanes
#   columnSpacing, else itemSpacing, else 0. Pages sit along the scroll axis.
# Until jsonui-cli 1.9.0 (measured on d975d6eb) every horizontal route drew one
# lane whatever `columns` said, and the single-lane stack took its spacing from
# itemSpacing, then columnSpacing, then lineSpacing.
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  before(:all) { described_class.superclass.validation_enabled = false }
  after(:all) { described_class.superclass.validation_enabled = true }

  def convert(extra)
    described_class.new({ 'type' => 'Collection', 'id' => 'list', 'layout' => 'horizontal', 'items' => '@{rows}' }.merge(extra)).convert.to_s
  end

  # [lanes, lane spacing, scroll spacing] of each LazyHGrid, in order.
  def grids(code)
    code.scan(/LazyHGrid\(rows: Array\(repeating: GridItem\(\.flexible\(\), spacing: (\S+?)\), count: (\S+?)\), alignment: \.\w+, spacing: (\S+?)\) \{/)
        .map { |lane, count, scroll| [count, lane, scroll] }
  end

  # The section each LazyHGrid opens in: the `sections[N]` line before it.
  def grid_sections(code)
    lines = code.lines
    lines.each_index.select { |i| lines[i].include?('LazyHGrid(') }
         .map { |i| lines[0...i].reverse.find { |l| l =~ /sections\[(\d+)\]/ }.to_s[/sections\[(\d+)\]/, 1] }
  end

  HORIZONTAL_LANES_SECTIONS = [{ 'cell' => 'ACell' }, { 'cell' => 'BCell', 'columns' => 1 }, { 'cell' => 'CCell', 'columns' => 3 }].freeze
  HORIZONTAL_LANES_ROUTES = {
    'lazy stack' => {}, 'eager stack' => { 'lazy' => 'eager' }, 'horizontalScroll' => { 'layout' => 'vertical', 'horizontalScroll' => true },
    'lazy:none row' => { 'lazy' => 'none' }
  }.freeze

  HORIZONTAL_LANES_ROUTES.each do |route, extra|
    it "#{route}: a section's lanes are its own columns, else the Collection's; one lane keeps the stack" do
      code = convert(extra.merge('columns' => 2, 'lineSpacing' => 8, 'columnSpacing' => 4, 'sections' => HORIZONTAL_LANES_SECTIONS))
      expect(grids(code)).to eq([%w[2 4 8], %w[3 4 8]]), code
      expect(grid_sections(code)).to eq(%w[0 2]), code # section 1 (own columns 1) is one lane
      expect(code[code.index('sections[1]')..][/.*?\n.*?\n.*?\n/m]).not_to include('LazyHGrid'), code
    end
  end

  it 'a bound columns keeps the grid at any count; a section that declares its own overrides it' do
    code = convert('columns' => '@{cols}', 'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell', 'columns' => 1 }])
    expect(grids(code)).to eq([%w[data.cols 0 0]]), code
    expect(grid_sections(code)).to eq(%w[0])
  end

  it 'the class-list shape takes the Collection columns as its lanes, on the stack and the lazy:none row' do
    [{}, { 'lazy' => 'none' }].each do |extra|
      code = convert(extra.merge('columns' => 2, 'cellClasses' => ['RowCell'], 'itemSpacing' => 6))
      expect(grids(code)).to eq([%w[2 6 6]]), code
    end
  end

  it 'one column, no lanes: the stack as before' do
    expect(grids(convert('sections' => HORIZONTAL_LANES_SECTIONS.first(1)))).to eq([])
    expect(grids(convert('columns' => 1, 'sections' => HORIZONTAL_LANES_SECTIONS.first(1)))).to eq([])
  end

  describe 'spacing on every horizontal Collection, one lane or many' do
    def stack_spacing(code)
      code[/^\s*spacing: (\S+),$/, 1] || code[/HStack\(alignment: \.\w+, spacing: (\S+?)\)/, 1]
    end

    it 'along the scroll axis: lineSpacing, else itemSpacing, else 0 — columnSpacing is the lanes' do
      [{}, { 'lazy' => 'none' }].each do |extra|
        base = extra.merge('sections' => [{ 'cell' => 'ACell' }])
        expect(stack_spacing(convert(base.merge('lineSpacing' => 8, 'itemSpacing' => 5, 'columnSpacing' => 3)))).to eq('8')
        expect(stack_spacing(convert(base.merge('itemSpacing' => 5, 'columnSpacing' => 3)))).to eq('5')
        expect(stack_spacing(convert(base.merge('columnSpacing' => 3)))).to eq('0')
        expect(stack_spacing(convert(base))).to eq('0')
      end
      lanes = convert('columns' => 2, 'itemSpacing' => 5, 'sections' => [{ 'cell' => 'ACell' }])
      expect(grids(lanes)).to eq([%w[2 5 5]])
    end

    it 'pages: lineSpacing, else itemSpacing (paging draws no lanes)' do
      pager = ->(extra) { convert({ 'paging' => true, 'columns' => 2, 'sections' => [{ 'cell' => 'ACell' }] }.merge(extra)) }
      expect(pager.call('lineSpacing' => 8, 'itemSpacing' => 4, 'columnSpacing' => 2)).to include('.padding(.horizontal, 4.0)')
      expect(pager.call('itemSpacing' => 4, 'columnSpacing' => 2)).to include('.padding(.horizontal, 2.0)')
      expect(pager.call('columnSpacing' => 2)).not_to include('.padding(.horizontal')
      expect(grids(pager.call('lineSpacing' => 8))).to eq([])
    end
  end

  describe 'the emitted Swift type-checks', :swift_compile do
    it 'on the stack, the lazy:none row, the class-list shape and a bound lane count' do
      stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + EmittedSwift::COLLECTION_STACK_VIEW_STUB +
              cell_view_stub('ACellView', 'BCellView', 'CCellView', 'RowCellView')
      codes = HORIZONTAL_LANES_ROUTES.values.map { |extra| convert(extra.merge('columns' => 2, 'lineSpacing' => 8, 'columnSpacing' => 4, 'sections' => HORIZONTAL_LANES_SECTIONS)) } +
              [convert('columns' => '@{cols}', 'sections' => HORIZONTAL_LANES_SECTIONS.first(1)),
               convert('columns' => 2, 'cellClasses' => ['RowCell'], 'lazy' => 'none')]
      expect(compilable_view("VStack {\n#{codes.join("\n")}\n}",
                             data: ['var rows: CollectionDataSource? = nil', 'var cols: Int = 2'], stubs: stubs)).to compile_as_swift
    end
  end
end
