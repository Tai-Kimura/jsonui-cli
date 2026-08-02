# frozen_string_literal: true

require 'compose/components/collection_component'
require 'compose/helpers/modifier_builder'

RSpec.describe KjuiTools::Compose::Components::CollectionComponent do
  let(:required_imports) { Set.new }

  describe '.generate' do
    it 'generates vertical LazyVerticalGrid by default' do
      json_data = { 'type' => 'Collection' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('LazyVerticalGrid(')
      expect(required_imports).to include(:lazy_grid)
    end

    it 'generates horizontal LazyHorizontalGrid' do
      json_data = { 'type' => 'Collection', 'layout' => 'horizontal' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('LazyHorizontalGrid(')
    end

    it 'sets columns from config' do
      json_data = { 'type' => 'Collection', 'columns' => 3 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('GridCells.Fixed(3)')
    end

    it 'applies content padding as array' do
      json_data = { 'type' => 'Collection', 'contentPadding' => [16, 8, 16, 8] }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('contentPadding = PaddingValues')
    end

    it 'applies content padding as number' do
      json_data = { 'type' => 'Collection', 'contentPadding' => 16 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('contentPadding = PaddingValues(16.dp)')
    end

    it 'applies item spacing' do
      json_data = { 'type' => 'Collection', 'itemSpacing' => 8 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Arrangement.spacedBy(8.dp)')
      expect(required_imports).to include(:arrangement)
    end

    it 'applies spacing attribute' do
      json_data = { 'type' => 'Collection', 'spacing' => 12 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Arrangement.spacedBy(12.dp)')
    end

    it 'handles items binding' do
      json_data = { 'type' => 'Collection', 'items' => '@{items}', 'cellClasses' => ['ItemCell'] }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('data.items')
    end

    context 'with sections' do
      it 'generates section-based collection' do
        json_data = {
          'type' => 'Collection',
          'sections' => [
            { 'type' => 'section', 'items' => '@{items}' }
          ]
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('LazyVerticalGrid')
      end

      it 'handles different column counts in sections' do
        json_data = {
          'type' => 'Collection',
          'sections' => [
            { 'type' => 'section', 'columns' => 2 },
            { 'type' => 'section', 'columns' => 3 }
          ]
        }
        result = described_class.generate(json_data, 0, required_imports)
        # LCM of 2 and 3 is 6
        expect(result).to include('GridCells.Fixed(6)')
      end

      it 'handles same column counts in sections' do
        json_data = {
          'type' => 'Collection',
          'sections' => [
            { 'type' => 'section', 'columns' => 2 },
            { 'type' => 'section', 'columns' => 2 }
          ]
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('GridCells.Fixed(2)')
      end
    end

    context 'with legacy cellClasses' do
      it 'uses first cell class' do
        json_data = {
          'type' => 'Collection',
          'cellClasses' => ['PrimaryCell', 'SecondaryCell'],
          'items' => '@{items}'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('PrimaryCell')
      end

      it 'handles no items binding' do
        json_data = {
          'type' => 'Collection',
          'cellClasses' => ['ItemCell']
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('items(0)')
        expect(result).to include('No items')
      end

      it 'renders nothing for an undeclared collection (declaration-faithful)' do
        # 2026-08-02 ruling: a Collection with no cells/data declared emits
        # no placeholder items — the old 10-item "Item ${index}" Cards were
        # undeclared behavior.
        json_data = { 'type' => 'Collection' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('nothing rendered (declaration-faithful)')
        expect(result).not_to include('items(10)')
        expect(result).not_to include('Item ${index}')
        expect(result).not_to include('Card(')
      end

      it 'applies cell height' do
        json_data = {
          'type' => 'Collection',
          'cellClasses' => ['ItemCell'],
          'items' => '@{items}',
          'cellHeight' => 100
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.height(100.dp)')
      end

      it 'fills width for grid layouts' do
        json_data = {
          'type' => 'Collection',
          'cellClasses' => ['ItemCell'],
          'items' => '@{items}',
          'columns' => 2
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.fillMaxWidth()')
      end
    end

    context 'with sections and binding' do
      it 'generates sections content with binding' do
        json_data = {
          'type' => 'Collection',
          'items' => '@{dataSource}',
          'sections' => [
            { 'cell' => 'ProductCell', 'columns' => 2 }
          ]
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('Section 1: ProductCell')
        expect(result).to include('ProductCellViewModel')
      end

      it 'generates section with header' do
        json_data = {
          'type' => 'Collection',
          'items' => '@{dataSource}',
          'sections' => [
            { 'cell' => 'ItemCell', 'header' => 'HeaderCell' }
          ]
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('Section 1 Header: HeaderCell')
        expect(result).to include('HeaderCellViewModel')
        # 1-column section-based collections route through CollectionStack
        # (LazyColumn-backed) so GridItemSpan no longer applies; headers use
        # plain `item { ... }` instead.
        expect(result).to include('CollectionStack(')
      end

      it 'generates section with footer' do
        json_data = {
          'type' => 'Collection',
          'items' => '@{dataSource}',
          'sections' => [
            { 'cell' => 'ItemCell', 'footer' => 'FooterCell' }
          ]
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('Section 1 Footer: FooterCell')
        expect(result).to include('FooterCellViewModel')
      end

      it 'handles sections without items binding' do
        json_data = {
          'type' => 'Collection',
          'sections' => [
            { 'cell' => 'ItemCell' }
          ]
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('No items binding specified')
      end

      it 'calculates span for different column counts' do
        json_data = {
          'type' => 'Collection',
          'items' => '@{dataSource}',
          'columns' => 6,
          'sections' => [
            { 'cell' => 'WideCell', 'columns' => 2 }
          ]
        }
        result = described_class.generate(json_data, 0, required_imports)
        # Span is calculated for sections with different columns
        expect(result).to include('WideCell')
        # The result should contain GridItemSpan for column differences
        expect(required_imports).to include(:grid_item_span)
      end

      it 'handles horizontal layout' do
        json_data = {
          'type' => 'Collection',
          'layout' => 'horizontal',
          'items' => '@{dataSource}',
          'sections' => [
            { 'cell' => 'CardCell' }
          ]
        }
        result = described_class.generate(json_data, 0, required_imports)
        # Single-column horizontal sections now go through CollectionStack
        # (LazyRow-backed) instead of LazyHorizontalGrid.
        expect(result).to include('CollectionStack(')
        expect(result).to include('CollectionStackAxis.HORIZONTAL')
        expect(result).to include('CardCellView')
      end

      # Regression: kjui-collection-stack-horizontal-line-spacing.
      # A horizontal CollectionStack collapses lines into a single row of
      # cells, so `lineSpacing` (the inter-line gap) IS the inter-cell gap
      # there. The old fallback chain dropped `lineSpacing` for horizontal,
      # which made `lineSpacing: 8` silently emit no spacing arg on Android
      # while the LazyHorizontalGrid path already accepted it. CollectionStack
      # must match that behavior.
      context 'horizontal CollectionStack spacing fallback' do
        it 'uses lineSpacing as inter-cell spacing when no itemSpacing/columnSpacing is set' do
          json_data = {
            'type' => 'Collection',
            'layout' => 'horizontal',
            'items' => '@{chips}',
            'lineSpacing' => 8,
            'sections' => [{ 'cell' => 'ChipCell' }]
          }
          result = described_class.generate(json_data, 0, required_imports)
          expect(result).to include('CollectionStackAxis.HORIZONTAL')
          expect(result).to include('spacing = 8.dp')
        end

        it 'still prefers itemSpacing over lineSpacing in horizontal' do
          json_data = {
            'type' => 'Collection',
            'layout' => 'horizontal',
            'items' => '@{chips}',
            'itemSpacing' => 12,
            'lineSpacing' => 8,
            'sections' => [{ 'cell' => 'ChipCell' }]
          }
          result = described_class.generate(json_data, 0, required_imports)
          expect(result).to include('spacing = 12.dp')
        end

        it 'vertical CollectionStack still uses lineSpacing first (no regression)' do
          json_data = {
            'type' => 'Collection',
            'items' => '@{messages}',
            'lineSpacing' => 6,
            'sections' => [{ 'cell' => 'MessageCell' }]
          }
          result = described_class.generate(json_data, 0, required_imports)
          expect(result).to include('CollectionStackAxis.VERTICAL')
          expect(result).to include('spacing = 6.dp')
        end
      end

      it 'handles vertical layout' do
        json_data = {
          'type' => 'Collection',
          'items' => '@{dataSource}',
          'sections' => [
            { 'cell' => 'ListItemCell' }
          ]
        }
        result = described_class.generate(json_data, 0, required_imports)
        # Single-column vertical sections route through CollectionStack
        # (LazyColumn-backed) instead of LazyVerticalGrid.
        expect(result).to include('CollectionStack(')
        expect(result).to include('CollectionStackAxis.VERTICAL')
        expect(result).to include('ListItemCellView')
      end

      it 'reverses section emission order in lazyContent when reverseLayout=true' do
        json_data = {
          'type' => 'Collection',
          'items' => '@{messages}',
          'reverseLayout' => true,
          'sections' => [
            { 'cell' => 'MessageCell' },
            { 'cell' => 'LocationPromptBubble' },
            { 'cell' => 'StreamingCell' }
          ]
        }
        result = described_class.generate(json_data, 0, required_imports)
        # Single-column path → CollectionStack with reverseLayout = true
        expect(result).to include('CollectionStack(')
        expect(result).to include('reverseLayout = true,')

        # In the LazyListScope (lazyContent block), sections must be emitted
        # in reverse JSON order so that LazyColumn's reverseLayout flips them
        # back into JSON-defined visual order.
        lazy_block = result.split('lazyContent = {', 2).last.split('eagerContent = {').first
        streaming_pos = lazy_block.index('// Section 3: StreamingCell')
        location_pos  = lazy_block.index('// Section 2: LocationPromptBubble')
        message_pos   = lazy_block.index('// Section 1: MessageCell')
        expect(streaming_pos).not_to be_nil
        expect(location_pos).not_to be_nil
        expect(message_pos).not_to be_nil
        expect(streaming_pos).to be < location_pos
        expect(location_pos).to be < message_pos

        # eagerContent retains natural JSON order (Column emits top→bottom
        # naturally and has no reverseLayout flag).
        eager_block = result.split('eagerContent = {', 2).last
        e_message_pos   = eager_block.index('// Section 1: MessageCell')
        e_location_pos  = eager_block.index('// Section 2: LocationPromptBubble')
        e_streaming_pos = eager_block.index('// Section 3: StreamingCell')
        expect(e_message_pos).to be < e_location_pos
        expect(e_location_pos).to be < e_streaming_pos
      end

      it 'preserves natural section order when reverseLayout is false/absent' do
        json_data = {
          'type' => 'Collection',
          'items' => '@{messages}',
          'sections' => [
            { 'cell' => 'MessageCell' },
            { 'cell' => 'StreamingCell' }
          ]
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).not_to include('reverseLayout = true,')
        lazy_block = result.split('lazyContent = {', 2).last.split('eagerContent = {').first
        message_pos   = lazy_block.index('// Section 1: MessageCell')
        streaming_pos = lazy_block.index('// Section 2: StreamingCell')
        expect(message_pos).to be < streaming_pos
      end

      it 'fills width for multi-column sections' do
        json_data = {
          'type' => 'Collection',
          'items' => '@{dataSource}',
          'sections' => [
            { 'cell' => 'GridCell', 'columns' => 2 }
          ]
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('GridCellView')
        expect(result).to include('GridCells.Fixed(2)')
      end
    end
  end

  describe 'private methods' do
    describe '.calculate_lcm' do
      it 'calculates LCM of two numbers' do
        result = described_class.send(:calculate_lcm, [2, 3])
        expect(result).to eq(6)
      end

      it 'calculates LCM of multiple numbers' do
        result = described_class.send(:calculate_lcm, [2, 3, 4])
        expect(result).to eq(12)
      end

      it 'returns 1 for empty array' do
        result = described_class.send(:calculate_lcm, [])
        expect(result).to eq(1)
      end
    end

    describe '.extract_view_name' do
      it 'converts cell class to view name' do
        result = described_class.send(:extract_view_name, 'ProductCell')
        expect(result).to eq('ProductView')
      end

      it 'handles CollectionViewCell suffix' do
        result = described_class.send(:extract_view_name, 'ItemCollectionViewCell')
        expect(result).to eq('ItemView')
      end

      it 'returns nil for nil input' do
        result = described_class.send(:extract_view_name, nil)
        expect(result).to be_nil
      end

      it 'preserves existing View suffix' do
        result = described_class.send(:extract_view_name, 'CardView')
        # CardView doesn't have Cell suffix, so it becomes CardviewView
        expect(result).to include('View')
      end
    end

    describe '.to_pascal_case' do
      it 'converts snake_case to PascalCase' do
        result = described_class.send(:to_pascal_case, 'my_component_name')
        expect(result).to eq('MyComponentName')
      end

      it 'converts kebab-case to PascalCase' do
        result = described_class.send(:to_pascal_case, 'my-component-name')
        expect(result).to eq('MyComponentName')
      end

      it 'returns empty string for nil' do
        result = described_class.send(:to_pascal_case, nil)
        expect(result).to eq(nil)
      end

      it 'returns empty string for empty' do
        result = described_class.send(:to_pascal_case, '')
        expect(result).to eq('')
      end
    end

    describe '.generate with lazy: "none"' do
      it 'uses Column instead of LazyVerticalGrid for vertical non-lazy' do
        json_data = {
          'type' => 'Collection',
          'lazy' => 'none',
          'items' => '@{messages}',
          'sections' => [{ 'cell' => 'MessageCell' }]
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('Column(')
        expect(result).not_to include('LazyVerticalGrid')
        expect(result).not_to include('LazyColumn')
      end

      it 'uses Row instead of LazyHorizontalGrid for horizontal non-lazy' do
        json_data = {
          'type' => 'Collection',
          'layout' => 'horizontal',
          'lazy' => 'none',
          'items' => '@{carousel}',
          'sections' => [{ 'cell' => 'CarouselCell' }]
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('Row(')
        expect(result).not_to include('LazyHorizontalGrid')
        expect(result).not_to include('LazyRow')
      end

      it 'defaults to lazy (LazyVerticalGrid) when lazy attribute is absent' do
        json_data = { 'type' => 'Collection' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('LazyVerticalGrid(')
      end
    end

    describe '.indent' do
      it 'returns text unchanged for level 0' do
        result = described_class.send(:indent, 'text', 0)
        expect(result).to eq('text')
      end

      it 'adds indentation for level 1' do
        result = described_class.send(:indent, 'text', 1)
        expect(result).to eq('    text')
      end

      it 'preserves empty lines' do
        result = described_class.send(:indent, "line1\n\nline2", 1)
        expect(result).to eq("    line1\n\n    line2")
      end
    end

    # Regression: jui-collection-columns-data-binding-support.
    # `columns: "@{prop}"` resolves at runtime against `data.prop` so a single
    # Collection can change column count without re-layout. The grid path
    # (LazyVerticalGrid / LazyHorizontalGrid) is forced regardless of the
    # binding's runtime value, so a binding that resolves to 1 still uses the
    # grid container — keeping layout structure stable.
    describe 'columns binding support' do
      it 'emits GridCells.Fixed(data.<prop>) for `columns: "@{prop}"`' do
        json = {
          'type' => 'Collection',
          'id' => 'grid',
          'columns' => '@{gridColumnCount}',
          'child' => [
            { 'type' => 'View', 'id' => 'item_cell' }
          ]
        }
        result = described_class.generate(json, 0, Set.new, nil)
        code = result.is_a?(Hash) ? result[:code] : result
        expect(code).to include('LazyVerticalGrid(')
        expect(code).to include('columns = GridCells.Fixed(data.gridColumnCount)')
      end

      it 'emits horizontal binding form into LazyHorizontalGrid.rows' do
        json = {
          'type' => 'Collection',
          'id' => 'grid',
          'orientation' => 'horizontal',
          'columns' => '@{horizontalRowCount}',
          'child' => [
            { 'type' => 'View', 'id' => 'item_cell' }
          ]
        }
        result = described_class.generate(json, 0, Set.new, nil)
        code = result.is_a?(Hash) ? result[:code] : result
        expect(code).to include('LazyHorizontalGrid(')
        expect(code).to include('rows = GridCells.Fixed(data.horizontalRowCount)')
      end

      it 'keeps `GridCells.Fixed(N)` literal for non-binding integer columns' do
        json = {
          'type' => 'Collection',
          'id' => 'grid',
          'columns' => 5,
          'child' => [
            { 'type' => 'View', 'id' => 'item_cell' }
          ]
        }
        result = described_class.generate(json, 0, Set.new, nil)
        code = result.is_a?(Hash) ? result[:code] : result
        expect(code).to include('columns = GridCells.Fixed(5)')
      end

      describe '.columns_emit_info' do
        it 'returns the binding expression for `@{prop}` form' do
          expect(described_class.columns_emit_info('columns' => '@{gridColumnCount}'))
            .to eq(expr: 'data.gridColumnCount', literal: nil, is_binding: true)
        end

        it 'returns literal int + expression for a static count' do
          expect(described_class.columns_emit_info('columns' => 5))
            .to eq(expr: '5', literal: 5, is_binding: false)
        end

        it 'defaults missing `columns` to 1' do
          expect(described_class.columns_emit_info({}))
            .to eq(expr: '1', literal: 1, is_binding: false)
        end
      end

      describe '.single_column_sections?' do
        # Binding form takes the multi-column grid path regardless of the
        # runtime value, so single-column CollectionStack fast-path is
        # disabled even when every section declares `columns: 1` explicitly.
        it 'returns false when top-level columns is a binding' do
          sections = [
            { 'cell' => 'CellView', 'columns' => 1 },
            { 'cell' => 'CellView', 'columns' => 1 }
          ]
          json = { 'columns' => '@{gridColumnCount}' }
          expect(described_class.single_column_sections?(sections, json)).to be false
        end

        it 'returns true when every section is literal single-column (existing behavior)' do
          sections = [
            { 'cell' => 'CellView', 'columns' => 1 },
            { 'cell' => 'CellView' }  # inherits default 1
          ]
          json = { 'columns' => 1 }
          expect(described_class.single_column_sections?(sections, json)).to be true
        end
      end

      # Regression: kjui-collection-columns-binding-crash-in-generate-sections-content.
      # Top-level `generate` resolves `columns_emit_info` and sets a literal
      # sentinel for the grid count, but the nested `generate_sections_content`
      # path was reading `json_data['columns']` raw — for a binding form that
      # returns the string `"@{prop}"`, which then crashed the LCM/item_span
      # math with "String can't be coerced into Integer".
      context 'binding-driven columns with sections (regression)' do
        it 'does not raise when columns is a binding AND sections is defined' do
          json = {
            'type' => 'Collection',
            'id' => 'grid_collection',
            'columns' => '@{gridColumnCount}',
            'items' => '@{gridItems}',
            'sections' => [{ 'cell' => 'ProductGridCell' }]
          }
          expect { described_class.generate(json, 0, Set.new) }.not_to raise_error
        end

        it 'emits GridCells.Fixed(data.<prop>) for the grid count' do
          json = {
            'type' => 'Collection',
            'id' => 'grid_collection',
            'columns' => '@{gridColumnCount}',
            'items' => '@{gridItems}',
            'sections' => [{ 'cell' => 'ProductGridCell' }]
          }
          result = described_class.generate(json, 0, Set.new)
          expect(result).to include('columns = GridCells.Fixed(data.gridColumnCount)')
        end

        it 'uses items(size) (no GridItemSpan span arg) for the binding case' do
          # Under a runtime-resolved grid, the LCM-based span math is
          # meaningless; the binding path must force span = 1 so the
          # `items(size)` branch is taken instead of
          # `items(size, span = { GridItemSpan(N) })`.
          json = {
            'type' => 'Collection',
            'id' => 'grid_collection',
            'columns' => '@{gridColumnCount}',
            'items' => '@{gridItems}',
            'sections' => [{ 'cell' => 'ProductGridCell' }]
          }
          result = described_class.generate(json, 0, Set.new)
          expect(result).to match(/items\(cellData\.data\.size\)\s*\{\s*cellIndex/)
          expect(result).not_to match(/GridItemSpan\(2\)/)  # sentinel must not leak
        end

        it 'comments the section header with the runtime expression, not the sentinel' do
          # Cosmetic but informative: previously emitted "// Section 1: X (2 columns)"
          # under a binding, which would mislead a reader expecting a literal.
          json = {
            'type' => 'Collection',
            'columns' => '@{gridColumnCount}',
            'items' => '@{gridItems}',
            'sections' => [{ 'cell' => 'ProductGridCell' }]
          }
          result = described_class.generate(json, 0, Set.new)
          expect(result).to include('// Section 1: ProductGridCell (data.gridColumnCount columns)')
        end
      end

      # defaultScrollAnchor — Compose has no `.defaultScrollAnchor`, and
      # reverseLayout is not one (it flips the item order too), so it is a
      # one-shot scroll once the data has arrived.
      describe 'defaultScrollAnchor' do
        def grid(anchor, extra = {})
          described_class.generate(
            { 'type' => 'Collection', 'id' => 'list', 'columns' => 2,
              'items' => '@{listData}', 'defaultScrollAnchor' => anchor,
              'sections' => [{ 'cell' => 'ItemCell' }] }.merge(extra),
            0, required_imports
          )
        end

        it 'scrolls to the last item for bottom' do
          result = grid('bottom')
          expect(result).to include('gridState.scrollToItem(defaultAnchorCount - 1)')
          expect(result).to include('state = gridState')
        end

        it 'scrolls to the middle item for center' do
          expect(grid('center')).to include('gridState.scrollToItem(defaultAnchorCount / 2)')
        end

        # Keyed on the count, not Unit: the list is usually empty on the first
        # composition, and an anchor applied to an empty list does nothing.
        it 'waits for the data and then applies exactly once' do
          result = grid('bottom')
          expect(result).to include('LaunchedEffect(defaultAnchorCount)')
          expect(result).to include('val defaultAnchorApplied = remember { mutableStateOf(false) }')
          expect(result).to include('if (!defaultAnchorApplied.value && defaultAnchorCount > 0)')
          expect(required_imports).to include(:remember_state, :launched_effect)
        end

        it 'emits nothing for top — that is where the list already starts' do
          expect(grid('top')).not_to include('defaultAnchorApplied')
        end

        it 'emits nothing without an items binding to count' do
          expect(grid('bottom', 'items' => nil)).not_to include('defaultAnchorApplied')
        end

        it 'reuses the state scrollTo already created' do
          result = grid('bottom', 'scrollTo' => '@{scrollIndex}')
          expect(result.scan('val gridState = rememberLazyGridState()').length).to eq(1)
          expect(result).to include('gridState.scrollToItem(defaultAnchorCount - 1)')
        end

        it 'applies on the CollectionStack path too' do
          result = described_class.generate(
            { 'type' => 'Collection', 'id' => 'list', 'items' => '@{listData}',
              'defaultScrollAnchor' => 'bottom', 'sections' => [{ 'cell' => 'ItemCell' }] },
            0, required_imports
          )
          expect(result).to include('collectionStackState.scrollToItem(defaultAnchorCount - 1)')
          expect(result).to include('lazyState = collectionStackState,')
        end
      end
    end
  end
end
