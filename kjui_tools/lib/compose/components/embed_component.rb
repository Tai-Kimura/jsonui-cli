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
          params = json_data['params'] || {}
          events = json_data['events'] || {}

          # Imports needed in the generated parent screen file.
          required_imports&.add(:embed_container)
          required_imports&.add(:viewmodel_compose)
          # The embedded screen's composable lives alongside other view files;
          # compose_builder's import resolver maps "tabview:Name" → import path
          # and APPENDS "View" itself (compose_builder.rb:1092). So we must
          # register the PascalCase name WITHOUT the "View" suffix — same
          # convention as TabView (`tabview_component.rb:25-26`). Registering
          # "HomeView" here would round-trip to "HomeViewView".
          required_imports&.add("tabview:#{embedded_screen_pascal(screen)}")
          required_imports&.add(:embedded_event) unless events.empty?

          code  = indent("// Embed: #{screen}", depth)
          code += "\n" + indent('EmbedContainer(', depth)
          code += "\n" + indent("embedId = \"#{embed_id}\",", depth + 1)
          unless params.empty?
            code += "\n" + indent('params = mapOf(', depth + 1)
            params.each_with_index do |(key, value), idx|
              expr = render_param_value(value)
              comma = idx == params.size - 1 ? '' : ','
              code += "\n" + indent("\"#{key}\" to #{expr}#{comma}", depth + 2)
            end
            code += "\n" + indent('),', depth + 1)
          end
          if events.empty?
            code += "\n" + indent("navigationMode = #{nav_mode_kotlin}", depth + 1)
          else
            code += "\n" + indent("navigationMode = #{nav_mode_kotlin},", depth + 1)
            code += "\n" + indent('eventBridge = { event ->', depth + 1)
            code += "\n" + indent('if (event is EmbeddedEvent.Named) {', depth + 2)
            code += "\n" + indent('when (event.name) {', depth + 3)
            events.each do |event_name, handler|
              code += "\n" + indent("\"#{event_name}\" -> viewModel.#{handler}(event.payload)", depth + 4)
            end
            code += "\n" + indent('}', depth + 3)
            code += "\n" + indent('}', depth + 2)
            code += "\n" + indent('}', depth + 1)
          end
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

        # Convert screen value (layout JSON filename, snake_case) to its
        # generated composable class name (PascalCase + "View").
        # PascalCase input passes through for backward compat.
        def self.embedded_view_class(screen)
          "#{embedded_screen_pascal(screen)}View"
        end

        # Just the PascalCase form of the screen name, without the "View" suffix.
        # Used for import registration (compose_builder appends "View" itself).
        def self.embedded_screen_pascal(screen)
          if screen.include?('_')
            screen.split('_').map(&:capitalize).join
          else
            screen[0].to_s.upcase + screen[1..].to_s
          end
        end

        # Render a single params value as Kotlin expression. Supports literals
        # and @{binding} → `data.{prop}`.
        def self.render_param_value(value)
          if value.is_a?(String) && value =~ /^@\{(.+)\}$/
            "data.#{Regexp.last_match(1)}"
          elsif value.is_a?(String)
            "\"#{value}\""
          elsif value == true || value == false
            value.to_s
          elsif value.is_a?(Integer)
            value.to_s
          elsif value.is_a?(Float)
            "#{value}f"
          else
            value.inspect
          end
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
