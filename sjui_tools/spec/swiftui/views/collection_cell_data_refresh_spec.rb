# frozen_string_literal: true

require 'swiftui/views/collection_converter'
require_relative '../../support/emitted_swift'

# A cell whose key stays fixed while its data changes shows the new data
# (ticket ios-cell-ignores-data-change-when-cellid-is-fixed-android-updates).
# The cell views `sjui g collection` and `sjui build` scaffold — app-owned
# once written — are Equatable on the "cellId" in their data, re-read their
# data on its change, and guard their view model's setData on it. A Collection
# whose cells kept a fixed "cellId" (cellIdProperty "cellId", no
# autoChangeTrackingId) kept the old data on iOS: 0 of 6 cells on the
# ConformanceHost probe, 0 of 8 on a consumer's tabs; Android and both
# Dynamic renderers redrew them. So every cell is handed its data with "cellId"
# rewritten to CellIdGenerator.autoId of it — its key, then a hash of the rest
# — while the loop keeps knowing the cell by its key. Generated code, so an
# app's existing scaffolds get it on the next build.
#
# The drawn arm is CellDataRefreshProbeUITests in SwiftJsonUI's
# ConformanceHost: (A) cellIdProperty "cellId", (B) "key", (C) "cellId" with
# autoChangeTrackingId, each on Dynamic and generated code.
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  include EmittedSwift

  before(:all) { described_class.superclass.validation_enabled = false }
  after(:all) { described_class.superclass.validation_enabled = true }

  def emit(extra)
    described_class.new({ 'type' => 'Collection', 'id' => 'list', 'width' => 300, 'height' => 200, 'items' => '@{rows}',
                          'sections' => [{ 'cell' => 'ACell' }] }.merge(extra)).convert.to_s
  end

  def cell_lines(code)
    code.lines.map(&:strip).grep(/\AACellView\(data:/)
  end

  it 'cellIdProperty "cellId": the cell gets "cellId" = autoId of its data, keyed on its own cellId' do
    code = emit('cellIdProperty' => 'cellId')
    expect(cell_lines(code)).to eq([
      'ACellView(data: { () -> [String: Any] in var refreshed = cell.data; refreshed["cellId"] = CellIdGenerator.autoId(from: cell.data, ' \
      'primaryKey: "cellId", fallbackIndex: cell.index); return refreshed }()).equatable()'
    ])
    # The loop still knows the cell by its key: no content in its id.
    expect(code).to include('IdentifiedCellItem(id: ').and include('ForEach(zip(ids, items)')
    expect(code).not_to include('.id(CellIdGenerator')
  end

  it 'another cellIdProperty: keyed on the data\'s own "cellId" when it has one, else on the cellIdProperty value' do
    expect(cell_lines(emit('cellIdProperty' => 'key')).first)
      .to include('primaryKey: cell.data["cellId"] != nil ? "cellId" : "key", fallbackIndex: cell.index')
  end

  it 'no cellIdProperty: keyed on the data\'s own "cellId", else on its place' do
    expect(cell_lines(emit({})).first)
      .to include('var refreshed = cellData;')
      .and include('primaryKey: "cellId", fallbackIndex: cellIndex')
  end

  # Only another cellIdProperty has a choice to write: with none, or "cellId"
  # itself, the data's own "cellId" and the fallback are one name (1.9.11
  # wrote `… ? "cellId" : "cellId"`).
  it 'writes the choice of primary key only when there is one' do
    [cell_lines(emit('cellIdProperty' => 'cellId')).first, cell_lines(emit({})).first].each do |line|
      expect(line).to include('primaryKey: "cellId", fallbackIndex: ')
      expect(line).not_to include('? "cellId" : "cellId"')
    end
    expect(cell_lines(emit('cellIdProperty' => 'key')).first).to include('? "cellId" : "key"')
  end

  it 'autoChangeTrackingId with cellIdProperty: the data is already enriched so, and passes as it is' do
    code = emit('cellIdProperty' => 'cellId', 'autoChangeTrackingId' => true)
    expect(cell_lines(code)).to eq(['ACellView(data: cell.data).equatable()'])
    expect(code).to include('.reconfigured(cellIdProperty: "cellId", autoChangeTrackingId: true)')
  end

  it 'every cell route hands the rewritten data: no cell view is built from the raw data' do
    routes = [
      {}, { 'cellIdProperty' => 'cellId' }, { 'columns' => 2 }, { 'layout' => 'horizontal' },
      { 'layout' => 'horizontal', 'paging' => true }, { 'lazy' => 'none' }, { 'lazy' => 'none', 'columns' => 2 },
      { 'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'ACell' }], 'cellIdProperty' => 'cellId' },
      { 'sections' => nil, 'cellClasses' => ['ACell'] }, { 'sections' => nil, 'cellClasses' => ['ACell'], 'columns' => 2 }
    ]
    routes.each do |extra|
      lines = cell_lines(emit(extra).to_s)
      expect(lines).not_to be_empty, extra.inspect
      expect(lines.grep_v(/\AACellView\(data: \{ \(\) -> \[String: Any\] in var refreshed = /)).to eq([]), extra.inspect
    end
  end

  # The pager is left out: its page style does not type-check for macOS,
  # the platform this arm compiles for (collection_paging_pages_spec.rb strips it).
  it 'type-checks on every route but the pager', :swift_compile do
    stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + EmittedSwift::COLLECTION_STACK_VIEW_STUB + cell_view_stub('ACellView')
    codes = [{}, { 'cellIdProperty' => 'cellId' }, { 'cellIdProperty' => 'key' }, { 'columns' => 2 },
             { 'layout' => 'horizontal' }, { 'lazy' => 'none' }, { 'sections' => nil, 'cellClasses' => ['ACell'] },
             { 'cellIdProperty' => 'cellId', 'autoChangeTrackingId' => true }].map { |extra| emit(extra) }
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}", data: ['var rows: CollectionDataSource? = nil'],
                           stubs: stubs + "\nextension Array where Element == [String: Any] {\n" \
                                          "  func reconfigured(cellIdProperty: String?, autoChangeTrackingId: Bool) -> [[String: Any]] { self }\n}\n"))
      .to compile_as_swift
  end
end
