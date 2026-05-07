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
  end
end
