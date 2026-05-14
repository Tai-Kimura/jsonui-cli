# frozen_string_literal: true

require_relative 'base_view_converter'

# Generates SwiftUI code for the `Embed` view type. Embeds another screen as
# a region of the parent layout; the embedded screen owns its own ViewModel.
#
# v1 (P1): emits EmbedContainer wrapping a direct call to the embedded screen's
# generated SwiftUI view. params/events wiring is deferred to P2.
#
# See jsonui-cli/docs/plans/2026-05-11-embed-feature.md.

module SjuiTools
  module SwiftUI
    module Views
      class EmbedConverter < BaseViewConverter
        def initialize(component, indent_level = 0, action_manager = nil, converter_factory = nil, view_registry = nil, binding_registry = nil)
          super(component, indent_level, action_manager, binding_registry)
          @converter_factory = converter_factory
          @view_registry = view_registry
        end

        def convert
          screen = @component['screen']
          if screen.nil? || screen.empty?
            add_line '// Embed: missing required `screen` attribute'
            return generated_code
          end

          embed_id = @component['id'] || 'embed'
          navigation_mode = @component['navigationMode'] || 'delegate'
          params = @component['params'] || {}
          events = @component['events'] || {}

          add_line 'EmbedContainer('
          indent do
            add_line "embedId: \"#{embed_id}\","
            add_line "screen: \"#{screen}\","
            unless params.empty?
              add_line 'params: ['
              indent do
                params.each_with_index do |(key, value), idx|
                  expr = render_param_value(value)
                  comma = idx == params.size - 1 ? '' : ','
                  add_line "\"#{key}\": #{expr}#{comma}"
                end
              end
              add_line '],'
            end
            if events.empty?
              add_line "navigationMode: .#{navigation_mode}"
            else
              add_line "navigationMode: .#{navigation_mode},"
              add_line 'eventBridge: { event in'
              indent do
                add_line 'if case .named(let name, let payload) = event {'
                indent do
                  events.each do |event_name, handler|
                    add_line "if name == \"#{event_name}\" { viewModel.#{handler}(payload) }"
                  end
                end
                add_line '}'
              end
              add_line '}'
            end
          end
          add_line ') {'
          indent do
            add_line "#{embedded_view_name(screen)}()"
          end
          add_line '}'

          apply_modifiers
          generated_code
        end

        private

        # Convert screen name to its generated View type name.
        # `screen` is the layout JSON filename (snake_case per spec); codegen
        # maps to PascalCase + "View" (e.g. "order_detail" → "OrderDetailView").
        # PascalCase input is accepted (passes through) for backward compat.
        def embedded_view_name(screen)
          base = if screen.include?('_')
                   screen.split('_').map(&:capitalize).join
                 else
                   # PascalCase passthrough: ensure first letter is uppercase
                   # so "counter" → "CounterView", "Counter" → "CounterView".
                   screen[0].upcase + screen[1..].to_s
                 end
          "#{base}View"
        end

        # Render a single params value as Swift expression. Supports literals
        # (string/number/bool) and @{binding} → `data.{prop}`.
        def render_param_value(value)
          if value.is_a?(String) && is_binding?(value)
            "data.#{extract_binding_property(value)}"
          elsif value.is_a?(String)
            "\"#{value}\""
          elsif value == true || value == false
            value.to_s
          elsif value.is_a?(Numeric)
            value.to_s
          else
            # Fallback — emit as Any literal
            value.inspect
          end
        end
      end
    end
  end
end
