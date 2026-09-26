# frozen_string_literal: true

require 'swiftui/views/collection_converter'
require_relative '../../support/emitted_swift'

# The iOS routes that drew no scrollTo until jsonui-cli 1.9.0 (round 12), by
# the rule of the SSoT's Collection.scrollTo — an Int is a cell counted across
# the drawn sections, a String the first cell, in section order, whose key
# (its cellId, else its cellIdProperty value) it is, anything else scrolls
# nowhere; the request is a change of the value:
# - the class-list shape's single-column List (cellClasses, no `sections`):
#   every data section's cells, looked up when the value changes — their ids
#   are their place, IndexPath(item:section:); the class-list grid, which
#   shares that emit, had `.id(cellIndex)` in every data section;
# - the pager: its TabView turns to the page the value names — the bound
#   currentPage, else a page state of its own;
# - a String with no cellIdProperty: a cell's cellId is its key.
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  include EmittedSwift

  before(:all) { described_class.superclass.validation_enabled = false }
  after(:all) { described_class.superclass.validation_enabled = true }

  INT = [{ 'name' => 'target', 'class' => 'Int', 'defaultValue' => 0 }].freeze
  STR = [{ 'name' => 'target', 'class' => 'String', 'defaultValue' => '' }].freeze

  def emit(node, props, rows: 'CollectionDataSource')
    converter = described_class.new({ 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'scrollTo' => '@{target}' }
                                      .merge(node), 0, nil, nil, props + [{ 'name' => 'rows', 'class' => rows }])
    [converter.convert.to_s, converter.state_variables]
  end

  CLASS_LIST = { 'cellClasses' => ['ACell'] }.freeze
  PAGER = { 'layout' => 'horizontal', 'paging' => true, 'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell' }] }.freeze

  describe 'the class-list List' do
    it 'reaches every data section: a reader, the cells by their place, the value looked up when it changes' do
      code, = emit(CLASS_LIST, INT)
      expect(code).to include('ScrollViewReader { scrollProxy in')
      expect(code).to include('.id(IndexPath(item: cellIndex, section: sectionIndex))')
      expect(code).to include('.onChange(of: data.target) { _, index in')
      expect(code).to include('search: for (sectionIndex, section) in (data.rows?.sections ?? []).enumerated() {')
      expect(code).to include('if place == index { found = IndexPath(item: cellIndex, section: sectionIndex); break search }')
      expect(code).to include('scrollProxy.scrollTo(found, anchor: .top)').or include('scrollProxy.scrollTo(found, anchor: .bottom)')
      expect(code).not_to include('.id(cellIndex)')
    end

    it 'a String is a key: the cellId, else the cellIdProperty value when there is one' do
      keyed, = emit(CLASS_LIST.merge('cellIdProperty' => 'key'), STR)
      expect(keyed).to include('if ((cell["cellId"] as? String) ?? (cell["key"] as? String)) == cellId { found = IndexPath(')
      ids, = emit(CLASS_LIST, STR)
      expect(ids).to include('if (cell["cellId"] as? String) == cellId { found = IndexPath(')
      expect(ids).not_to include('place')
    end

    it 'the class-list grid shares the emit, so its cells answer by their place too' do
      code, = emit(CLASS_LIST.merge('columns' => 2), INT)
      expect(code).to include('.id(IndexPath(item: cellIndex, section: sectionIndex))')
      expect(code).to include('scrollProxy.scrollTo(found, anchor:')
    end
  end

  describe 'the pager' do
    it 'turns a page state of its own, 0 as the TabView starts, to the page the value names' do
      code, state = emit(PAGER, INT)
      expect(state).to eq(['@State private var listScrollPage: Int = 0'])
      expect(code).to include('TabView(selection: $listScrollPage) {')
      expect(code).to include('.onChange(of: data.target) { _, index in')
      expect(code).to include('if page == index { found = page; break search }')
      expect(code).to include('withAnimation { listScrollPage = found }')
    end

    it 'turns the bound currentPage when there is one, and a key names the first page with it' do
      code, state = emit(PAGER.merge('currentPage' => '@{page}', 'cellIdProperty' => 'key', 'scrollAnimated' => false), STR)
      expect(state).to eq([])
      expect(code).to include('TabView(selection: $data.page) {')
      expect(code).to include('if ((cell["cellId"] as? String) ?? (cell["key"] as? String)) == cellId { found = page; break search }')
      expect(code).to include("\n    data.page = found\n")
    end

    it 'control: with no scrollTo it has no selection of its own and no lookup' do
      code, state = emit(PAGER.merge('scrollTo' => nil), INT)
      expect(state).to eq([])
      expect(code).to include('TabView {')
      expect(code).not_to include('search:')
    end
  end

  describe 'a String with no cellIdProperty' do
    it "is a cell's cellId: a cell with one takes it as .id — a later section's only when no earlier one has it" do
      code, = emit({ 'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell' }] }, STR)
      expect(code).to include('.id((cellData["cellId"] as? String).map { AnyHashable($0) } ?? AnyHashable(cellIndex))')
      expect(code).to include('let earlierKeys = Set([0].map { dataSource.sections[$0] }.flatMap { ($0.cells?.data ?? []).compactMap { $0["cellId"] as? String } })')
      expect(code).to include('.id((cell.data["cellId"] as? String).flatMap { earlierKeys.contains($0) ? nil : AnyHashable($0) } ?? AnyHashable(sectionStart + cell.index))')
      expect(code).to include('.onChange(of: data.target) { _, cellId in')
    end

    it 'control: an Int keeps the counted ids' do
      code, = emit({ 'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell' }] }, INT)
      expect(code).to include('.id(cellIndex)')
      expect(code).not_to include('AnyHashable')
    end
  end

  it 'type-checks on each route, Int and String', :swift_compile do
    stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + EmittedSwift::COLLECTION_STACK_VIEW_STUB +
            cell_view_stub('ACellView', 'BCellView')
    shapes = [[CLASS_LIST, INT], [CLASS_LIST.merge('cellIdProperty' => 'key'), STR], [CLASS_LIST, STR],
              [CLASS_LIST.merge('columns' => 2), INT], [PAGER, INT], [PAGER.merge('cellIdProperty' => 'key'), STR],
              [PAGER.merge('currentPage' => '@{page}'), INT],
              [{ 'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell' }] }, STR]]
    views = shapes.each_with_index.map do |(node, props), i|
      code, state = emit(node.merge('id' => "list#{i}"), props)
      # `.page(indexDisplayMode:)` is iOS only and this check type-checks for
      # the host (collection_paging_pages_spec.rb sets it aside the same way).
      code = code.lines.reject { |l| l.include?('.tabViewStyle(.page(') }.join
      target = props.first['class'] == 'String' ? 'var target: String = ""' : 'var target: Int = 0'
      <<~SWIFT
        struct Host#{i}Data { var rows: CollectionDataSource? = nil; #{target}; var page: Int = 0 }
        struct Host#{i}: View {
            @State var data = Host#{i}Data()
        #{state.map { |l| "    #{l}" }.join("\n")}
            var body: some View {
        #{code.lines.map { |l| "        #{l}" }.join}
            }
        }
      SWIFT
    end
    expect("#{EmittedSwift::LIBRARY_STUBS}\n#{stubs}\n#{views.join("\n")}").to compile_as_swift
  end
end
