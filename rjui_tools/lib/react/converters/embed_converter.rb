# frozen_string_literal: true

require_relative 'base_converter'

# Generates React/Next.js code for the `Embed` view type. Embeds another
# screen as a region of the parent layout; the embedded screen owns its own
# ViewModel via hook scoping (each <EmbeddedScreen /> render call gets its
# own hook closure, naturally isolated from the parent).
#
# v1 (P1): emits <EmbedContainer> wrapping a direct call to the embedded
# screen component. params/events wiring is added in P2.
#
# See jsonui-cli/docs/plans/2026-05-11-embed-feature.md.

module RjuiTools
  module React
    module Converters
      class EmbedConverter < BaseConverter
        def convert(indent = 2)
          screen = attributes['screen']
          if screen.nil? || screen.to_s.empty?
            return "#{indent_str(indent)}{/* Embed: missing required `screen` attribute */}"
          end

          embed_id = attributes['id'] || 'embed'
          navigation_mode = attributes['navigationMode'] || 'delegate'
          class_name = build_class_name
          embedded_component = embedded_component_name(screen)
          params_attr = build_params_attr(attributes['params'])
          event_bridge_attr = build_event_bridge_attr(attributes['events'])

          class_attr = class_name.empty? ? '' : %( className="#{class_name}")

          <<~JSX.chomp
            #{indent_str(indent)}<EmbedContainer
            #{indent_str(indent + 2)}embedId="#{embed_id}"
            #{indent_str(indent + 2)}screen="#{screen}"
            #{indent_str(indent + 2)}navigationMode="#{navigation_mode}"#{params_attr}#{event_bridge_attr}#{class_attr}
            #{indent_str(indent)}>
            #{indent_str(indent + 2)}<#{embedded_component} />
            #{indent_str(indent)}</EmbedContainer>
          JSX
        end

        private

        # Convert screen name (layout JSON filename, snake_case) to its
        # generated component name (PascalCase). Backward-compat with PascalCase input.
        def embedded_component_name(screen)
          if screen.include?('_')
            screen.split('_').map(&:capitalize).join
          else
            # PascalCase passthrough: capitalize first letter.
            screen[0].to_s.upcase + screen[1..].to_s
          end
        end

        def build_params_attr(params)
          return '' if params.nil? || params.empty?
          entries = params.map do |key, value|
            "#{key}: #{render_param_value(value)}"
          end
          "\n        params={{ #{entries.join(', ')} }}"
        end

        def build_event_bridge_attr(events)
          return '' if events.nil? || events.empty?
          cases = events.map do |event_name, handler|
            "if (event.type === '#{event_name}') viewModel.#{handler}(event.payload);"
          end
          "\n        eventBridge={(event) => { #{cases.join(' ')} }}"
        end

        # Render a single params value as JS expression. Supports literals
        # and @{binding} → `data.{prop}`.
        def render_param_value(value)
          if value.is_a?(String) && value =~ /^@\{(.+)\}$/
            "data.#{Regexp.last_match(1)}"
          elsif value.is_a?(String)
            "'#{value.gsub("'", "\\\\'")}'"
          elsif value == true || value == false
            value.to_s
          elsif value.is_a?(Numeric)
            value.to_s
          else
            value.to_json
          end
        end
      end
    end
  end
end
