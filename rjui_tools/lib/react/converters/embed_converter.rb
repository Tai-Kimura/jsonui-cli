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
          screen = json['screen']
          if screen.nil? || screen.to_s.empty?
            return "#{indent_str(indent)}{/* Embed: missing required `screen` attribute */}"
          end

          embed_id = json['id'] || 'embed'
          navigation_mode = json['navigationMode'] || 'delegate'
          class_name = build_class_name
          embedded_component = embedded_component_name(screen)

          class_attr = class_name.empty? ? '' : %( className="#{class_name}")

          <<~JSX.chomp
            #{indent_str(indent)}<EmbedContainer
            #{indent_str(indent + 2)}embedId="#{embed_id}"
            #{indent_str(indent + 2)}screen="#{screen}"
            #{indent_str(indent + 2)}navigationMode="#{navigation_mode}"#{class_attr}
            #{indent_str(indent)}>
            #{indent_str(indent + 2)}<#{embedded_component} />
            #{indent_str(indent)}</EmbedContainer>
          JSX
        end

        private

        # Convert screen name to its generated component name.
        # Accepts both PascalCase ("OrderDetail") and snake_case ("order_detail").
        def embedded_component_name(screen)
          if screen.include?('_')
            screen.split('_').map(&:capitalize).join
          else
            screen
          end
        end
      end
    end
  end
end
