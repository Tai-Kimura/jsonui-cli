# frozen_string_literal: true

module JsonUIShared
  # A node's position in its layout, as a name — for a node that needs a name
  # the layout does not give it (kjui: a Radio item's value; sjui: a stateful
  # node's state declaration). One rule for the sjui and kjui codegen, both
  # running shared/core/layout_path_vectors.json from byte-identical copies.
  #
  # An explicit `id` wins; this is the name when there is none. It is the same
  # on every build (a function of the tree alone — no counter, no randomness,
  # no per-kind fixed name) and unique within the view.
  #
  # The root is `0`; each step appends `_<index>` of the node in its parent's
  # child list — `0_2_1` is the second child (index 1) of the root's third
  # child (index 2). The index is the position as written: a single-object
  # `child` is index 0; a non-object entry still takes its index; a node that
  # carries both `child` and `children` counts them as one list, `child`
  # first (TapAccessibility.children's order), so no two siblings share one.
  #
  # The tree stamped is the include-expanded, style-merged one — the tree the
  # tap shapes are annotated on. An include is replaced by the root it
  # expands to, so it takes one index.
  #
  # The path changes when a node is inserted, removed or moved BEFORE the node
  # or before one of its ancestors in that ancestor's parent's list, or when
  # the node or an ancestor is wrapped in a new container. Nothing after the
  # path moves it. A layout variant file (home@regular) has its own root, so
  # the same node may get a different path there than in the base layout.
  module LayoutPath
    module_function

    KEY = '_layoutPath'

    # Writes KEY on every object node of the tree, `path` being the root's.
    def stamp!(node, path = '0')
      return node unless node.is_a?(Hash)

      node[KEY] = path
      children(node).each_with_index { |child, i| stamp!(child, "#{path}_#{i}") }
      node
    end

    def stamped?(node)
      node.is_a?(Hash) && node.key?(KEY)
    end

    # The child list positions count over: `child` then `children`, every
    # entry, object or not.
    def children(node)
      %w[child children].flat_map do |key|
        value = node[key]
        case value
        when Array then value
        when Hash then [value]
        else []
        end
      end
    end
  end
end
