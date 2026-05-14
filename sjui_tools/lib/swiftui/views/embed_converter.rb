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

          add_line 'EmbedContainer('
          indent do
            add_line "embedId: \"#{embed_id}\","
            add_line "screen: \"#{screen}\","
            add_line "navigationMode: .#{navigation_mode}"
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
        # Accepts both PascalCase ("OrderDetail") and snake_case ("order_detail").
        def embedded_view_name(screen)
          if screen.include?('_')
            screen.split('_').map(&:capitalize).join + 'View'
          else
            "#{screen}View"
          end
        end
      end
    end
  end
end
