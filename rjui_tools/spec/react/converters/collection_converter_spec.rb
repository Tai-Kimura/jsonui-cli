# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/collection_converter'

RSpec.describe RjuiTools::React::Converters::CollectionConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'basic collection with single column' do
      it 'generates list layout' do
        converter = create_converter({ 'class' => 'Collection', 'cellClasses' => ['ItemCell'] })
        result = converter.convert
        expect(result).to include('<div')
        expect(result).to include('flex flex-col')
      end
    end

    context 'with multiple columns' do
      it 'generates grid layout' do
        converter = create_converter({ 'class' => 'Collection', 'columnCount' => 3, 'cellClasses' => ['ItemCell'] })
        result = converter.convert
        expect(result).to include('grid')
        expect(result).to include('grid-cols-3')
      end
    end

    context 'with horizontal layout' do
      it 'generates horizontal scroll layout' do
        converter = create_converter({ 'class' => 'Collection', 'layout' => 'horizontal', 'cellClasses' => ['ItemCell'] })
        result = converter.convert
        expect(result).to include('flex flex-row')
        expect(result).to include('overflow-x-auto')
      end
    end

    context 'with itemSpacing' do
      it 'applies gap spacing' do
        converter = create_converter({ 'class' => 'Collection', 'cellClasses' => ['ItemCell'], 'itemSpacing' => 8 })
        result = converter.convert
        expect(result).to include('gap-[8px]')
      end
    end

    context 'with items binding' do
      it 'generates map rendering with TypeScript index type' do
        converter = create_converter({ 'class' => 'Collection', 'cellClasses' => ['ItemCell'], 'items' => '@{listItems}' })
        result = converter.convert
        expect(result).to include('{data.listItems?.map((item, index: number) =>')
        expect(result).to include('key={index}')
        expect(result).to include('data={item}')
      end

      # Regression: rjui-collection-cells-missing-item-index-id — kjui
      # testTag parity so jsonui-test-runner's tapItem can click
      # #{collectionId}_item_{index}.
      it 'passes the {id}_item_{index} identifier to each cell (legacy path)' do
        converter = create_converter({ 'class' => 'Collection', 'id' => 'gallery_thumbnail_row',
                                       'cellClasses' => ['ItemCell'], 'items' => '@{listItems}' })
        result = converter.convert
        expect(result).to include('key={index} id={`gallery_thumbnail_row_item_${index}`} data={item} />')
      end

      it 'omits the item identifier when the collection has no literal id' do
        converter = create_converter({ 'class' => 'Collection', 'cellClasses' => ['ItemCell'], 'items' => '@{listItems}' })
        expect(converter.convert).not_to include('_item_')
      end
    end

    context 'with headerClasses' do
      it 'includes header component' do
        converter = create_converter({ 'class' => 'Collection', 'cellClasses' => ['ItemCell'], 'headerClasses' => ['HeaderView'] })
        result = converter.convert
        expect(result).to include('<HeaderView />')
      end
    end

    context 'with footerClasses' do
      it 'includes footer component' do
        converter = create_converter({ 'class' => 'Collection', 'cellClasses' => ['ItemCell'], 'footerClasses' => ['FooterView'] })
        result = converter.convert
        expect(result).to include('<FooterView />')
      end
    end

    context 'with sections' do
      it 'generates section-based rendering with nullish coalescing' do
        json = {
          'class' => 'Collection',
          'sections' => [
            { 'header' => 'SectionHeader', 'cell' => 'ItemCell', 'footer' => 'SectionFooter' }
          ],
          'items' => '@{sectionData}'
        }
        converter = create_converter(json)
        result = converter.convert
        expect(result).to include('SectionHeader')
        expect(result).to include('SectionFooter')
        # Updated expectation: uses nullish coalescing with array
        expect(result).to include('sections?.[0]?.cells?.data ?? []')
      end

      it 'passes the {id}_item_{index} identifier to each cell (sections path)' do
        json = {
          'class' => 'Collection',
          'id' => 'fee_sections_collection',
          'sections' => [{ 'cell' => 'FeeCell' }],
          'items' => '@{sectionData}'
        }
        result = create_converter(json).convert
        expect(result).to include('id={`fee_sections_collection_item_${cellIndex}`}')
      end
    end

    context 'with contentInset' do
      it 'applies padding from insets' do
        converter = create_converter({ 'class' => 'Collection', 'cellClasses' => ['ItemCell'], 'contentInset' => [10, 20, 10, 20] })
        result = converter.convert
        expect(result).to include('pt-[10px]')
        expect(result).to include('pl-[20px]')
        expect(result).to include('pb-[10px]')
        expect(result).to include('pr-[20px]')
      end
    end

    context 'cell class name conversion' do
      context 'with CollectionViewCell suffix' do
        it 'converts to View suffix' do
          converter = create_converter({ 'class' => 'Collection', 'cellClasses' => ['ProductCollectionViewCell'] })
          result = converter.convert
          expect(result).to include('ProductView')
        end
      end

      context 'with Cell suffix' do
        it 'adds View suffix' do
          converter = create_converter({ 'class' => 'Collection', 'cellClasses' => ['ProductCell'] })
          result = converter.convert
          expect(result).to include('ProductCellView')
        end
      end

      context 'with path-based reference' do
        it 'converts to PascalCase' do
          converter = create_converter({ 'class' => 'Collection', 'cellClasses' => ['components/product_item'] })
          result = converter.convert
          expect(result).to include('ProductItem')
        end
      end
    end

    context 'with testId' do
      it 'generates data-testid attribute' do
        converter = create_converter({ 'class' => 'Collection', 'cellClasses' => ['ItemCell'], 'testId' => 'product-list' })
        result = converter.convert
        expect(result).to include('data-testid="product-list"')
      end
    end

    context 'with visibility binding' do
      it 'wraps with conditional rendering' do
        converter = create_converter({ 'class' => 'Collection', 'cellClasses' => ['ItemCell'], 'visibility' => '@{showList}' })
        result = converter.convert
        expect(result).to include('{data.showList !== "gone" &&')
      end
    end

    context 'with lazy: "none"' do
      it 'drops overflow-y-auto for single column' do
        converter = create_converter({ 'class' => 'Collection', 'cellClasses' => ['ItemCell'], 'lazy' => 'none' })
        result = converter.convert
        expect(result).to include('flex flex-col')
        expect(result).not_to include('overflow-y-auto')
      end

      it 'drops overflow-x-auto for horizontal' do
        converter = create_converter({ 'class' => 'Collection', 'layout' => 'horizontal', 'cellClasses' => ['ItemCell'], 'lazy' => 'none' })
        result = converter.convert
        expect(result).to include('flex flex-row')
        expect(result).not_to include('overflow-x-auto')
        expect(result).not_to include('flex-nowrap')
      end

      it 'keeps overflow classes when lazy attribute is absent (defaults to "lazy")' do
        converter = create_converter({ 'class' => 'Collection', 'cellClasses' => ['ItemCell'] })
        result = converter.convert
        expect(result).to include('overflow-y-auto')
      end
    end

    # Regression: jui-collection-columns-data-binding-support.
    # Tailwind's JIT can't see `grid-cols-${variable}` at build time, so a
    # `@{prop}` binding cannot reach the class string. Emit the bare `grid`
    # class and push `gridTemplateColumns: \`repeat(${data.prop}, minmax(0,
    # 1fr))\`` into the inline style attribute instead. A literal int keeps
    # the existing `grid-cols-N` shortcut.
    context 'with `columns: "@{prop}"` data binding' do
      it 'emits `grid` class but no `grid-cols-N` Tailwind class' do
        converter = create_converter({
          'class' => 'Collection',
          'columns' => '@{gridColumnCount}',
          'cellClasses' => ['ItemCell']
        })
        result = converter.convert
        expect(result).to include('grid')
        expect(result).not_to match(/grid-cols-\d+/)
      end

      it 'emits `gridTemplateColumns: `repeat(${data.<prop>}, minmax(0, 1fr))`` as inline style' do
        converter = create_converter({
          'class' => 'Collection',
          'columns' => '@{gridColumnCount}',
          'cellClasses' => ['ItemCell']
        })
        result = converter.convert
        expect(result).to include('gridTemplateColumns: `repeat(${data.gridColumnCount}, minmax(0, 1fr))`')
      end

      it 'keeps the literal `grid-cols-N` class for static integer columns' do
        converter = create_converter({
          'class' => 'Collection',
          'columns' => 5,
          'cellClasses' => ['ItemCell']
        })
        result = converter.convert
        expect(result).to include('grid-cols-5')
        expect(result).not_to include('gridTemplateColumns')
      end

      it 'forces the grid path even when the binding could resolve to 1' do
        # A literal `columns: 1` routes through the `flex flex-col` list
        # path. A binding can't take that path because its runtime value
        # might be >1; the grid layout structure must stay stable across
        # runtime changes.
        converter = create_converter({
          'class' => 'Collection',
          'columns' => '@{gridColumnCount}',
          'cellClasses' => ['ItemCell']
        })
        result = converter.convert
        expect(result).not_to include('flex flex-col')
      end
    end

    # Scroll control. The element side lives here; the effects that drive it
    # are hoisted by ReactGenerator (react_generator_spec).
    context 'scroll control' do
      def scrolling(extra)
        create_converter(
          { 'class' => 'Collection', 'id' => 'item_list', 'items' => '@{listData}',
            'cellClasses' => ['ItemCell'] }.merge(extra)
        ).convert
      end

      it 'attaches the ref the hoisted effects target' do
        expect(scrolling('scrollTo' => '@{scrollIndex}')).to include('ref={itemListRef}')
      end

      %w[defaultScrollAnchor currentPage onItemAppear].each do |attr|
        it "attaches the ref for #{attr}" do
          value = attr == 'defaultScrollAnchor' ? 'bottom' : '@{x}'
          expect(scrolling(attr => value)).to include('ref={itemListRef}')
        end
      end

      it 'attaches no ref when no scroll control is declared' do
        expect(scrolling({})).not_to include('ref=')
      end

      # Without a literal id there is no stable variable name for the
      # converter and the generator to agree on, so the attributes would
      # silently do nothing.
      it 'warns instead of silently dropping the attributes when the id is missing' do
        converter = create_converter(
          { 'class' => 'Collection', 'scrollTo' => '@{scrollIndex}', 'cellClasses' => ['ItemCell'] }
        )
        expect { converter.convert }.to output(/literal `id`/).to_stderr
      end

      # currentPage read-back: `data.on<Prop>Change` is the same write-back
      # convention the inputs use, and comparing against the bound value keeps
      # a scroll from firing the handler on every frame.
      it 'reports the page back through the derived change handler' do
        result = scrolling('currentPage' => '@{page}')
        expect(result).to include('onScroll={')
        expect(result).to include('currentCollectionPage(itemListRef.current, false)')
        expect(result).to include('if (page !== data.page) data.onPageChange?.(page)')
      end

      it 'measures the horizontal axis for a horizontal collection' do
        result = scrolling('currentPage' => '@{page}', 'orientation' => 'horizontal')
        expect(result).to include('currentCollectionPage(itemListRef.current, true)')
      end

      it 'adds no scroll handler without currentPage' do
        expect(scrolling('scrollTo' => '@{scrollIndex}')).not_to include('onScroll=')
      end

      # The snap points have to be on the children, and the children are user
      # cell components — hence the arbitrary-variant class.
      it 'snaps children for paging' do
        expect(scrolling('paging' => true)).to include('snap-y snap-mandatory [&>*]:snap-start')
        expect(scrolling('paging' => true, 'orientation' => 'horizontal'))
          .to include('snap-x snap-mandatory [&>*]:snap-start')
      end

      it 'does not snap without paging' do
        expect(scrolling({})).not_to include('snap-')
      end
    end
  end
end
