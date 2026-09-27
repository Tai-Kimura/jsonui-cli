# frozen_string_literal: true

require 'swiftui/views/collection_converter'

# Two or more sections in one Collection (4f round 9):
# - With cellIdProperty, a section after the first gives its cells ids of
#   their own — "<section>:" + the key. Keys two sections share were one id to
#   the lazy stack / TabView the sections share, which dropped the later
#   section's cell, as `\.offset` did before 9ef11908. With scrollTo, a
#   cell's loop id is its scroll target instead (4f round 13): its key, else
#   its place — an IndexPath, which no String equals.
# - Without it, a scrolled-to index is a cell's place among the drawn
#   sections' cells: a later section's cells are `.id(sectionStart + index)`.
#   They were `.id(index)`, so every section answered 0…, and scrollTo(n)
#   reached the first section's cell n.
# The first section, and a Collection of one section, emit as before.
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  before(:all) { described_class.superclass.validation_enabled = false }
  after(:all) { described_class.superclass.validation_enabled = true }

  def section_scroll_routes
    { 'list' => {}, 'lazy:none' => { 'lazy' => 'none' }, 'grid' => { 'columns' => 2 },
      'grid, lazy:none' => { 'columns' => 2, 'lazy' => 'none' }, 'flow' => { 'layout' => 'flow' } }
  end

  def convert(extra)
    described_class.new({
      'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}',
      'sections' => [{ 'cell' => 'ACell' }, { 'header' => 'HCell' }, { 'cell' => 'BCell' }, { 'cell' => 'CCell' }]
    }.merge(extra).compact).convert.to_s
  end

  # The emit of each section block: { section index => its text }.
  def blocks(code)
    code.split(/(?=if (?:let dataSource = data\.rows, )?dataSource\.sections\.count > \d+ \{|if data\.rows\.sections\.count > \d+ \{)/)
        .grep(/sections\.count > \d+/).to_h { |b| [b[/sections\.count > (\d+)/, 1].to_i, b] }
  end

  describe 'cellIdProperty: a later section qualifies its keys' do
    it 'on every route: section 0 its keys, sections 2 and 3 "2:" and "3:"' do
      section_scroll_routes.each do |route, extra|
        b = blocks(convert(extra.merge('cellIdProperty' => 'key')))
        expect(b[0]).to include('IdentifiedCellItem(id: (data["cellId"] as? String) ?? (data["key"] as? String) ?? "\\(index)", index: index'), route
        expect(b[2]).to include('IdentifiedCellItem(id: "2:" + ((data["cellId"] as? String) ?? (data["key"] as? String) ?? "\\(index)"), index: index'), route
        expect(b[3]).to include('IdentifiedCellItem(id: "3:" + ('), route
      end
    end

    # With scrollTo a cell's loop id is its scroll target (4f round 13): its
    # key when no cell before it in section order has it — no earlier drawn
    # section (4f ruling 2026-09-27, round 10: scrollTo names the FIRST cell,
    # in section order, whose key it is) and no earlier cell of its own
    # section (round 14) — else its place, an IndexPath: a cell with no key
    # has no key, and no value a scrollTo sends (a String, an Int) equals an
    # IndexPath. Until jsonui-cli 1.9.0 a cell with no key had the loop id
    # "\(index)" ("<section>:\(index)" after section 0) and a later section's
    # cell its key as `.id` inside loop ids "<section>:<key>": on the codegen
    # host (iOS 26.5, ScrollRuleProbeUITests.testACellWithNoKeyAnswersNoKey)
    # the String "3" reached section 0's fourth cell, which has no key, over
    # the later section's cell keyed "3"; "1:7" the later section's eighth
    # cell, which has no key; "1:y2" the later section's cell keyed "y2".
    def keyed_scroll_routes
      section_scroll_routes.merge('sectioned List' => { 'listStyle' => 'plain' }, 'horizontal' => { 'layout' => 'horizontal' },
                                  'pager' => { 'layout' => 'horizontal', 'paging' => true })
    end

    # A section's targets: the cells' keys, each taken by the first cell
    # that has it — `seen` starts from the earlier drawn sections' keys
    # (`earlierKeys`) after section 0 — else the cells' places.
    targets = lambda do |seen, s|
      "let targets: [AnyHashable] = {\n" \
        "#{'X'}var seen = #{seen}\n" \
        "#{'X'}return items.map { cell in\n" \
        "#{'XX'}if let key = ((cell.data[\"cellId\"] as? String) ?? (cell.data[\"key\"] as? String)), seen.insert(key).inserted { return AnyHashable(key) }\n" \
        "#{'XX'}return AnyHashable(IndexPath(item: cell.index, section: #{s}))\n" \
        "#{'X'}}\n" \
        "}()\n" \
        "ForEach(zip(targets, items).map { pair in (target: pair.0, cell: pair.1) }, id: \\.target) { item in\n" \
        "#{'X'}let cell = item.cell\n"
    end
    # The block's text with its indentation read relative to the targets line.
    def relative(block)
      lines = block.lines
      start = lines.index { |l| l.include?('let targets: [AnyHashable] = {') }
      return '' unless start

      base = lines[start][/\A */].size
      lines[start, 9].map { |l| l.sub(/\A {#{base}}/, '').gsub(/\G {4}/, 'X') }.join
    end

    it "with scrollTo, on every route a cell's loop id is its key, else its place — the key the first cell's in section order" do
      keyed_scroll_routes.each do |route, extra|
        b = blocks(convert(extra.merge('cellIdProperty' => 'key', 'scrollTo' => '@{target}')))
        expect(relative(b[0])).to eq(targets.call('Set<String>()', 0)), route
        expect(relative(b[2])).to eq(targets.call('earlierKeys', 2)), route
        expect(relative(b[3])).to eq(targets.call('earlierKeys', 3)), route
        # The earlier drawn sections' keys: 0 before section 2 (1 draws no
        # cell), 0 and 2 before 3 — keys only, a cell with no key adds none.
        keys = '.flatMap { ($0.cells?.data ?? []).compactMap { (($0["cellId"] as? String) ?? ($0["key"] as? String)) } })'
        expect(b[2]).to include("let earlierKeys = Set([0].map { dataSource.sections[$0] }#{keys}"), route
        expect(b[3]).to include("let earlierKeys = Set([0, 2].map { dataSource.sections[$0] }#{keys}"), route
      end
    end

    # The red arm of round 13: the String "3" against a section with no keys.
    # Its cells' index reaches no scroll target — no loop over the
    # IdentifiedCellItems' String ids (whose fallback is "\(index)"), no `.id`
    # — and the one place an index is spelled into a String is that
    # IdentifiedCellItem id, which is no longer the loop's identity.
    it 'with scrollTo, a cell with no key answers no String: its index is spelled into no loop id and no .id' do
      keyed_scroll_routes.each do |route, extra|
        code = convert(extra.merge('cellIdProperty' => 'key', 'scrollTo' => '@{target}'))
        expect(code).not_to include('ForEach(items) {'), route
        expect(code).not_to include('.id('), route
        spelled = code.lines.select { |l| l.include?('\\(index)') || l.include?('\\(cell.index)') }
        expect(spelled.reject { |l| l.include?('IdentifiedCellItem(id: ') || l.include?('.accessibilityIdentifier(') }).to eq([]), route
      end
    end

    # Round 14: two cells of one section with one key. The first takes the
    # key; the later is its place — no two views answer one id, and a String
    # reaches the first by construction. Until jsonui-cli 1.9.0 both loop ids
    # were the key, and which view a scrollTo reached was SwiftUI's choice
    # (section 0: `(target: key.map { AnyHashable($0) } ?? place)`; after it
    # the key unless `earlierKeys` had it).
    it 'with scrollTo, a key already taken in its own section is no loop id: a later cell with it is its place' do
      keyed_scroll_routes.each do |route, extra|
        b = blocks(convert(extra.merge('cellIdProperty' => 'key', 'scrollTo' => '@{target}')))
        [0, 2, 3].each do |s|
          expect(b[s]).to include(', seen.insert(key).inserted { return AnyHashable(key) }'), "#{route} #{s}"
          expect(b[s]).not_to include('.map { AnyHashable($0) }'), "#{route} #{s}"
          expect(b[s]).not_to include('earlierKeys.contains('), "#{route} #{s}"
        end
      end
    end

    # Round 15: with no scrollTo a loop's ids are the IdentifiedCellItem ids
    # as before — the key, else "\(index)"; "<section>:" after section 0 —
    # except that an id an earlier cell of the loop has is the later cell's
    # place: no two cells of a loop share an id, and the first keeps its own.
    # Until jsonui-cli 1.9.0 the loop was ForEach(items), and two cells with
    # one key were one id to SwiftUI.
    it 'with no scrollTo, a loop id is the IdentifiedCellItem id unless an earlier cell of the loop has it: then its place' do
      keyed_scroll_routes.each do |route, extra|
        code = convert(extra.merge('cellIdProperty' => 'key'))
        b = blocks(code)
        [0, 2, 3].each do |s|
          expect(b[s]).to include("let ids: [AnyHashable] = {\n#{' ' * (b[s][/^( *)let ids/, 1].to_s.size + 4)}var seen = Set<String>()\n"), "#{route} #{s}"
          expect(b[s]).to include("return items.map { cell in seen.insert(cell.id).inserted ? AnyHashable(cell.id) : " \
                                  "AnyHashable(IndexPath(item: cell.index, section: #{s})) }"), "#{route} #{s}"
          expect(b[s]).to include('ForEach(zip(ids, items).map { pair in (id: pair.0, cell: pair.1) }, id: \\.id) { item in'), "#{route} #{s}"
        end
        expect(code).not_to include('ForEach(items) {'), route
        expect(code).not_to include('let targets'), route
        expect(code).not_to include('.id('), route
        expect(code).not_to include('earlierKeys'), route
      end
    end
  end

  describe 'no cellIdProperty: a scrolled-to index counts across the sections' do
    it 'on every route: .id(cellIndex) in section 0, .id(sectionStart + cell.index) after it' do
      section_scroll_routes.each do |route, extra|
        b = blocks(convert(extra.merge('scrollTo' => '@{target}')))
        expect(b[0]).to include('.id(cellIndex)'), route
        expect(b[2]).to include('let sectionStart = (dataSource.sections[0].cells?.data.count ?? 0)'), route
        expect(b[2]).to include('.id(sectionStart + cell.index)'), route
        # The header-only section 1 draws no cell: it is not counted.
        expect(b[3]).to include('let sectionStart = (dataSource.sections[0].cells?.data.count ?? 0) + ' \
                                '(dataSource.sections[2].cells?.data.count ?? 0)'), route
      end
    end

    it 'control: no scrollTo, no sectionStart and no .id' do
      code = convert({})
      expect(code).not_to include('sectionStart')
      expect(code).not_to include('.id(')
    end

    it 'control: one section emits as before' do
      code = described_class.new({ 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'scrollTo' => '@{target}',
                                   'sections' => [{ 'cell' => 'ACell' }] }).convert.to_s
      expect(code).to include('.id(cellIndex)')
      expect(code).not_to include('sectionStart')
    end
  end

  # The ids are only half: a scrollTo reaches them through the ScrollViewReader
  # around the route's scroll container, and the value's change is what
  # scrolls (`.onChange(of:)` — the value it is drawn with scrolls nowhere).
  # The flow had the ids and no reader until jsonui-cli 1.9.0, so a scrollTo
  # drew nothing there. `lazy: none` has no scroll container of its own.
  it 'on every lazy route the value reaches the cells: a ScrollViewReader, and its change scrolls' do
    routes = section_scroll_routes.reject { |route, _| route.include?('lazy:none') }
                                  .merge('sectioned List' => { 'listStyle' => 'plain' }, 'horizontal' => { 'layout' => 'horizontal' })
    routes.each do |route, extra|
      [['@{target}', {}, 'index'], ['@{key}', { 'cellIdProperty' => 'key' }, 'cellId']].each do |value, more, name|
        code = convert(extra.merge(more).merge('scrollTo' => value))
        expect(code).to include('ScrollViewReader { scrollProxy in'), "#{route} #{name}"
        expect(code).to include(".onChange(of: data.#{value[2..-2]}) { _, #{name} in"), "#{route} #{name}"
        expect(code).to include("scrollProxy.scrollTo(#{name}, anchor: .bottom)"), "#{route} #{name}"
        expect(code).not_to include('initial:'), "#{route} #{name}"
      end
    end
    expect(convert('lazy' => 'none', 'scrollTo' => '@{target}')).not_to include('ScrollViewReader')
  end

  it 'type-checks on every route, with and without cellIdProperty', :swift_compile do
    stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + EmittedSwift::COLLECTION_STACK_VIEW_STUB +
            cell_view_stub('ACellView', 'BCellView', 'CCellView', 'HCellView') +
            "struct FlowLayout<Content: View>: View { let content: () -> Content\n" \
            "  init(alignment: HorizontalAlignment, horizontalSpacing: CGFloat, verticalSpacing: CGFloat, @ViewBuilder content: @escaping () -> Content) { self.content = content }\n" \
            "  var body: some View { VStack { content() } } }\n"
    codes = section_scroll_routes.values.flat_map do |extra|
      [convert(extra.merge('scrollTo' => '@{target}')), convert(extra.merge('scrollTo' => '@{key}', 'cellIdProperty' => 'key')),
       convert(extra.merge('cellIdProperty' => 'key'))]
    end
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}",
                           data: ['var rows: CollectionDataSource? = nil', 'var target: Int = 0', 'var key: String = ""'],
                           stubs: stubs)).to compile_as_swift
  end
end
