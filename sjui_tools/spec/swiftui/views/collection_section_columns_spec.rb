# frozen_string_literal: true

require 'swiftui/views/collection_converter'

# A section's own `columns` is declared (attribute_definitions.json,
# Collection.sections.items.properties.columns), so a section declaring more
# than one draws as a grid of that many on every vertical route that draws
# sections — including the routes where the Collection itself is one column.
# Until 1.8.121 (measured on a22b5182, 2026-09-26) the list-style, lazy and
# non-lazy single-column routes drew it one cell per row; the section's
# columns were read only on the grid routes.
#
# And one reading of a grid's spacing (Collection.columnSpacing "Spacing
# between columns", lineSpacing "Spacing between rows", itemSpacing "used for
# both grid spacing and list item spacing"): between cells columnSpacing, else
# itemSpacing; between rows lineSpacing, else itemSpacing. The non-lazy grid
# put columnSpacing between rows too.
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  before(:all) { described_class.superclass.validation_enabled = false }
  after(:all) { described_class.superclass.validation_enabled = true }

  def convert(extra)
    described_class.new({
      'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}',
      'sections' => [{ 'cell' => 'ACell', 'columns' => 2 }, { 'cell' => 'BCell' }]
    }.merge(extra)).convert.to_s
  end

  # The LazyVGrid lines in the emit: [cell spacing, count, row spacing].
  def grids(code)
    code.scan(/LazyVGrid\(columns: Array\(repeating: GridItem\(\.flexible\(\), spacing: (\S+?)\), count: (\S+?)\), alignment: \S+, spacing: (\S+?)\) \{/)
  end

  SINGLE_COLUMN_ROUTES = {
    'list style' => { 'listStyle' => 'plain' },
    'lazy' => {},
    'lazy:none' => { 'lazy' => 'none' }
  }.freeze

  SINGLE_COLUMN_ROUTES.each do |route, extra|
    it "#{route}, one column: the section declaring 2 is a grid of 2, the other is not" do
      code = convert(extra.merge('columnSpacing' => 3, 'lineSpacing' => 7))
      expect(grids(code)).to eq([%w[3 2 7]]), code
      grid_at = code.index('LazyVGrid(')
      expect(grid_at).to be < code.index('ACellView(')
      expect(code.index('BCellView(')).to be > code.index('ACellView(')
      # The grid's cells fill their column, as every grid route's do.
      a_cell = code[code.index('ACellView(')..code.index('BCellView(')]
      expect(a_cell).to include('.frame(maxWidth: .infinity)')
      expect(code[code.index('BCellView(')..]).not_to include('.frame(maxWidth: .infinity)')
    end
  end

  it 'the non-lazy grid spaces rows by lineSpacing and cells by columnSpacing; itemSpacing stands in for either' do
    both = convert('columns' => 2, 'lazy' => 'none', 'columnSpacing' => 3, 'lineSpacing' => 7)
    expect(grids(both)).to eq([%w[3 2 7], %w[3 2 7]]), both
    legacy = described_class.new({ 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'columns' => 2,
                                   'lazy' => 'none', 'cellClasses' => ['ACell'], 'columnSpacing' => 3, 'lineSpacing' => 7 }).convert.to_s
    expect(grids(legacy)).to eq([%w[3 2 7]]), legacy
    item = convert('columns' => 2, 'lazy' => 'none', 'itemSpacing' => 5)
    expect(grids(item)).to eq([%w[5 2 5], %w[5 2 5]]), item
    # The lazy grid already read it this way; the control.
    expect(grids(convert('columns' => 2, 'columnSpacing' => 3, 'lineSpacing' => 7))).to eq([%w[3 2 7], %w[3 2 7]])
  end

  describe 'the emitted Swift type-checks', :swift_compile do
    it 'on each single-column route and the non-lazy grid' do
      stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + EmittedSwift::COLLECTION_STACK_VIEW_STUB +
              cell_view_stub('ACellView', 'BCellView')
      codes = SINGLE_COLUMN_ROUTES.values.map { |extra| convert(extra.merge('columnSpacing' => 3, 'lineSpacing' => 7)) } +
              [convert('columns' => 2, 'lazy' => 'none', 'columnSpacing' => 3, 'lineSpacing' => 7)]
      body = "VStack {\n#{codes.join("\n")}\n}"
      expect(compilable_view(body, data: ['var rows: CollectionDataSource? = nil'], stubs: stubs)).to compile_as_swift
    end
  end
end
