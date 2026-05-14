# frozen_string_literal: true

# Generates Compose code for the `Embed` view type. Embeds another screen as
# a region of the parent layout; the embedded screen owns its own ViewModel.
#
# v1 (P1): emits EmbedContainer wrapping a direct call to the embedded
# screen's generated composable. params/events wiring is added in P2.
#
# See jsonui-cli/docs/plans/2026-05-11-embed-feature.md.

module KjuiTools
  module Compose
    module Components
      class EmbedComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          screen = json_data['screen']
          if screen.nil? || screen.to_s.empty?
            return indent('// Embed: missing required `screen` attribute', depth)
          end

          embed_id = json_data['id'] || 'embed'
          navigation_mode = json_data['navigationMode'] || 'delegate'
          nav_mode_kotlin = navigation_mode == 'isolated' ? 'EmbedNavigationMode.Isolated' : 'EmbedNavigationMode.Delegate'

          # Imports needed in the generated parent screen file.
          required_imports&.add(:embed_container)
          required_imports&.add(:viewmodel_compose)
          # The embedded screen's composable lives alongside other view files;
          # compose_builder's import resolver maps "tabview:Name" → import path.
          # We reuse the same convention so the Embed reference is wired through.
          required_imports&.add("tabview:#{embedded_view_class(screen)}")

          code  = indent("// Embed: #{screen}", depth)
          code += "\n" + indent('EmbedContainer(', depth)
          code += "\n" + indent("embedId = \"#{embed_id}\",", depth + 1)
          code += "\n" + indent("navigationMode = #{nav_mode_kotlin}", depth + 1)
          code += "\n" + indent(') { embedScope ->', depth)
          code += "\n" + indent("#{embedded_view_class(screen)}(", depth + 1)
          code += "\n" + indent('viewModel = androidx.lifecycle.viewmodel.compose.viewModel(', depth + 2)
          code += "\n" + indent('viewModelStoreOwner = embedScope.viewModelStoreOwner,', depth + 3)
          code += "\n" + indent("key = \"#{embed_id}\"", depth + 3)
          code += "\n" + indent(')', depth + 2)
          code += "\n" + indent(')', depth + 1)
          code += "\n" + indent('}', depth)
          code
        end

        def self.embedded_view_class(screen)
          # Accept both PascalCase ("OrderDetail") and snake_case ("order_detail").
          base = screen.include?('_') ? screen.split('_').map(&:capitalize).join : screen
          "#{base}View"
        end

        def self.indent(text, level)
          return text if level == 0
          spaces = '    ' * level
          text.split("\n").map { |line|
            line.empty? ? line : spaces + line
          }.join("\n")
        end
      end
    end
  end
end
