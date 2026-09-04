# frozen_string_literal: true

require 'swiftui/views/collection_converter'

# Characterization of CollectionConverter emit paths that collection_converter_spec
# does not exercise: sections-based verticals, paging, non-lazy (`lazy: "none"`)
# variants, legacy cellClasses fallbacks, and the scroll-container attrs.
# Assertions capture the current emitted Swift verbatim-by-fragment; a failure
# here means the emitted structure changed — decide deliberately, don't loosen.
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  def convert(component, data_properties = [])
    described_class.new(component, 0, nil, nil, data_properties).convert
  end

  describe 'vertical single-column with sections (CollectionStackView path)' do
    it 'delegates the outer container to CollectionStackView and unwraps the optional data source' do
      code = convert(
        { 'type' => 'Collection', 'columns' => 1,
          'sections' => [{ 'cell' => 'FooCell' }], 'items' => '@{items}' }
      )
      expect(code).to include('CollectionStackView(')
      expect(code).to include('mode: .lazy')
      expect(code).to include('axis: .vertical')
      expect(code).to include('if let dataSource = data.items, dataSource.sections.count > 0 {')
      expect(code).to include('let section = dataSource.sections[0]')
      expect(code).to include('FooCellView(data: cellData).equatable()')
    end
  end

  describe 'legacy List with footer but no header' do
    it 'appends the footer view after the cells inside the List' do
      code = convert(
        { 'type' => 'Collection', 'columns' => 1,
          'cellClasses' => ['ItemCell'], 'footerClasses' => ['MyFooter'] }
      )
      expect(code).to include('List {')
      expect(code).to include('MyFooterView()')
      expect(code).to include('.listStyle(PlainListStyle())')

      # This example used to assert
      # `data.collectionDataSource.getCellData(for: "ItemCell")`. That string
      # is not Swift: nothing declares `collectionDataSource`, and
      # `CollectionDataSource`'s public API is `sections` / `init` /
      # `reconfigured` — there is no lookup-by-cell-name method. The
      # characterization pinned emitted TEXT that no compiler had ever read,
      # so it stayed green for years while the branch could not build.
      # A Collection with no `items` now emits no cells, and the layout is
      # named by a validator warning.
      expect(code).not_to include('getCellData')
      expect(code).to include("no 'items' data source declared")
    end
  end

  describe 'horizontal paging (TabView path)' do
    let(:component) do
      { 'type' => 'Collection', 'id' => 'pager', 'layout' => 'horizontal',
        'paging' => true, 'itemSpacing' => 8,
        'currentPage' => '@{page}', 'onValueChange' => '@{onPageChange}',
        'sections' => [{ 'cell' => 'PageCell' }], 'items' => '@{items}' }
    end

    it 'emits a selection-bound TabView with page style' do
      code = convert(component)
      expect(code).to include('TabView(selection: $data.page) {')
      expect(code).to include('.tabViewStyle(.page(indexDisplayMode: .never))')
    end

    it 'tags cells, halves the item spacing as padding, and stamps the item identifier' do
      code = convert(component)
      expect(code).to include('PageCellView(data: cellData).equatable()')
      expect(code).to include('.padding(.horizontal, 4.0)')
      expect(code).to include('.accessibilityIdentifier("pager_item_\\(cellIndex)")')
      expect(code).to include('.tag(cellIndex)')
    end

    it 'guards the page-change callback against the feedback loop' do
      code = convert(component)
      expect(code).to include('.onChange(of: data.page) { oldValue, newValue in')
      expect(code).to include('guard oldValue != newValue else { return }')
      expect(code).to include('data.onPageChange?()')
    end

    it 'emits an unbound TabView when currentPage is absent' do
      code = convert(component.reject { |k, _| %w[currentPage onValueChange].include?(k) })
      expect(code).to include('TabView {')
      expect(code).not_to include('.onChange(')
    end
  end

  describe 'multi-section grid with a non-optional data property' do
    it 'indexes each section with a count guard and direct (non-optional) access' do
      code = convert(
        { 'type' => 'Collection', 'id' => 'twosec', 'columns' => 2, 'cellHeight' => 44,
          'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell' }], 'items' => '@{items}' },
        [{ 'name' => 'items', 'defaultValue' => 'CollectionDataSource()' }]
      )
      expect(code).to include('if data.items.sections.count > 0 {')
      expect(code).to include('if data.items.sections.count > 1 {')
      expect(code).to include('let section = data.items.sections[1]')
      expect(code).to include('ACellView(data: cellData).equatable()')
      expect(code).to include('BCellView(data: cellData).equatable()')
      expect(code).to include('.frame(height: 44, alignment: .topLeading)')
      expect(code).to include('.accessibilityIdentifier("twosec_item_\\(cellIndex)")')
    end
  end

  describe 'sections without an items binding' do
    it 'emits an empty grid with the no-binding comment' do
      code = convert(
        { 'type' => 'Collection', 'id' => 'fb', 'columns' => 2,
          'cellWidth' => 100, 'cellHeight' => 50, 'sections' => [{ 'cell' => 'LegacyCell' }] }
      )
      expect(code).to include('LazyVGrid(')
      expect(code).to include('// No items binding specified')
      expect(code).to include('.accessibilityIdentifier("fb")')
    end

    it 'renders static header/footer views around the empty grid' do
      code = convert(
        { 'type' => 'Collection', 'columns' => 2,
          'sections' => [{ 'cell' => 'XCell', 'header' => 'HeadView', 'footer' => 'FootView' }] }
      )
      expect(code).to include("HeadView()\n")
      expect(code).to include('// No items binding specified')
      expect(code).to include("FootView()\n")
    end
  end

  describe 'legacy cellClasses grid with items binding' do
    it 'unwraps the optional data source and renders the declared cell' do
      # Was pinned as "falls back to the viewName TODO placeholder". That was
      # a faithful characterization of what the code did and a wrong
      # description of what the declaration means: SSoT
      # (`/Collection/cellClasses`) says a single cellClass renders every
      # item, which is what kjui and rjui already did. iOS printed the
      # runtime view name instead, so one layout rendered cells on two faces
      # and debug text on the third.
      code = convert(
        { 'type' => 'Collection', 'id' => 'lg', 'columns' => 2,
          'cellWidth' => 90, 'cellHeight' => 40,
          'cellClasses' => ['GridCell'], 'items' => '@{rows}' }
      )
      expect(code).to include('if let dataSource = data.rows {')
      expect(code).to include('ForEach(Array(dataSource.sections.enumerated()), id: \\.offset) { sectionIndex, section in')
      expect(code).to include('GridCellView(data: cellData)')
      expect(code).not_to include('TODO')
      expect(code).not_to include('Text("\\(viewName)')
      expect(code).to include('.frame(height: 40, alignment: .topLeading)')
    end

    it 'accesses a non-optional property directly' do
      code = convert(
        { 'type' => 'Collection', 'columns' => 2, 'cellClasses' => ['GridCell'], 'items' => '@{rows}' },
        [{ 'name' => 'rows', 'defaultValue' => 'CollectionDataSource()' }]
      )
      expect(code).to include('ForEach(Array(data.rows.sections.enumerated()), id: \\.offset) { sectionIndex, section in')
      expect(code).not_to include('if let dataSource = data.rows {')
    end

    it 'wraps the grid with legacy header/footer classes' do
      code = convert(
        { 'type' => 'Collection', 'columns' => 2, 'cellClasses' => ['CCell'],
          'headerClasses' => ['HClass'], 'footerClasses' => ['FClass'], 'items' => '@{rows}' }
      )
      expect(code).to include("HClassView()\n")
      expect(code).to include("FClassView()\n")
    end
  end

  describe 'scroll container attrs' do
    it 'maps a 2-element containerInset to symmetric EdgeInsets contentMargins' do
      code = convert(
        { 'type' => 'Collection', 'columns' => 2, 'containerInset' => [10, 20],
          'cellClasses' => ['CCell'], 'items' => '@{rows}' }
      )
      expect(code).to include('.contentMargins(.all, EdgeInsets(top: 10, leading: 20, bottom: 10, trailing: 20), for: .scrollContent)')
    end

    it 'maps a 4-element containerInset and scrollableAxes adjustment' do
      code = convert(
        { 'type' => 'Collection', 'columns' => 2, 'containerInset' => [1, 2, 3, 4],
          'contentInsetAdjustmentBehavior' => 'scrollableAxes',
          'cellClasses' => ['CCell'], 'items' => '@{rows}' }
      )
      expect(code).to include('.contentMargins(.all, EdgeInsets(top: 1, leading: 2, bottom: 3, trailing: 4), for: .scrollContent)')
      expect(code).to include('.ignoresSafeArea(edges: .horizontal)')
    end

    it 'maps a 1-element containerInset to uniform EdgeInsets' do
      code = convert(
        { 'type' => 'Collection', 'columns' => 2, 'containerInset' => [7],
          'cellClasses' => ['CCell'], 'items' => '@{rows}' }
      )
      expect(code).to include('.contentMargins(.all, EdgeInsets(top: 7, leading: 7, bottom: 7, trailing: 7), for: .scrollContent)')
    end
  end

  describe 'non-lazy (`lazy: "none"`) variants' do
    it 'flow layout with sections: VStack of per-section FlowLayouts, no ScrollView' do
      code = convert(
        { 'type' => 'Collection', 'id' => 'flw', 'lazy' => 'none', 'layout' => 'flow',
          'sections' => [{ 'cell' => 'TagCell' }], 'items' => '@{tags}' }
      )
      expect(code).not_to include('ScrollView(')
      expect(code).to include('VStack(spacing: 8) {')
      expect(code).to include('if let dataSource = data.tags, dataSource.sections.count > 0 {')
      expect(code).to include('FlowLayout(alignment: .leading, horizontalSpacing: 8, verticalSpacing: 8) {')
      expect(code).to include('TagCellView(data: cellData).equatable()')
      expect(code).to include('.accessibilityIdentifier("flw_item_\\(cellIndex)")')
    end

    it 'flow layout with legacy cellClasses: first-section cells in one FlowLayout' do
      code = convert(
        { 'type' => 'Collection', 'lazy' => 'none', 'layout' => 'flow',
          'cellClasses' => ['TagCell'], 'items' => '@{tags}' }
      )
      expect(code).to include('if let dataSource = data.tags, let cellsData = dataSource.sections.first?.cells?.data {')
      expect(code).to include('FlowLayout(alignment: .leading, horizontalSpacing: 8, verticalSpacing: 8) {')
      expect(code).to include('TagCellView(data: cellData)')
      expect(code).not_to include('.equatable()')
    end

    it 'single column legacy: plain VStack wrapping header, cells, footer' do
      code = convert(
        { 'type' => 'Collection', 'lazy' => 'none', 'columns' => 1,
          'cellClasses' => ['RowCell'], 'headerClasses' => ['HdrC'],
          'footerClasses' => ['FtrC'], 'items' => '@{rows}' }
      )
      expect(code).not_to include('List {')
      expect(code).to include('VStack(alignment: .leading, spacing: 0) {')
      expect(code).to include("HdrCView()\n")
      expect(code).to include("FtrCView()\n")
    end

    it 'grid with sections: data-bound header/footer around a LazyVGrid' do
      code = convert(
        { 'type' => 'Collection', 'id' => 'nlg', 'lazy' => 'none', 'columns' => 2,
          'cellHeight' => 30,
          'sections' => [{ 'cell' => 'GCell', 'header' => 'GHead', 'footer' => 'GFoot' }],
          'items' => '@{rows}' }
      )
      expect(code).to include('VStack(alignment: .leading, spacing: 0) {')
      expect(code).to include('if let headerData = section.header?.data {')
      expect(code).to include('GHeadView(data: headerData)')
      expect(code).to include('if let footerData = section.footer?.data {')
      expect(code).to include('GFootView(data: footerData)')
      expect(code).to include('GCellView(data: cellData).equatable()')
      expect(code).to include('.frame(height: 30, alignment: .topLeading)')
    end

    it 'grid with two sections and a non-optional property: per-index count guards' do
      code = convert(
        { 'type' => 'Collection', 'lazy' => 'none', 'columns' => 2, 'cellWidth' => 80,
          'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell' }], 'items' => '@{rows}' },
        [{ 'name' => 'rows', 'defaultValue' => 'CollectionDataSource()' }]
      )
      expect(code).to include('if data.rows.sections.count > 0 {')
      expect(code).to include('if data.rows.sections.count > 1 {')
      expect(code).to include('let section = data.rows.sections[1]')
      expect(code).to include('ACellView(data: cellData).equatable()')
      expect(code).to include('BCellView(data: cellData).equatable()')
    end

    it 'grid with legacy header/footer classes: bare views around the LazyVGrid' do
      code = convert(
        { 'type' => 'Collection', 'lazy' => 'none', 'columns' => 2,
          'cellClasses' => ['GCell'], 'headerClasses' => ['GH'],
          'footerClasses' => ['GF'], 'items' => '@{rows}' }
      )
      expect(code).to include("GHView()\n")
      expect(code).to include('LazyVGrid(')
      expect(code).to include("}\nGFView()")
      expect(code).not_to include('ScrollView(')
    end
  end
end
