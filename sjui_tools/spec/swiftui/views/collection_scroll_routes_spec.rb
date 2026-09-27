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
# - a String with no cellIdProperty: a cell's cellId is its key — its loop id
#   the cellId when no cell before it has it, else its place (round 15);
# - an Int with cellIdProperty (round 14): the value's declared class says
#   what it names, cellIdProperty only what a key is — an Int is a cell's
#   place on every route. Until jsonui-cli 1.9.0 cellIdProperty made every
#   value a key: the class-list List and the pager did not compile
#   (`String? == Int`), the other routes scrolled nowhere.
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

  # Round 16: cellIdProperty is the class-list cells' identity too (the
  # SSoT: "unique ID for ForEach identity"), by the keyed loops' rule — the
  # key in its data section, [sectionIndex, key], when no earlier cell of the
  # section has it, else the place — and a scrollTo goes to that id (no
  # `.id`). Until jsonui-cli 1.9.0 the class-list loop's ids were the
  # offsets whatever cellIdProperty said, and a scroll went to
  # `.id(IndexPath(...))`.
  describe 'the class-list List with cellIdProperty' do
    it "its loop ids are the keys in their data section, else the places; a scrollTo goes to the found cell's loop id" do
      [[STR, 'cellId', 'key == cellId'], [INT, 'index', 'place == index'], [[], nil, nil]].each do |props, recv, match|
        node = CLASS_LIST.merge('cellIdProperty' => 'key')
        node = node.merge('scrollTo' => nil) if props.empty?
        code, = emit(node, props)
        expect(code).to include('let cells = cellsData.enumerated().map { (cellIndex: $0.offset, cellData: $0.element) }')
        expect(code).to include('if let key = ((cell.cellData["cellId"] as? String) ?? (cell.cellData["key"] as? String)), seen.insert(key).inserted { ' \
                                'return AnyHashable([AnyHashable(sectionIndex), AnyHashable(key)]) }')
        expect(code).to include('return AnyHashable(IndexPath(item: cell.cellIndex, section: sectionIndex))')
        expect(code).to include('ForEach(zip(ids, cells).map { pair in (id: pair.0, cell: pair.1) }, id: \\.id) { item in')
        expect(code).not_to include('ForEach(Array(cellsData.enumerated()), id: \\.offset)')
        expect(code).not_to include('.id(')
        next unless recv

        expect(code).to include(".onChange(of: data.target) { _, #{recv} in")
        expect(code).to include("if #{match} {")
        expect(code).to include('scrollProxy.scrollTo(found, anchor:')
      end
    end

    it 'control: with no cellIdProperty the loop is the offsets, and a scroll goes to .id(IndexPath(...))' do
      code, = emit(CLASS_LIST, INT)
      expect(code).to include('ForEach(Array(cellsData.enumerated()), id: \\.offset) { cellIndex, cellData in')
      expect(code).to include('.id(IndexPath(item: cellIndex, section: sectionIndex))')
      expect(code).not_to include('let ids')
    end

    it 'type-checks with a String, an Int, none, and autoChangeTrackingId', :swift_compile do
      stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + EmittedSwift::COLLECTION_STACK_VIEW_STUB + cell_view_stub('ACellView') +
              "extension Array where Element == [String: Any] {\n" \
              "  func reconfigured(cellIdProperty: String?, autoChangeTrackingId: Bool) -> [[String: Any]] { self } }\n"
      shapes = [[{}, STR], [{}, INT], [{ 'scrollTo' => nil }, []], [{ 'autoChangeTrackingId' => true }, STR],
                [{ 'autoChangeTrackingId' => true }, INT], [{ 'columns' => 2 }, STR]]
      views = shapes.each_with_index.map do |(extra, props), i|
        code, state = emit(CLASS_LIST.merge('cellIdProperty' => 'key', 'id' => "keyedClass#{i}").merge(extra), props)
        target = props.empty? ? '' : (props.first['class'] == 'String' ? 'var target: String = ""' : 'var target: Int = 0')
        <<~SWIFT
          struct KeyedClass#{i}Data { var rows: CollectionDataSource? = nil; #{target} }
          struct KeyedClass#{i}: View {
              @State var data = KeyedClass#{i}Data()
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
      expect(keyed).to include("let key = ((cell[\"cellId\"] as? String) ?? (cell[\"key\"] as? String))\n")
      expect(keyed).to include("if key == cellId {\n")
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
    # Round 15: the keyed loops' rule (collection_section_scroll_ids_spec) on
    # the cellIds. Until jsonui-cli 1.9.0 a cell took its cellId as `.id`
    # inside loops of offsets — "<section>:<offset>" Strings after section 0,
    # which a String such as "1:3" reached — and two cells of a section with
    # one cellId had one `.id`.
    it "is a cell's cellId: its loop id is the cellId when no cell before it has it, else its place" do
      code, = emit({ 'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell' }] }, STR)
      key = 'if let key = (cell.data["cellId"] as? String), seen.insert(key).inserted { return AnyHashable(key) }'
      expect(code).to include("var seen = Set<String>()\n")
      expect(code).to include('let earlierKeys = Set([0].map { dataSource.sections[$0] }.flatMap { ($0.cells?.data ?? []).compactMap { $0["cellId"] as? String } })')
      expect(code).to include('var seen = earlierKeys')
      expect(code.scan(key).size).to eq(2)
      expect(code).to include('return AnyHashable(IndexPath(item: cell.index, section: 0))')
      expect(code).to include('return AnyHashable(IndexPath(item: cell.index, section: 1))')
      expect(code.scan('ForEach(zip(targets, items).map { pair in (target: pair.0, cell: pair.1) }, id: \\.target) { item in').size).to eq(2)
      expect(code).not_to include('.id(')
      expect(code).not_to include('$0.offset')
      expect(code).not_to include('id: \\.offset')
      expect(code).not_to include('sectionStart')
      expect(code).to include('.onChange(of: data.target) { _, cellId in')
      expect(code).to include('scrollProxy.scrollTo(cellId, anchor: .bottom)')
    end

    it 'control: an Int keeps the counted ids' do
      code, = emit({ 'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell' }] }, INT)
      expect(code).to include('.id(cellIndex)')
      expect(code).not_to include('AnyHashable')
    end
  end

  # Round 15: with autoChangeTrackingId a cell's key is its enriched cellId
  # on every path — the keyed loops read their cells `.reconfigured(...)`,
  # and so do the lookups. Until jsonui-cli 1.9.0 the pager's and the
  # class-list List's compared the data's own key: the String a list reached
  # was no key there, and the data's key reached a page no list would.
  describe 'autoChangeTrackingId: the lookups read the enriched cellId, as the loops do' do
    AUTO = { 'cellIdProperty' => 'key', 'autoChangeTrackingId' => true }.freeze
    ENRICH = '.reconfigured(cellIdProperty: "key", autoChangeTrackingId: true)'

    it 'the pager' do
      code, = emit(PAGER.merge(AUTO), STR)
      secs = '(data.rows?.sections ?? [])'
      expect(code).to include("search: for cells in [(#{secs}.count > 0 ? (#{secs}[0].cells?.data ?? []) : [])#{ENRICH}, " \
                              "(#{secs}.count > 1 ? (#{secs}[1].cells?.data ?? []) : [])#{ENRICH}] {")
      expect(code).to include('if ((cell["cellId"] as? String) ?? (cell["key"] as? String)) == cellId { found = page; break search }')
    end

    it 'the class-list List' do
      code, = emit(CLASS_LIST.merge(AUTO), STR)
      expect(code).to include("for (cellIndex, cell) in (section.cells?.data ?? [])#{ENRICH}.enumerated() {")
    end

    it 'control: an Int counts cells and reads no key; with no autoChangeTrackingId nothing is enriched' do
      [[PAGER.merge(AUTO), INT], [PAGER.merge('cellIdProperty' => 'key'), STR],
       [CLASS_LIST.merge('cellIdProperty' => 'key'), STR]].each do |node, props|
        code, = emit(node, props)
        lookup = code.lines.grep(/search: for |for \(cellIndex, /)
        expect(lookup.size).to be >= 1, node.keys.join(' ')
        expect(lookup.join).not_to include('.reconfigured('), node.keys.join(' ')
      end
    end

    it 'type-checks: the pager, the class-list List and a list, a String with autoChangeTrackingId', :swift_compile do
      stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + EmittedSwift::COLLECTION_STACK_VIEW_STUB +
              cell_view_stub('ACellView', 'BCellView') +
              "extension Array where Element == [String: Any] {\n" \
              "  func reconfigured(cellIdProperty: String?, autoChangeTrackingId: Bool) -> [[String: Any]] { self } }\n"
      views = [PAGER, CLASS_LIST, { 'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell' }] }].each_with_index.map do |node, i|
        code, state = emit(node.merge(AUTO).merge('id' => "auto#{i}"), STR)
        code = code.lines.reject { |l| l.include?('.tabViewStyle(.page(') }.join
        <<~SWIFT
          struct Auto#{i}Data { var rows: CollectionDataSource? = nil; var target: String = "" }
          struct Auto#{i}: View {
              @State var data = Auto#{i}Data()
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

  # scrollAnchor says where the target lands along the scroll axis (the SSoT's
  # Collection.scrollAnchor): on a horizontal Collection, top / center /
  # bottom are `.leading` / `.center` / `.trailing` (4f ruling 2026-09-27).
  # Until jsonui-cli 1.9.0 they were `.top` / `.center` / `.bottom`, whose x
  # is 0.5: every anchor put the target's middle at the viewport's middle —
  # measured on the codegen host (ScrollRouteProbeUITests' seventh page).
  describe "a horizontal Collection's scrollAnchor" do
    it 'is the leading edge, the middle or the trailing edge along the scroll axis, on every horizontal spelling' do
      spellings = { 'layout' => { 'layout' => 'horizontal' }, 'orientation' => { 'orientation' => 'horizontal' },
                    'horizontalScroll' => { 'horizontalScroll' => true }, 'lanes' => { 'layout' => 'horizontal', 'columns' => 2 } }
      spellings.each do |name, extra|
        { 'top' => '.leading', 'center' => '.center', 'bottom' => '.trailing', nil => '.trailing' }.each do |anchor, point|
          node = { 'sections' => [{ 'cell' => 'ACell' }] }.merge(extra)
          node = node.merge('scrollAnchor' => anchor) if anchor
          code, = emit(node, INT)
          expect(code).to include("scrollProxy.scrollTo(index, anchor: #{point})"), "#{name} #{anchor.inspect}"
          expect(code).not_to match(/anchor: \.(top|bottom)\b/), "#{name} #{anchor.inspect}"
        end
      end
    end

    it 'control: a vertical Collection keeps .top / .center / .bottom' do
      { 'top' => '.top', 'center' => '.center', 'bottom' => '.bottom' }.each do |anchor, point|
        code, = emit({ 'sections' => [{ 'cell' => 'ACell' }], 'scrollAnchor' => anchor }, INT)
        expect(code).to include("scrollProxy.scrollTo(index, anchor: #{point})"), anchor
      end
    end
  end

  describe 'an Int with cellIdProperty: the declared class decides' do
    SECTIONED = { 'sections' => [{ 'cell' => 'ACell' }, { 'header' => 'HCell' }, { 'cell' => 'BCell' }] }.freeze
    KEYED = { 'cellIdProperty' => 'key' }.freeze

    it 'the class-list List and the pager look the Int up as a place, as with no cellIdProperty' do
      list, = emit(CLASS_LIST.merge(KEYED), INT)
      expect(list).to include('.onChange(of: data.target) { _, index in')
      # The class-list's loop ids are keyed (round 16): the place's cell, its
      # loop id.
      expect(list).to include("if place == index {\n")
      expect(list).to include('if let key, first { found = AnyHashable([AnyHashable(sectionIndex), AnyHashable(key)]) } ' \
                              'else { found = AnyHashable(IndexPath(item: cellIndex, section: sectionIndex)) }')
      expect(list).not_to include('as? String)) == index')
      pager, = emit(PAGER.merge(KEYED), INT)
      expect(pager).to include('.onChange(of: data.target) { _, index in')
      expect(pager).to include('if page == index { found = page; break search }')
      expect(pager).not_to include('as? String)) == index')
    end

    # The cells' loop ids are their keys, else their places
    # (collection_section_scroll_ids_spec): the Int is looked up by the
    # loops' own rule — the drawn sections in order, the key when no cell
    # before it has it — and the scroll goes to that id.
    it "a keyed loop looks the Int up and scrolls to the cell's own loop id" do
      code, = emit(SECTIONED.merge(KEYED), INT)
      secs = '(data.rows?.sections ?? [])'
      expect(code).to include('.onChange(of: data.target) { _, index in')
      expect(code).to include("search: for (sectionIndex, cells) in [(0, (#{secs}.count > 0 ? (#{secs}[0].cells?.data ?? []) : [])), " \
                              "(2, (#{secs}.count > 2 ? (#{secs}[2].cells?.data ?? []) : []))] {")
      expect(code).to include('let first = key.map { seen.insert($0).inserted } ?? false')
      expect(code).to include('if let key, first { found = AnyHashable(key) } else { found = AnyHashable(IndexPath(item: cellIndex, section: sectionIndex)) }')
      expect(code).to include('scrollProxy.scrollTo(found, anchor: .bottom)')
      expect(code).not_to include('scrollProxy.scrollTo(index')
      auto, = emit(SECTIONED.merge(KEYED).merge('autoChangeTrackingId' => true), INT)
      expect(auto).to include('[0].cells?.data ?? []) : []).reconfigured(cellIdProperty: "key", autoChangeTrackingId: true))')
    end

    it 'control: a String with cellIdProperty scrolls to the value; a value of no declared class is a String with cellIdProperty' do
      code, = emit(SECTIONED.merge(KEYED), STR)
      expect(code).to include('.onChange(of: data.target) { _, cellId in')
      expect(code).to include('scrollProxy.scrollTo(cellId, anchor: .bottom)')
      expect(code).not_to include('search:')
      undeclared, = emit(SECTIONED.merge(KEYED), [])
      expect(undeclared).to include('scrollProxy.scrollTo(cellId, anchor: .bottom)')
    end

    it 'type-checks on every route with an Int and cellIdProperty, with and without autoChangeTrackingId', :swift_compile do
      routes = [SECTIONED, SECTIONED.merge('lazy' => 'none'), SECTIONED.merge('columns' => 2), SECTIONED.merge('layout' => 'flow'),
                SECTIONED.merge('listStyle' => 'plain'), SECTIONED.merge('layout' => 'horizontal'), PAGER, PAGER.merge('currentPage' => '@{page}'),
                CLASS_LIST, CLASS_LIST.merge('columns' => 2), { 'sections' => [{ 'cell' => 'ACell' }] }]
      stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + EmittedSwift::COLLECTION_STACK_VIEW_STUB +
              cell_view_stub('ACellView', 'BCellView', 'HCellView') +
              "struct FlowLayout<Content: View>: View { let content: () -> Content\n" \
              "  init(alignment: HorizontalAlignment, horizontalSpacing: CGFloat, verticalSpacing: CGFloat, @ViewBuilder content: @escaping () -> Content) { self.content = content }\n" \
              "  var body: some View { VStack { content() } } }\n" \
              "extension Array where Element == [String: Any] {\n" \
              "  func reconfigured(cellIdProperty: String?, autoChangeTrackingId: Bool) -> [[String: Any]] { self } }\n"
      views = routes.product([{}, { 'autoChangeTrackingId' => true }]).each_with_index.map do |(node, auto), i|
        code, state = emit(node.merge(KEYED).merge(auto).merge('id' => "keyed#{i}"), INT)
        code = code.lines.reject { |l| l.include?('.tabViewStyle(.page(') }.join
        <<~SWIFT
          struct Keyed#{i}Data { var rows: CollectionDataSource? = nil; var target: Int = 0; var page: Int = 0 }
          struct Keyed#{i}: View {
              @State var data = Keyed#{i}Data()
          #{state.map { |l| "    #{l}" }.join("\n")}
              var body: some View {
          #{code.lines.map { |l| "        #{l}" }.join}
              }
          }
        SWIFT
      end
      expect(views.size).to eq(22)
      expect("#{EmittedSwift::LIBRARY_STUBS}\n#{stubs}\n#{views.join("\n")}").to compile_as_swift
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
