# frozen_string_literal: true

require 'set'
require_relative '../core/layout_path'

module RjuiTools
  module React
    # The viewId of an id-less node is its position in the include-EXPANDED
    # tree (JsonUIShared::LayoutPath: `selectBox_0_3_1`), which is what sjui
    # and kjui stamp. rjui does not expand an include — it calls the included
    # layout's own component — so a node inside one is stamped from that
    # file's root, and the part of its path above the include has to come in
    # at run time: the component takes `jsonuiPath` (its own root's path in
    # the expanded tree) and the include site hands it the include node's.
    #
    # Only a layout that needs it takes it, so a layout whose includes hand
    # no viewId comes out as it did: one that someone includes and that holds
    # a node handing a viewId without an id (SelectBoxConverter
    # .hands_view_id?, BaseConverter.tap_hands_view_id? — a tap whose
    # handler the data declares `(String)`), itself or in a layout it
    # includes.
    module IncludePaths
      module_function

      # The raw file stems (an include's basename) of the layouts that take
      # `jsonuiPath`, from { stem => tree }.
      def stems_taking_path(trees)
        includes = trees.transform_values { |tree| include_stems(tree) }
        needs = trees.select { |_, tree| view_id_without_id?(tree) }.keys.to_set
        loop do
          grown = includes.select { |stem, inner| !needs.include?(stem) && inner.any? { |s| needs.include?(s) } }.keys
          break if grown.empty?

          needs.merge(grown)
        end
        needs & includes.values.flatten.to_set
      end

      # The basename of every include in the tree.
      def include_stems(node, stems = [])
        case node
        when Hash
          stems << node['include'].split('/').last if node['include'].is_a?(String)
          node.each_value { |value| include_stems(value, stems) }
        when Array
          node.each { |value| include_stems(value, stems) }
        end
        stems
      end

      def view_id_without_id?(tree)
        classes = declared_data_classes(tree)
        nodes(tree).any? do |node|
          node['id'].nil? &&
            (Converters::SelectBoxConverter.hands_view_id?(node, classes) || Converters::BaseConverter.tap_hands_view_id?(node, classes))
        end
      end

      # name => class, for every entry of every `data` list in the tree — the
      # root's and a data-only child's alike.
      def declared_data_classes(node, classes = {})
        case node
        when Hash
          Array(node['data']).each do |entry|
            classes[entry['name']] = entry['class'] if entry.is_a?(Hash) && entry['name'].is_a?(String)
          end
          node.each { |key, value| declared_data_classes(value, classes) unless key == 'data' }
        when Array
          node.each { |value| declared_data_classes(value, classes) }
        end
        classes
      end

      def nodes(node, out = [])
        case node
        when Hash
          out << node
          node.each_value { |value| nodes(value, out) }
        when Array
          node.each { |value| nodes(value, out) }
        end
        out
      end
    end
  end
end
