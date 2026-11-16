# frozen_string_literal: true

require_relative '../view_binding_handler'

module SjuiTools
  module UIKit
    # CollectionViewBindingHandler handles UIKit binding for CollectionView components.
    # Supports binding UIKitCollectionDataSource to CollectionView via setupWithDataSource.
    class CollectionViewBindingHandler < ViewBindingHandler
      def handle_specific_binding(view_name, key, value)
        case key
        when "items"
          # items binds a UIKitCollectionDataSource to the CollectionView
          # Uses setupWithDataSource for initial setup and reloadWithDataSource for updates
          @binding_content << "        #{view_name}?.reloadWithDataSource(#{value})\n"
        when "scrollEnabled"
          @binding_content << "        #{view_name}?.isScrollEnabled = #{value}\n"
        when "pagingEnabled"
          @binding_content << "        #{view_name}?.isPagingEnabled = #{value}\n"
        when "showsHorizontalScrollIndicator"
          @binding_content << "        #{view_name}?.showsHorizontalScrollIndicator = #{value}\n"
        when "showsVerticalScrollIndicator"
          @binding_content << "        #{view_name}?.showsVerticalScrollIndicator = #{value}\n"
        when "contentInset"
          # contentInset expects UIEdgeInsets
          @binding_content << "        #{view_name}?.contentInset = #{value}\n"
        when "minimumLineSpacing"
          @binding_content << "        (#{view_name}?.collectionViewLayout as? UICollectionViewFlowLayout)?.minimumLineSpacing = #{value}\n"
        when "minimumInteritemSpacing"
          @binding_content << "        (#{view_name}?.collectionViewLayout as? UICollectionViewFlowLayout)?.minimumInteritemSpacing = #{value}\n"
        when "scrollDirection"
          # scrollDirection: "horizontal" or "vertical"
          @binding_content << "        if let flowLayout = #{view_name}?.collectionViewLayout as? UICollectionViewFlowLayout {\n"
          @binding_content << "            flowLayout.scrollDirection = #{value}.lowercased() == \"horizontal\" ? .horizontal : .vertical\n"
          @binding_content << "        }\n"
        else
          return false
        end
        true
      end
    end
  end
end
