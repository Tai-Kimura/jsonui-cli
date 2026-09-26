# frozen_string_literal: true

require 'swiftui/views/collection_converter'

# Two or more sections in one Collection (4f round 9):
# - With cellIdProperty, a section after the first gives its cells ids of
#   their own — "<section>:" + the key. Keys two sections share were one id to
#   the lazy stack / TabView the sections share, which dropped the later
#   section's cell, as `\.offset` did before 9ef11908. A scrollTo names a cell
#   by its key, so a later section's cell takes the key as its `.id`.
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

    it "with scrollTo, a later section's cell carries its key as .id; section 0 does not need one" do
      b = blocks(convert('cellIdProperty' => 'key', 'scrollTo' => '@{target}'))
      key = '.id((cell.data["cellId"] as? String) ?? (cell.data["key"] as? String) ?? "\\(cell.index)")'
      expect(b[0]).not_to include('.id(')
      expect(b[2]).to include(key)
      expect(b[3]).to include(key)
      expect(convert('cellIdProperty' => 'key')).not_to include('.id(')
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

  it 'type-checks on every route, with and without cellIdProperty', :swift_compile do
    stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + EmittedSwift::COLLECTION_STACK_VIEW_STUB +
            cell_view_stub('ACellView', 'BCellView', 'CCellView', 'HCellView') +
            "struct FlowLayout<Content: View>: View { let content: () -> Content\n" \
            "  init(alignment: HorizontalAlignment, horizontalSpacing: CGFloat, verticalSpacing: CGFloat, @ViewBuilder content: @escaping () -> Content) { self.content = content }\n" \
            "  var body: some View { VStack { content() } } }\n"
    codes = section_scroll_routes.values.flat_map do |extra|
      [convert(extra.merge('scrollTo' => '@{target}')), convert(extra.merge('scrollTo' => '@{key}', 'cellIdProperty' => 'key'))]
    end
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}",
                           data: ['var rows: CollectionDataSource? = nil', 'var target: Int = 0', 'var key: String = ""'],
                           stubs: stubs)).to compile_as_swift
  end
end
