# frozen_string_literal: true

module KjuiTools
  module Compose
    module Helpers
      # `safeAreaInsetPositions` — the edges a node reserves, for the plain
      # node (ModifierBuilder) and SafeAreaView (ComposeBuilder) alike.
      #
      # The six declared words, as written (4f ruling, 2026-09-26, the same
      # on every path): `top` / `bottom` are that edge; `leading` is where
      # reading starts and `trailing` where it ends (WindowInsetsSides.Start /
      # End); `vertical` is top and bottom; `all` is every edge. Any other
      # word — `start`, `end`, `left`, `right`, `horizontal`, another case —
      # reserves no edge.
      #
      # The two paths read the words apart: the plain node took `vertical`
      # and SafeAreaView did not, neither took `leading` / `trailing`, and
      # SafeAreaView turned `all` minus a TabView's bottom into `start` /
      # `end`, which it then drew nothing for. Each edge is the system bars'
      # inset on that side only — the navigation bar sits on a side in
      # landscape, where `navigationBarsPadding` reserved it for a `bottom`.
      # A TabView reserves its content's bottom (LocalSafeAreaConfig), and
      # both paths leave that edge to it, as KotlinJsonUI's Dynamic does.
      module SafeAreaEdges
        # Declared word -> the edges it reserves. `SIDES` order is the order
        # the paddings are emitted in.
        WORDS = {
          'top' => %w[top],
          'bottom' => %w[bottom],
          'leading' => %w[leading],
          'trailing' => %w[trailing],
          'vertical' => %w[top bottom],
          'all' => %w[top bottom leading trailing]
        }.freeze
        SIDES = { 'top' => 'Top', 'bottom' => 'Bottom', 'leading' => 'Start', 'trailing' => 'End' }.freeze
        # The edge an enclosing TabView may already reserve, and its flag.
        CONFIG_FLAGS = { 'top' => 'ignoreTop', 'bottom' => 'ignoreBottom' }.freeze

        module_function

        # The edges the written positions reserve, in emit order. A single
        # string is read as a one-item list, as before.
        def edges(positions)
          words = positions.is_a?(Array) ? positions : [positions]
          named = words.flat_map { |w| WORDS[w.is_a?(String) ? w : nil] || [] }
          SIDES.keys.select { |side| named.include?(side) }
        end

        # The modifiers reserving `edges`. `config` is the Kotlin expression
        # of the enclosing SafeAreaConfig.
        def modifiers(edges, config, required_imports = nil)
          return [] if edges.empty?

          required_imports&.add(:safe_area_sides)
          required_imports&.add(:safe_area_config)
          lines = CONFIG_FLAGS.keys.select { |side| edges.include?(side) }.map do |side|
            ".then(if (!#{config}.#{CONFIG_FLAGS[side]}) Modifier.#{padding([side])} else Modifier)"
          end
          horizontal = edges - CONFIG_FLAGS.keys
          lines << ".#{padding(horizontal)}" unless horizontal.empty?
          lines
        end

        def padding(sides)
          "windowInsetsPadding(WindowInsets.systemBars.only(#{sides.map { |s| "WindowInsetsSides.#{SIDES[s]}" }.join(' + ')}))"
        end
      end
    end
  end
end
