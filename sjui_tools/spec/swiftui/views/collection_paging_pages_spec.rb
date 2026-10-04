# frozen_string_literal: true

require 'open3'
require 'tempfile'
require 'swiftui/views/collection_converter'

# A paging Collection's pages (4f ruling, 2026-09-26, round 6): one page per
# cell, every drawn section's cells in order — what SwiftJsonUI Dynamic, rjui
# and KotlinJsonUI Dynamic draw. A page's tag is its place among ALL the
# pages, so a bound `currentPage` (TabView(selection:)) names exactly one
# page: a section's tags start where the drawn sections before it end
# (`let pageStart = …`). Until jsonui-cli 1.9.0 every section's tags counted
# from 0, so section 2's pages carried section 1's tags again. The class-list
# shape (cellClasses, no `sections`) is one section — the first data section,
# or the declared list — as on the other one-section routes; it drew no page.
#
# A later section's cells are counted from its pageStart in the ids its
# ForEach gives them, not only in the tag (round 8): sibling ForEaches whose
# ids repeat (`\.offset` from 0 in each) end a TabView at the first section's
# last page — measured on the ConformanceHost codegen host with XCUITest
# (PagingAddressProbeUITests), a pager of 2 + 3 cells stopped at page 1.
#
# One declared section keeps the text this converter always wrote (the
# golden below is that emit, measured on deaead11 for the shape the faces'
# three carousels have: one section, cellClasses naming the same cell,
# currentPage bound, itemSpacing).
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  before(:all) { described_class.superclass.validation_enabled = false }
  after(:all) { described_class.superclass.validation_enabled = true }

  def convert(extra)
    described_class.new({ 'type' => 'Collection', 'id' => 'pager', 'layout' => 'horizontal', 'paging' => true,
                          'items' => '@{rows}', 'currentPage' => '@{page}' }.merge(extra)).convert.to_s
  end

  PAGING_FOUR_SECTIONS = [{ 'cell' => 'ACell' }, { 'header' => 'HCell' }, { 'cell' => 'BCell' }, { 'cell' => 'CCell' }].freeze

  # The tag each page carries, in the order the pages are drawn, for a data
  # source whose sections hold `counts` cells: read off the emitted text —
  # each section block's guard (`sections.count > k`), its `pageStart` sum
  # (each `sections[j]…count ?? 0` term is counts[j]) and its `.tag(…)`.
  def tags(code, counts)
    blocks = code.scan(/sections\.count > (\d+) \{\n(.*?)\.tag\(([^)]*)\)/m)
    expect(blocks).not_to be_empty, code
    blocks.flat_map do |k, body, tag|
      k = k.to_i
      next [] unless k < counts.size

      start = body[/let pageStart = (.*)$/, 1]
      offset = if start
                 sum = start.gsub(/\((?:dataSource|data\.rows)\.sections\[(\d+)\]\.cells\?\.data\.count \?\? 0\)/) { counts[Regexp.last_match(1).to_i].to_s }
                 expect(sum).to match(/\A[\d +]+\z/), start
                 sum.split('+').sum(&:to_i)
               else
                 0
               end
      expect(tag).to eq(start ? 'cell.index' : 'cellIndex').or eq('cell.index')
      # The loop's index is the page: a later section's ForEach counts from
      # its pageStart, in its ids as in the index it hands the cell.
      if start
        expect(body).to include("ForEach(cellsData.enumerated().map { IdentifiedCellItem(id: \"#{k}:\\($0.offset)\", " \
                                'index: pageStart + $0.offset, data: $0.element) }) { cell in')
          .or include('index: pageStart + index, data: data)')
      else
        expect(body).to include('ForEach(Array(cellsData.enumerated()), id: \\.offset) { cellIndex, cellData in').or include('index: index, data: data)')
      end
      # The item address counts as the tag does (round 7; it restarted per
      # section until jsonui-cli 1.9.0) — as kjui's pager tag and rjui's id do.
      expect(body).to include(".accessibilityIdentifier(\"pager_item_\\(#{tag})\")")
      (0...counts[k]).map { |i| offset + i }
    end
  end

  describe 'the tags of every page' do
    it 'count across the drawn sections: section 2 starts where section 1 ends' do
      expect(tags(convert('sections' => PAGING_FOUR_SECTIONS.values_at(0, 2)), [2, 3])).to eq([0, 1, 2, 3, 4])
    end

    it 'a section that draws no cell adds no page and no tag' do
      # Data section 1 (header only) holds 5 cells: none is a page.
      expect(tags(convert('sections' => PAGING_FOUR_SECTIONS), [2, 5, 3, 1])).to eq([0, 1, 2, 3, 4, 5])
    end

    it 'fewer data sections than declared ones: the pages there are, numbered from 0' do
      expect(tags(convert('sections' => PAGING_FOUR_SECTIONS), [2, 5])).to eq([0, 1])
    end

    it 'the same with cellIdProperty (the identified-items loop)' do
      expect(tags(convert('sections' => PAGING_FOUR_SECTIONS.values_at(0, 2), 'cellIdProperty' => 'id'), [2, 3])).to eq([0, 1, 2, 3, 4])
    end
  end

  describe 'the class-list shape: one section' do
    it 'a CollectionDataSource: the first data section, a page per cell' do
      code = convert('cellClasses' => ['ACell'])
      expect(code).to include('if let dataSource = data.rows, let cellsData = dataSource.sections.first?.cells?.data {')
      expect(code.scan('ACellView(data: { () -> [String: Any] in var refreshed = cellData; ').size).to eq(1)
      expect(code).to include('.tag(cellIndex)')
    end

    it 'a declared list: its elements' do
      node = { 'type' => 'Collection', 'id' => 'pager', 'layout' => 'horizontal', 'paging' => true, 'items' => '@{rows}',
               'cellClasses' => ['ACell'] }
      code = described_class.new(node, 0, nil, nil, [{ 'name' => 'rows', 'class' => '[ACellData]', 'defaultValue' => '[]' }]).convert.to_s
      expect(code).to include('if let cellsData = Optional(data.rows.map({ $0.toDictionary() })) {')
      expect(code.scan('ACellView(data: { () -> [String: Any] in var refreshed = cellData; ').size).to eq(1)
    end

    it 'no items: no page (the validator names it)' do
      node = { 'type' => 'Collection', 'id' => 'pager', 'layout' => 'horizontal', 'paging' => true, 'cellClasses' => ['ACell'] }
      expect(described_class.new(node).convert.to_s).not_to include('ACellView')
    end
  end

  # From jsonui-cli 1.9.6 a bound currentPage outside the pages is clamped and
  # written back (the `.onChange` block below; ticket
  # sjui-dynamic-pager-does-not-write-back-a-clamped-page). Otherwise the emit
  # it always had.
  it 'one declared section: the emit it always had (the faces carousels shape)' do
    node = { 'type' => 'Collection', 'id' => 'carousel', 'layout' => 'horizontal', 'paging' => true, 'items' => '@{cards}',
             'currentPage' => '@{currentPage}', 'itemSpacing' => 8, 'sections' => [{ 'cell' => 'card_cell' }],
             'cellClasses' => ['card_cell'] }
    expect(described_class.new(node).convert.to_s).to eq(<<~'SWIFT'.chomp)
      TabView(selection: $data.currentPage) {
          if let dataSource = data.cards, dataSource.sections.count > 0 {
              let section = dataSource.sections[0]
              if let cellsData = section.cells?.data {
                  ForEach(Array(cellsData.enumerated()), id: \.offset) { cellIndex, cellData in
                      CardCellView(data: { () -> [String: Any] in var refreshed = cellData; refreshed["cellId"] = CellIdGenerator.autoId(from: cellData, primaryKey: cellData["cellId"] != nil ? "cellId" : "cellId", fallbackIndex: cellIndex); return refreshed }()).equatable()
                          .padding(.horizontal, 4.0)
                          .accessibilityIdentifier("carousel_item_\(cellIndex)")
                          .tag(cellIndex)
                  }
              }
          }
      }
          .tabViewStyle(.page(indexDisplayMode: .never))
          .onChange(of: data.currentPage) { oldValue, newValue in
          let lastPage = max([((data.cards?.sections ?? []).count > 0 ? ((data.cards?.sections ?? [])[0].cells?.data ?? []) : [])].reduce(0) { $0 + $1.count } - 1, 0)
          let clamped = min(max(newValue, 0), lastPage)
          if clamped != newValue {
              data.currentPage = clamped
              return
          }
          guard (0...lastPage).contains(oldValue) else { return }
      }
          .accessibilityIdentifier("carousel")
    SWIFT
  end

  # A pager's common modifiers are emitted once (ticket
  # sjui-pager-emits-its-common-modifiers-twice): `generate_paging_horizontal`
  # applied them and then `convert_non_responsive` applied them again, so
  # `.frame(` and the padding / margin stages came out twice — and stacked
  # paddings add up in SwiftUI (a `topMargin: 24` drew 48pt).
  describe 'the common modifiers of a pager' do
    PAGER_NODE = { 'type' => 'Collection', 'id' => 'pager', 'layout' => 'horizontal', 'paging' => true,
                   'items' => '@{cards}', 'currentPage' => '@{currentPage}', 'cellClasses' => ['card_cell'],
                   'width' => 300, 'height' => 44, 'topMargin' => 24, 'padding' => 4 }.freeze

    def once(code, needle)
      expect(code.scan(needle).size).to eq(1), "#{needle.inspect} ×#{code.scan(needle).size} in:\n#{code}"
    end

    it 'the plain pager: `.frame(`, `.padding(4)` and `.padding(.top, 24)` once each' do
      code = described_class.new(PAGER_NODE.dup).convert.to_s
      once(code, '.padding(.top, 24)')
      once(code, '.frame(')
      once(code, '.padding(4)')
    end

    it 'the responsive pager: once per branch' do
      node = PAGER_NODE.merge('responsive' => { 'regular' => { 'topMargin' => 24, 'height' => 200 } })
      code = described_class.new(node).convert.to_s
      branches = code.split(/\} else \{/)
      expect(branches.size).to eq(2), code
      branches.each do |branch|
        once(branch, '.padding(.top, 24)')
        once(branch, '.frame(')
      end
    end
  end

  # The pager without its iOS-only page style, type-checked where the suite's
  # compile arm runs (the macOS SDK has TabView(selection:) but no `.page`):
  # the tag arithmetic and the Int selection.
  it 'the emitted Swift type-checks, the page style aside', :swift_compile do
    list_node = { 'type' => 'Collection', 'id' => 'l', 'layout' => 'horizontal', 'paging' => true, 'items' => '@{list}',
                  'currentPage' => '@{page}', 'cellClasses' => ['ACell'] }
    codes = [convert('sections' => PAGING_FOUR_SECTIONS),
             convert('sections' => PAGING_FOUR_SECTIONS.values_at(0, 2), 'cellIdProperty' => 'id'),
             convert('cellClasses' => ['ACell']),
             described_class.new(list_node, 0, nil, nil, [{ 'name' => 'list', 'class' => '[ACellData]', 'defaultValue' => '[]' }]).convert.to_s]
    styled = codes.map { |code| code.lines.reject { |l| l.include?('.tabViewStyle(.page(') }.join }
    expect(styled.join).not_to include('.page(')
    expect(<<~SWIFT).to compile_as_swift
      #{EmittedSwift::COLLECTION_DATA_SOURCE_STUB}
      #{cell_view_stub('ACellView', 'BCellView', 'CCellView')}
      struct ACellData { var title = ""; func toDictionary() -> [String: Any] { ["title": title] } }
      struct TestData { var rows: CollectionDataSource? = nil; var list: [ACellData] = []; var page: Int = 0 }
      struct EmittedHost: View {
          @State var data = TestData()
          var body: some View {
              VStack {
      #{styled.join("\n")}
              }
          }
      }
    SWIFT
  end

  # The paging style is iOS's: type-checked against the iOS simulator SDK
  # (the macOS one has no `.page`), with the selection bound to an Int.
  describe 'the emitted Swift type-checks for iOS', :swift_compile do
    def ios_sdk
      out, status = Open3.capture2e('xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path')
      status.success? ? out.strip : nil
    end

    it 'the sectioned pager, the class-list pager and the declared-list pager' do
      sdk = ios_sdk
      skip 'no iOS simulator SDK here (xcrun --sdk iphonesimulator)' unless sdk && !sdk.empty?

      list_node = { 'type' => 'Collection', 'id' => 'l', 'layout' => 'horizontal', 'paging' => true, 'items' => '@{list}',
                    'currentPage' => '@{page}', 'cellClasses' => ['ACell'] }
      codes = [convert('sections' => PAGING_FOUR_SECTIONS),
               convert('sections' => PAGING_FOUR_SECTIONS.values_at(0, 2), 'cellIdProperty' => 'id'),
               convert('cellClasses' => ['ACell']),
               described_class.new(list_node, 0, nil, nil, [{ 'name' => 'list', 'class' => '[ACellData]', 'defaultValue' => '[]' }]).convert.to_s]
      source = <<~SWIFT
        import SwiftUI
        #{EmittedSwift::COLLECTION_DATA_SOURCE_STUB}
        #{cell_view_stub('ACellView', 'BCellView', 'CCellView')}
          struct ACellData { var title = ""; func toDictionary() -> [String: Any] { ["title": title] } }
        struct TestData { var rows: CollectionDataSource? = nil; var list: [ACellData] = []; var page: Int = 0 }
        struct EmittedHost: View {
            @State var data = TestData()
            var body: some View {
                VStack {
        #{codes.join("\n")}
                }
            }
        }
      SWIFT
      Tempfile.create(['paging', '.swift']) do |file|
        file.write(source)
        file.flush
        out, status = Open3.capture2e('swiftc', '-typecheck', '-sdk', sdk, '-target', 'arm64-apple-ios17.0-simulator', file.path)
        expect(status.success?).to be(true), "#{out}\n#{source}"
      end
    end
  end
end
