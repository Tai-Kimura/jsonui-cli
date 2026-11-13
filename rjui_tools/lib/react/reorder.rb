# frozen_string_literal: true

module RjuiTools
  module React
    # Whether a layout holds a reorderable Collection (ticket
    # jui-collection-drag-to-reorder, ruling B 2026-11-13): `rjui build`
    # writes the reorder helper (lib/react/templates/reorder.tsx) when one
    # does. CollectionConverter#reorder? decides which Collections the helper
    # wraps (v1: one vertical column); a reorderable grid is drawn as before.
    module Reorder
      module_function

      def used?(node)
        case node
        when Hash
          type = node['type'] || node['class']
          value = node['reorderable']
          return true if type == 'Collection' && (value == true || (value.is_a?(String) && value.include?('@{')))

          node.values.any? { |child| used?(child) }
        when Array
          node.any? { |child| used?(child) }
        else
          false
        end
      end
    end
  end
end
