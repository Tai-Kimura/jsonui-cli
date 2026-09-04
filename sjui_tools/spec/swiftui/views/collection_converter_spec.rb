# frozen_string_literal: true

require 'swiftui/views/collection_converter'

RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#extract_view_name' do
    let(:converter) { described_class.new({ 'type' => 'Collection' }) }

    it 'converts CollectionViewCell suffix to View' do
      result = converter.send(:extract_view_name, 'MyItemCollectionViewCell')
      expect(result).to eq('MyItemView')
    end

    it 'handles hash class info' do
      result = converter.send(:extract_view_name, { 'className' => 'TestCollectionViewCell' })
      expect(result).to eq('TestView')
    end

    it 'adds View suffix if missing' do
      result = converter.send(:extract_view_name, 'MyComponent')
      expect(result).to eq('MyComponentView')
    end

    it 'handles Cell suffix' do
      result = converter.send(:extract_view_name, 'ItemCell')
      expect(result).to eq('ItemCellView')
    end

    it 'handles lowercase cell suffix' do
      result = converter.send(:extract_view_name, 'Itemcell')
      expect(result).to eq('ItemCellView')
    end

    it 'returns nil for nil input' do
      expect(converter.send(:extract_view_name, nil)).to be_nil
    end

    it 'keeps View suffix if already present' do
      result = converter.send(:extract_view_name, 'MyView')
      expect(result).to eq('MyView')
    end
  end

  describe '#extract_property_name' do
    let(:converter) { described_class.new({ 'type' => 'Collection' }) }

    it 'extracts property name from binding expression' do
      result = converter.send(:extract_property_name, '@{items}')
      expect(result).to eq('items')
    end

    it 'returns nil for non-binding expression' do
      result = converter.send(:extract_property_name, 'items')
      expect(result).to be_nil
    end

    it 'returns nil for nil input' do
      result = converter.send(:extract_property_name, nil)
      expect(result).to be_nil
    end
  end

  describe '#convert' do
    context 'with no cells or data declared (declaration-faithful, 2026-08-02 ruling)' do
      it 'renders no placeholder items' do
        # The old fallbacks emitted a 10-item "Item \(index)" ForEach in
        # three places — undeclared behavior, removed with the bare-Collection
        # ruling (parity family F4). Since run 31234163967 the bare shape
        # short-circuits to Color.clear before any List exists — the other
        # three faces render only the collection's own box.
        code = described_class.new({ 'type' => 'Collection' }).convert
        expect(code).not_to include('Item \\(index)')
        expect(code).not_to include('ForEach(0..<10')
        expect(code).not_to include('List {')
        expect(code).to include('nothing rendered (declaration-faithful)')
        expect(code).to include('Color.clear')
      end
    end

    context 'with single column collection' do
      let(:component) do
        # A cellClasses entry keeps this on the legacy List path — a fully
        # bare Collection now short-circuits to Color.clear (nothing
        # renderable, declaration-faithful).
        {
          'type' => 'Collection',
          'columns' => 1,
          'cellClasses' => ['Cell']
        }
      end

      it 'generates List' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('List {')
        expect(code).to include('.listStyle(PlainListStyle())')
      end
    end

    context 'with multi-column collection' do
      let(:component) do
        {
          'type' => 'Collection',
          'columns' => 3
        }
      end

      it 'generates ScrollView with LazyVGrid' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('ScrollView(.vertical')
        expect(code).to include('LazyVGrid(columns:')
        expect(code).to include('count: 3')
      end
    end

    context 'with horizontal layout' do
      let(:component) do
        {
          'type' => 'Collection',
          'layout' => 'horizontal',
          'sections' => [
            { 'cell' => 'ItemCell' }
          ],
          'items' => '@{items}'
        }
      end

      it 'emits CollectionStackView with horizontal axis' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('CollectionStackView(')
        expect(code).to include('axis: .horizontal')
        # Outer ScrollView/HStack is no longer emitted by the generator;
        # CollectionStackView wraps the cell content with the right shell.
        expect(code).not_to include('ScrollView(.horizontal')
      end

      # Regression: kjui-collection-stack-horizontal-line-spacing.
      # A horizontal CollectionStackView lays out one cell per line, so
      # `lineSpacing` (the inter-line gap) IS the inter-cell gap. Previously
      # the horizontal branch dropped `lineSpacing` from the fallback chain,
      # so authoring `lineSpacing: 8` silently got the default `spacing: 10`
      # back instead. Match kjui's CollectionStack behavior.
      context 'horizontal spacing fallback' do
        it 'uses lineSpacing when no itemSpacing/columnSpacing is set' do
          converter = described_class.new(component.merge('lineSpacing' => 8))
          code = converter.convert
          expect(code).to include('axis: .horizontal')
          expect(code).to include('spacing: 8')
        end

        it 'still prefers itemSpacing over lineSpacing' do
          converter = described_class.new(component.merge('itemSpacing' => 12, 'lineSpacing' => 8))
          code = converter.convert
          expect(code).to include('spacing: 12')
        end

        # Regression: sjui-collection-undeclared-default-insets-and-spacing —
        # the all-absent default used to be an iOS-only 10; kjui's
        # CollectionStack composable defaults to 0.dp, so declaration-faithful
        # means 0 here too.
        it 'falls back to 0 when no spacing attr is set' do
          converter = described_class.new(component)
          code = converter.convert
          expect(code).to include('spacing: 0')
          expect(code).not_to include('spacing: 10')
        end
      end
    end

    # Regression: sjui-collection-undeclared-default-insets-and-spacing —
    # with insets/spacing undeclared, iOS injected `.padding(.horizontal)`
    # (SwiftUI system ≈16pt) and `spacing: 10` into grid paths while Compose
    # emitted nothing. Ruling: declaration-faithful (the Android behavior).
    describe 'undeclared insets / spacing (declaration-faithful)' do
      let(:grid_component) do
        {
          'type' => 'Collection',
          'columns' => 2,
          'items' => '@{listItems}',
          'sections' => [{ 'cell' => 'item_cell' }]
        }
      end

      it 'emits no horizontal padding when insets are undeclared' do
        code = described_class.new(grid_component).convert
        expect(code).not_to include('.padding(.horizontal)')
      end

      it 'emits spacing 0 when spacing attrs are undeclared' do
        code = described_class.new(grid_component).convert
        expect(code).to include('spacing: 0')
        expect(code).not_to include('spacing: 10')
      end

      it 'still honours declared insets on the grid' do
        code = described_class.new(grid_component.merge('insets' => [16, 16, 16, 16])).convert
        expect(code).to include('.padding(EdgeInsets(top: 16, leading: 16, bottom: 16, trailing: 16))')
      end

      # The `|| 10` default had been masking that this path never read
      # columnSpacing/lineSpacing at all (declared 12/12 emitted 10/10 —
      # close enough to hide). kjui's order: inter-column prefers
      # columnSpacing, inter-row prefers lineSpacing.
      it 'honours columnSpacing for the inter-column gap and lineSpacing for the inter-row gap' do
        code = described_class.new(
          grid_component.merge('columnSpacing' => 12, 'lineSpacing' => 14)
        ).convert
        expect(code).to include('GridItem(.flexible(), spacing: 12)')
        expect(code).to include('alignment: .center, spacing: 14)')
      end

      it 'falls back to itemSpacing for both gaps' do
        code = described_class.new(grid_component.merge('itemSpacing' => 6)).convert
        expect(code).to include('GridItem(.flexible(), spacing: 6)')
        expect(code).to include('alignment: .center, spacing: 6)')
      end
    end

    # Regression: sjui-flow-spacing-chain-asymmetric-with-kjui — the flow
    # default 8 is symmetric with kjui and stays; the chain CONTENT differed:
    # vertical never fell back to itemSpacing, and horizontal preferred
    # itemSpacing over columnSpacing (kjui prefers columnSpacing).
    describe 'flow spacing chains' do
      let(:flow_component) do
        {
          'type' => 'Collection',
          'layout' => 'flow',
          'items' => '@{tags}',
          'sections' => [{ 'cell' => 'tag_cell' }]
        }
      end

      it 'falls back to itemSpacing on the vertical axis' do
        code = described_class.new(flow_component.merge('itemSpacing' => 6)).convert
        expect(code).to include('verticalSpacing: 6')
        expect(code).to include('horizontalSpacing: 6')
      end

      it 'prefers columnSpacing horizontally and lineSpacing vertically' do
        code = described_class.new(flow_component.merge(
          'itemSpacing' => 6, 'columnSpacing' => 12, 'lineSpacing' => 14
        )).convert
        expect(code).to include('horizontalSpacing: 12')
        expect(code).to include('verticalSpacing: 14')
      end

      it 'keeps the symmetric default 8 when nothing is declared' do
        code = described_class.new(flow_component).convert
        expect(code).to include('horizontalSpacing: 8')
        expect(code).to include('verticalSpacing: 8')
      end

      # 2026-08-03 unification (SSoT valueAliases): LeftAligned IS flow —
      # the raw-reading codegen accepts the alias spellings like dynamic's
      # generated enum folds them.
      it 'routes the leftAligned alias spellings through the flow layout' do
        %w[leftAligned LeftAligned].each do |spelling|
          code = described_class.new(flow_component.merge('layout' => spelling)).convert
          expect(code).to include('FlowLayout'), "expected layout: #{spelling} to render as flow"
        end
      end
    end

    describe 'section header/footer insets alignment' do
      let(:grid_component) do
        {
          'type' => 'Collection',
          'columns' => 2,
          'items' => '@{listItems}',
          'sections' => [{ 'cell' => 'item_cell' }]
        }
      end

      it 'aligns declared headers to the declared horizontal insets, not the system default' do
        with_header = grid_component.merge(
          'insets' => [4, 12, 4, 8],
          'sections' => [{ 'cell' => 'item_cell', 'header' => 'header_view' }]
        )
        code = described_class.new(with_header).convert
        expect(code).to include('.padding(EdgeInsets(top: 0, leading: 12, bottom: 0, trailing: 8))')
        expect(code).not_to include('.padding(.horizontal)')
      end

      it 'emits no header padding at all when insets are undeclared' do
        with_header = grid_component.merge(
          'sections' => [{ 'cell' => 'item_cell', 'header' => 'header_view' }]
        )
        code = described_class.new(with_header).convert
        expect(code).not_to include('.padding(.horizontal)')
        expect(code).not_to include('.padding(EdgeInsets(top: 0,')
      end
    end

    context 'with cell classes' do
      let(:component) do
        {
          'type' => 'Collection',
          'columns' => 1,
          'cellClasses' => ['ItemCollectionViewCell']
        }
      end

      it 'ignores cellClasses when a data source is declared' do
        # Measured, and not what the old example implied. With `items`, the
        # section-driven path runs and reads the cell view name from the DATA
        # (`section.cells?.viewName`), so `cellClasses` never reaches the
        # emit — it renders a placeholder instead.
        code = described_class.new(component.merge('items' => '@{rows}')).convert

        expect(code).not_to include('ItemView')
        expect(code).to include('TODO: Implement dynamic view instantiation')
      end

      it 'emits no cells when nothing declares the data source' do
        # Was asserted as "uses cell class name" with no `items`, which
        # emitted `data.collectionDataSource.getCellData(for:)` — a property
        # nothing declares calling a method that does not exist on
        # `CollectionDataSource` (its API is `sections` / `init` /
        # `reconfigured`). The example passed because it read the emitted
        # string, which no compiler had checked.
        code = described_class.new(component).convert

        expect(code).not_to include('getCellData')
        expect(code).to include("no 'items' data source declared")
      end
    end

    context 'with header and footer classes' do
      let(:component) do
        {
          'type' => 'Collection',
          'columns' => 1,
          'cellClasses' => ['ItemCell'],
          'headerClasses' => ['HeaderCell'],
          'footerClasses' => ['FooterCell']
        }
      end

      it 'includes header and footer views' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Section {')
        expect(code).to include('HeaderCellView')
      end
    end

    context 'with item spacing' do
      let(:component) do
        {
          'type' => 'Collection',
          'columns' => 2,
          'itemSpacing' => 15
        }
      end

      it 'uses custom spacing' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('spacing: 15')
      end
    end

    context 'with cell height' do
      let(:component) do
        {
          'type' => 'Collection',
          'columns' => 2,
          'cellHeight' => 100,
          'items' => '@{data}',
          'sections' => [{ 'cell' => 'Cell' }]
        }
      end

      it 'sets frame height' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.frame(height: 100, alignment: .topLeading)')
      end
    end

    context 'with sections' do
      let(:component) do
        {
          'type' => 'Collection',
          'columns' => 2,
          'items' => '@{listData}',
          'sections' => [
            {
              'header' => 'SectionHeaderCell',
              'cell' => 'ItemCell',
              'footer' => 'SectionFooterCell'
            }
          ]
        }
      end

      it 'generates section structure' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('SectionHeaderCellView')
        expect(code).to include('ItemCellView')
        expect(code).to include('SectionFooterCellView')
      end
    end

    context 'with setTargetAsDataSource' do
      let(:component) do
        {
          'type' => 'Collection',
          'setTargetAsDataSource' => true
        }
      end

      it 'adds comment for data source' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('// setTargetAsDataSource: true')
      end
    end

    context 'with setTargetAsDelegate' do
      let(:component) do
        {
          'type' => 'Collection',
          'setTargetAsDelegate' => true
        }
      end

      it 'adds comment for delegate' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('// setTargetAsDelegate: true')
      end
    end

    context 'with scroll indicator hidden' do
      let(:component) do
        {
          'type' => 'Collection',
          'columns' => 2,
          'showsVerticalScrollIndicator' => false
        }
      end

      it 'hides scroll indicators' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('showsIndicators: false')
      end
    end

    context 'with horizontal scroll indicator hidden' do
      let(:component) do
        {
          'type' => 'Collection',
          'layout' => 'horizontal',
          'showsHorizontalScrollIndicator' => false,
          'sections' => [{ 'cell' => 'Cell' }],
          'items' => '@{items}'
        }
      end

      it 'hides horizontal scroll indicators' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('showsIndicators: false')
      end
    end

    context 'with cell width in horizontal layout' do
      let(:component) do
        {
          'type' => 'Collection',
          'layout' => 'horizontal',
          'cellWidth' => 200,
          'sections' => [{ 'cell' => 'Cell' }],
          'items' => '@{items}'
        }
      end

      it 'sets cell width' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.frame(width: 200, alignment: .topLeading)')
      end
    end

    context 'with section-specific columns' do
      let(:component) do
        {
          'type' => 'Collection',
          'columns' => 2,
          'items' => '@{data}',
          'sections' => [
            { 'cell' => 'Cell', 'columns' => 3 }
          ]
        }
      end

      it 'uses section columns' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('count: 3')
      end
    end
  end

  describe '#convert with lazy: "none"' do
    context 'single-column vertical with sections' do
      let(:component) do
        {
          'type' => 'Collection',
          'id' => 'chat',
          'columns' => 1,
          'lazy' => 'none',
          'items' => '@{messages}',
          'sections' => [{ 'cell' => 'MessageCell' }]
        }
      end

      it 'omits ScrollView and LazyVStack, emits plain VStack' do
        code = described_class.new(component).convert
        expect(code).not_to include('ScrollView')
        expect(code).not_to include('LazyVStack')
        expect(code).to include('VStack(')
      end
    end

    context 'horizontal with sections' do
      let(:component) do
        {
          'type' => 'Collection',
          'id' => 'row',
          'layout' => 'horizontal',
          'lazy' => 'none',
          'items' => '@{carousel}',
          'sections' => [{ 'cell' => 'CarouselCell' }]
        }
      end

      it 'omits ScrollView and LazyHStack, emits plain HStack' do
        code = described_class.new(component).convert
        expect(code).not_to include('ScrollView')
        expect(code).not_to include('LazyHStack')
        expect(code).to include('HStack(')
      end
    end

    context 'multi-column grid' do
      let(:component) do
        {
          'type' => 'Collection',
          'id' => 'grid',
          'columns' => 2,
          'lazy' => 'none',
          'items' => '@{tiles}',
          'sections' => [{ 'cell' => 'TileCell' }]
        }
      end

      it 'omits outer ScrollView while keeping LazyVGrid layout' do
        code = described_class.new(component).convert
        expect(code).not_to include('ScrollView')
        expect(code).to include('LazyVGrid')
      end
    end
  end

  describe 'scrollEnabled emission' do
    it 'emits scrollDisabled(true) when scrollEnabled is literal false' do
      converter = described_class.new({
        'type' => 'Collection',
        'id' => 'list',
        'scrollEnabled' => false,
        'cellClasses' => ['ItemCell']
      })
      code = converter.convert
      expect(code).to include('.scrollDisabled(true)')
      expect(code).not_to include('.disabled(true)')
    end

    it 'emits scrollDisabled with negated binding when scrollEnabled is bound' do
      converter = described_class.new({
        'type' => 'Collection',
        'id' => 'list',
        'scrollEnabled' => '@{canScroll}',
        'cellClasses' => ['ItemCell']
      })
      code = converter.convert
      expect(code).to include('.scrollDisabled(!data.canScroll)')
      expect(code).not_to include('.disabled(data.canScroll == false)')
    end
  end

  describe '#convert with responsive block (regression: sjui-responsive-collection-columns-not-applied)' do
    it 'emits an if/else size class branch when responsive.regular.columns is set' do
      component = {
        'type' => 'Collection',
        'id' => 'grid_collection',
        'columns' => 2,
        'responsive' => {
          'regular' => { 'columns' => 5 }
        }
      }
      code = described_class.new(component).convert
      expect(code).to include('if horizontalSizeClass == .regular {')
      expect(code).to include('} else {')
    end

    it 'uses the overridden column count in the regular branch' do
      component = {
        'type' => 'Collection',
        'id' => 'grid_collection',
        'columns' => 2,
        'responsive' => {
          'regular' => { 'columns' => 5 }
        }
      }
      code = described_class.new(component).convert
      expect(code).to include('count: 5')
      expect(code).to include('count: 2')
    end

    it 'leaves non-responsive collections untouched (regression check)' do
      component = {
        'type' => 'Collection',
        'id' => 'grid_collection',
        'columns' => 3
      }
      code = described_class.new(component).convert
      expect(code).not_to include('horizontalSizeClass')
      expect(code).to include('count: 3')
    end

    # Regression: jui-collection-columns-data-binding-support.
    # `columns: "@{prop}"` resolves at runtime to `data.prop`; the grid path
    # (LazyVGrid / LazyHGrid) is forced regardless of the runtime value so
    # the layout structure stays stable across runtime column changes.
    it 'emits `count: data.<prop>` for `columns: "@{prop}"` and routes through the grid path' do
      component = {
        'type' => 'Collection',
        'id' => 'grid_collection',
        'columns' => '@{gridColumnCount}',
        'cellClasses' => ['ItemCell']
      }
      code = described_class.new(component).convert
      expect(code).to include('LazyVGrid(')
      expect(code).to include('count: data.gridColumnCount')
      # Binding must NEVER reach the single-column List/LazyVStack fast-path
      # — that branch interpolates `columns == 1` and would emit the wrong
      # container for a binding.
      expect(code).not_to include('flat list')
    end

    it 'resolves `columns: "@{prop}"` inside `responsive.regular`' do
      component = {
        'type' => 'Collection',
        'id' => 'grid_collection',
        'columns' => 2,
        'responsive' => {
          'regular' => { 'columns' => '@{tabletGridColumnCount}' }
        },
        'cellClasses' => ['ItemCell']
      }
      code = described_class.new(component).convert
      expect(code).to include('count: data.tabletGridColumnCount')
      expect(code).to include('count: 2')
    end

    # Regression: sjui-collection-responsive-block-missing-group-wrap.
    # Without `Group { }` the bare if/else lands directly inside the
    # parent AnyView(...) argument and Swift refuses to parse it.
    it 'wraps the if/else branches in Group { } so AnyView(...) accepts them' do
      component = {
        'type' => 'Collection',
        'id' => 'grid_collection',
        'columns' => 2,
        'responsive' => {
          'regular' => { 'columns' => 5 }
        }
      }
      code = described_class.new(component).convert
      expect(code).to include('Group {')
      group_idx = code.index('Group {')
      if_idx = code.index('if horizontalSizeClass == .regular {')
      expect(group_idx).not_to be_nil
      expect(if_idx).not_to be_nil
      expect(group_idx).to be < if_idx
    end
  end

  describe '#to_camel_case' do
    let(:converter) { described_class.new({ 'type' => 'Collection' }) }

    it 'converts snake_case to camelCase' do
      expect(converter.send(:to_camel_case, 'my_property')).to eq('myProperty')
    end

    it 'handles empty string' do
      expect(converter.send(:to_camel_case, '')).to eq('')
    end

    it 'handles nil' do
      expect(converter.send(:to_camel_case, nil)).to be_nil
    end
  end
end
