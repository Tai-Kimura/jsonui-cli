# frozen_string_literal: true

require_relative 'code_indent'
require_relative 'resource_resolver'
require_relative '../../core/type_synonyms'

module KjuiTools
  module Compose
    module Helpers
      # A container's `tintColor`, handed down to the controls inside it.
      #
      # tintColor is the accent of a node's operable parts — a control's
      # accent, a link's colour, the cursor — never the text colour
      # (jsonui-cli 1.9.0 ruling). sjui emits `.tint(...)` on every node that
      # declares it, and SwiftUI's `.tint` reaches the controls inside that
      # node. Here a node that holds other nodes — its children, or a layout
      # it draws in a composable of its own (a Collection's cells, an Embed's
      # screen, a TabView's tabs) — provides KotlinJsonUI's own
      # `LocalJsonUITint` around what it composes, and every control reads
      # its own tintColor first and the local second (`jsonUITintOr`). The
      # local is not `LocalContentColor`, which is the text colour the ruling
      # rules out. The KotlinJsonUI Dynamic runtime provides and reads the
      # same local, so a tint crosses an included layout on either path.
      module InheritedTint
        module_function

        # The Material controls' default accent: what `jsonUITintOr` falls
        # back to when no container handed a tint down.
        THEME_ACCENT = 'MaterialTheme.colorScheme.primary'

        # The types that compose a layout of their own (TapAccessibility's
        # drawn_elsewhere), whatever their children.
        HOLDERS = %w[Collection Embed TabView].freeze

        # The accent expression a control emits where it declares none of its
        # own: the handed-down tint, else `fallback`.
        def accent(required_imports, fallback = THEME_ACCENT)
          required_imports&.add(:jsonui_tint_or)
          required_imports&.add(:material_theme) if fallback.include?('MaterialTheme')
          "jsonUITintOr(#{fallback})"
        end

        # Whether `json_data` hands its tintColor down: it declares one and
        # holds other nodes.
        def hands_down?(json_data)
          return false unless json_data.is_a?(Hash)

          tint = json_data['tintColor']
          return false unless tint.is_a?(String) && !tint.empty?

          children?(json_data) || HOLDERS.include?(JsonUIShared::TypeSynonyms.drawn_type(json_data['type'].to_s))
        end

        def children?(json_data)
          %w[child children].any? do |key|
            value = json_data[key]
            (value.is_a?(Array) && value.any? { |c| c.is_a?(Hash) }) || value.is_a?(Hash)
          end
        end

        # `code` inside `CompositionLocalProvider(LocalJsonUITint provides
        # <tint>) { … }` when the node hands its tint down. The provider adds
        # no layout node, and its content lambda has no receiver, so a weight
        # / align / constrainAs on the node still resolves in the scope around
        # it.
        def provide(json_data, code, depth, required_imports)
          return code unless code.is_a?(String) && !code.strip.empty?
          return code unless hands_down?(json_data)

          tint = ResourceResolver.process_color(json_data['tintColor'], required_imports)
          return code unless tint

          required_imports&.add(:composition_local_provider)
          required_imports&.add(:local_jsonui_tint)
          # Parenthesised: a bound tint reads `data.x ?: Color.Unspecified`,
          # and an infix call binds tighter than `?:`.
          CodeIndent.pad("CompositionLocalProvider(LocalJsonUITint provides (#{tint})) {", depth) + "\n" +
            CodeIndent.shift(code.rstrip, 1) + "\n" +
            CodeIndent.pad('}', depth)
        end
      end
    end
  end
end
