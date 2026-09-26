# frozen_string_literal: true

require 'stringio'
require 'swiftui/views/collection_converter'

# Collection.items is a CollectionDataSource or an array (4f ruling,
# 2026-09-26). A class-list Collection (cellClasses, no `sections`) whose items
# property the layout DECLARES a list — `Array`, `[T]` — is one section: every
# element with cellClasses[0], on the routes a one-section data source draws
# (List, grid, lazy:none, horizontal, flow, and paging — a page per element
# since 4f's round-6 ruling, 2026-09-26; it drew none). Any other
# declaration, or none, is the canonical CollectionDataSource,
# emitted as before. Until jsonui-cli 1.9.0 every class-list route read
# `.sections`, which a list does not have.
#
# The cells get what the cell view's model reads (init(data: Any); setData
# reads a dictionary): a list of the cell's own Data becomes its
# dictionaries, an untyped list is read element by element as dictionaries,
# and a list of any other type is named.
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  before(:all) { described_class.superclass.validation_enabled = false }
  after(:all) { described_class.superclass.validation_enabled = true }

  CLASS_LIST_ITEMS_ROUTES = {
    'List' => {}, 'grid' => { 'columns' => 2 }, 'lazy:none' => { 'lazy' => 'none' },
    'lazy:none grid' => { 'lazy' => 'none', 'columns' => 2 }, 'horizontal' => { 'layout' => 'horizontal' },
    'lazy:none horizontal' => { 'lazy' => 'none', 'layout' => 'horizontal' }, 'flow' => { 'layout' => 'flow' },
    'paging' => { 'layout' => 'horizontal', 'paging' => true }
  }.freeze

  CLASS_LIST_ITEMS_DECLARATIONS = {
    '[RowCellData] = []' => [{ 'name' => 'rows', 'class' => '[RowCellData]', 'defaultValue' => '[]' },
                             'Optional(data.rows.map({ $0.toDictionary() }))', 'var rows: [RowCellData] = []'],
    'Array (optional)' => [{ 'name' => 'rows', 'class' => 'Array' },
                           'data.rows?.compactMap({ $0 as? [String: Any] })', 'var rows: [Any]? = nil']
  }.freeze

  def convert(extra, data_property)
    described_class.new({ 'type' => 'Collection', 'id' => 'list', 'cellClasses' => ['row_cell'], 'items' => '@{rows}' }.merge(extra),
                        0, nil, nil, [data_property].compact).convert.to_s
  end

  CLASS_LIST_ITEMS_DECLARATIONS.each do |declared, (property, source, _swift)|
    CLASS_LIST_ITEMS_ROUTES.each do |route, extra|
      it "items #{declared}, #{route}: one ForEach over the list, no `.sections`" do
        code = convert(extra, property)
        expect(code.scan('RowCellView(').size).to eq(1), code
        expect(code).to include("if let cellsData = #{source} {")
        expect(code).not_to include('.sections')
      end
    end
  end

  it 'a CollectionDataSource, or no declaration, reads the data sections as before' do
    [{ 'name' => 'rows', 'class' => 'CollectionDataSource' }, nil].each do |property|
      expect(convert({}, property)).to include('ForEach(Array(dataSource.sections.enumerated())'), property.inspect
      expect(convert({ 'layout' => 'horizontal' }, property)).to include('let cellsData = dataSource.sections.first?.cells?.data {')
    end
  end

  # Through the tool's logger (its WARNING line), not a bare `warn` to stderr —
  # the rule jui_tools' test_ruby_tools_print_problems_through_their_loggers
  # holds for every line in lib.
  it "names a list of another type: its elements are no dictionary, so its cells draw with no data" do
    code = nil
    expect { code = convert({}, { 'name' => 'rows', 'class' => '[Booking]', 'defaultValue' => '[]' }) }
      .to output(/^WARNING: \[sjui\] Collection at list: items 'rows' is a list of Booking; a cell reads its own RowCellData or a dictionary/).to_stdout
    expect(code).to include('Optional(data.rows.compactMap({ $0 as? [String: Any] }))')
  end

  describe 'the emitted Swift type-checks', :swift_compile do
    CLASS_LIST_ITEMS_DECLARATIONS.each do |declared, (property, _source, swift)|
      it "items #{declared} on every route" do
        stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + EmittedSwift::COLLECTION_STACK_VIEW_STUB +
                cell_view_stub('RowCellView') +
                "struct RowCellData { var title: String = \"\"; func toDictionary() -> [String: Any] { [\"title\": title] } }\n" \
                "struct FlowLayout<Content: View>: View { let content: () -> Content\n" \
                "  init(alignment: HorizontalAlignment, horizontalSpacing: CGFloat, verticalSpacing: CGFloat, @ViewBuilder content: @escaping () -> Content) { self.content = content }\n" \
                "  var body: some View { VStack { content() } } }\n"
        # Paging draws no class-list cell, and its TabView page style is not
        # in the macOS SDK the check type-checks against.
        codes = CLASS_LIST_ITEMS_ROUTES.reject { |route, _| route == 'paging' }.values.map { |extra| convert(extra, property) }
        expect(compilable_view("VStack {\n#{codes.join("\n")}\n}", data: [swift], stubs: stubs)).to compile_as_swift
      end
    end
  end
end
