# frozen_string_literal: true

require_relative 'resource_resolver'

module KjuiTools
  module Compose
    module Helpers
      # `common.tintColor` — the accent colour a node hands DOWN.
      #
      # Both other platforms treat it that way: sjui emits `.tint(...)`
      # (base_view_converter.rb) and rjui the CSS `accentColor`
      # (base_converter.rb), and both propagate to descendants rather than
      # painting the node. Compose's peer is `LocalContentColor`, which is a
      # CompositionLocal — so this is a wrapper, not a modifier, and that is
      # why the first attempt at this attribute (a `drawWithContent` scrim)
      # was withdrawn: it painted the node and its children flat, which is a
      # different thing entirely (plan 49 lane C).
      #
      # `CompositionLocalProvider` introduces NO layout node, so wrapping is
      # layout-neutral. What it does introduce is a plain `@Composable () ->
      # Unit` content lambda, and that is not a Row/Column/BoxScope receiver:
      # a wrapped child loses `Modifier.weight(...)` and `Modifier.align(...)`,
      # which do not resolve outside their scope. Those two are hoisted onto a
      # Box so the scope call stays where the scope is — the same problem
      # VisibilityHelper solves for VisibilityWrapper, minus the option of
      # putting them on the wrapper itself, because CompositionLocalProvider
      # takes no modifier.
      module TintHelper
        module_function

        SCOPE_BOUND = /^\s*\.(weight|align)\(/.freeze

        def declared?(json_data)
          json_data.is_a?(Hash) && json_data['tintColor'] && !json_data['tintColor'].to_s.empty?
        end

        # Wrap `code` so descendants inherit the tint. Returns `code` unchanged
        # when the attribute is absent.
        def wrap_with_tint(json_data, code, depth, required_imports)
          return code unless declared?(json_data)
          return code unless code.is_a?(String) && !code.empty?

          required_imports&.add(:composition_local_provider)
          required_imports&.add(:local_content_color)
          # process_color handles both a literal and a binding, and both a
          # String-typed and a Color-typed property. Emitting the property
          # bare is what stopped the ios host on `common/tintColor__binding`:
          # the binding survived, so codegen-effect passed it, and the type
          # did not — this path does not repeat that.
          color = ResourceResolver.process_color(json_data['tintColor'], required_imports)

          scope_lines = code.lines.select { |l| l =~ SCOPE_BOUND }
          inner = scope_lines.empty? ? code : code.lines.reject { |l| l =~ SCOPE_BOUND }.join

          # `provides` is an infix call and `?:` binds looser than one, so
          # `provides X ?: Y` parses as `(provides X) ?: Y` — the infix gets a
          # `Color?` and the whole expression becomes a `ProvidedValue?`. The
          # colour expression is only precedence-safe inside an argument list,
          # which is where every other caller of process_color puts it.
          provider = pad("CompositionLocalProvider(LocalContentColor provides (#{color})) {", depth) + "\n" +
                     shift(inner.rstrip, 1) + "\n" +
                     pad('}', depth)
          return provider if scope_lines.empty?

          # A weighted or aligned node: the scope call has to stay in the
          # scope, so a Box takes it and the provider sits inside.
          required_imports&.add(:box)
          pad('Box(', depth) + "\n" +
            pad('modifier = Modifier', depth + 1) + "\n" +
            scope_lines.map { |l| pad(l.strip, depth + 2) }.join("\n") + "\n" +
            pad(') {', depth) + "\n" +
            shift(provider, 1) + "\n" +
            pad('}', depth)
        end

        def pad(text, level)
          return text if level.to_i <= 0

          ('    ' * level) + text
        end

        def shift(text, levels)
          prefix = '    ' * levels
          text.split("\n").map { |l| l.empty? ? l : prefix + l }.join("\n")
        end
      end
    end
  end
end
