# frozen_string_literal: true

require 'json'
require 'set'
require_relative 'include_expander'
require_relative '../core/screen_index'

module SjuiTools
  module SwiftUI
    # Which elements of which layouts a reorderable Collection picks its rows up by (ticket
    # jui-collection-drag-to-reorder): a Collection with `reorderable`, `onReorder` and `reorderHandle` draws its
    # cells from layouts of their own, so the handle — an element of the CELL's layout, named by id — is marked in
    # that layout's file (`.collectionReorderHandle()`, BaseViewConverter after the identifier), not in the Collection's.
    # Built over the whole layouts directory: { cell layout id => Set of handle ids }. Empty when it is absent.
    module ReorderHandleIndex
      def self.build(layouts_dir)
        root = layouts_dir.to_s
        index = Hash.new { |h, k| h[k] = Set.new }
        return {} unless layouts_dir && File.directory?(root)

        Dir.glob(File.join(root, '**', '*.json')).sort.each do |path|
          dirs = File.dirname(path).delete_prefix(root).split(File::SEPARATOR)
          next if (dirs & JsonUIShared::ScreenIndex::NON_LAYOUT_SUBTREES).any?

          tree = begin
            JSON.parse(File.read(path))
          rescue StandardError
            next
          end
          tree = begin
            IncludeExpander.process_includes(tree, File.dirname(path), nil, root)
          rescue StandardError
            tree
          end
          collect(tree, index)
        end
        index.transform_values(&:freeze)
      end

      def self.collect(node, index)
        case node
        when Array then node.each { |n| collect(n, index) }
        when Hash
          handle = node['reorderHandle']
          if node['type'] == 'Collection' && handle.is_a?(String) && !handle.empty? && declared?(node)
            cell_refs(node).each { |ref| index[JsonUIShared::ScreenIndex.screen_id_for_path(ref)] << handle }
          end
          node.each_value { |v| collect(v, index) if v.is_a?(Hash) || v.is_a?(Array) }
        end
      end

      def self.declared?(node)
        r = node['reorderable']
        !(r.nil? || r == false || r == 'false') && node['onReorder'].is_a?(String) && !node['onReorder'].empty?
      end

      # The layouts a Collection draws its rows with: each section's cell, and the legacy cellClasses.
      def self.cell_refs(node)
        refs = []
        Array(node['sections']).each { |s| refs << s['cell'] if s.is_a?(Hash) && s['cell'].is_a?(String) }
        Array(node['cellClasses']).each do |c|
          refs << (c.is_a?(Hash) ? c['className'] : c) if c.is_a?(String) || c.is_a?(Hash)
        end
        refs.compact.reject(&:empty?)
      end
    end
  end
end
