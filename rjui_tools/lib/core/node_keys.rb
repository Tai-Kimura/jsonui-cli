# frozen_string_literal: true

require_relative 'layout_path'

module RjuiTools
  module Core
    # The keys a layout node was written with. The generator stamps every node
    # it converts with its position (JsonUIShared::LayoutPath::KEY), so a
    # predicate over a node's key set that counts the stamp judges a node the
    # layout did not write: from 2de6da9b a data-only element `{ "data": [...] }`
    # was drawn as an empty <div /> on every web face that declares its data
    # that way. Every predicate over a node's keys reads them through here.
    module NodeKeys
      STAMPS = [JsonUIShared::LayoutPath::KEY].freeze

      module_function

      def written(node)
        node.keys - STAMPS
      end
    end
  end
end
