# frozen_string_literal: true

require 'uikit/handlers/collection_view_binding_handler'

RSpec.describe SjuiTools::UIKit::CollectionViewBindingHandler do
  let(:binding_content) { [] }
  let(:reset_text_views) { {} }
  let(:reset_constraint_views) { {} }
  let(:handler) { described_class.new(binding_content, reset_text_views, reset_constraint_views) }

  describe '#handle_specific_binding' do
    it 'handles items binding with reloadWithDataSource' do
      result = handler.handle_specific_binding('collectionView', 'items', 'model.dataSource')

      expect(result).to be true
      expect(binding_content.join).to include('collectionView?.reloadWithDataSource(model.dataSource)')
    end

    it 'handles scrollEnabled' do
      result = handler.handle_specific_binding('collectionView', 'scrollEnabled', 'true')

      expect(result).to be true
      expect(binding_content.join).to include('collectionView?.isScrollEnabled = true')
    end

    it 'handles pagingEnabled' do
      result = handler.handle_specific_binding('collectionView', 'pagingEnabled', 'true')

      expect(result).to be true
      expect(binding_content.join).to include('collectionView?.isPagingEnabled = true')
    end

    it 'handles showsHorizontalScrollIndicator' do
      result = handler.handle_specific_binding('collectionView', 'showsHorizontalScrollIndicator', 'false')

      expect(result).to be true
      expect(binding_content.join).to include('collectionView?.showsHorizontalScrollIndicator = false')
    end

    it 'handles showsVerticalScrollIndicator' do
      result = handler.handle_specific_binding('collectionView', 'showsVerticalScrollIndicator', 'false')

      expect(result).to be true
      expect(binding_content.join).to include('collectionView?.showsVerticalScrollIndicator = false')
    end

    it 'handles contentInset' do
      result = handler.handle_specific_binding('collectionView', 'contentInset', 'UIEdgeInsets(top: 10, left: 0, bottom: 10, right: 0)')

      expect(result).to be true
      expect(binding_content.join).to include('collectionView?.contentInset = UIEdgeInsets')
    end

    it 'handles minimumLineSpacing' do
      result = handler.handle_specific_binding('collectionView', 'minimumLineSpacing', '10')

      expect(result).to be true
      expect(binding_content.join).to include('collectionViewLayout as? UICollectionViewFlowLayout)?.minimumLineSpacing = 10')
    end

    it 'handles minimumInteritemSpacing' do
      result = handler.handle_specific_binding('collectionView', 'minimumInteritemSpacing', '5')

      expect(result).to be true
      expect(binding_content.join).to include('collectionViewLayout as? UICollectionViewFlowLayout)?.minimumInteritemSpacing = 5')
    end

    it 'handles scrollDirection' do
      result = handler.handle_specific_binding('collectionView', 'scrollDirection', '"horizontal"')

      expect(result).to be true
      content = binding_content.join
      expect(content).to include('flowLayout.scrollDirection')
      expect(content).to include('.horizontal')
    end

    it 'returns false for unknown key' do
      result = handler.handle_specific_binding('collectionView', 'unknownKey', 'value')

      expect(result).to be false
    end
  end
end
