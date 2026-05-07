# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'

module KjuiTools
  module Compose
    module Components
      # SwitchComponent handles both Switch (primary) and Toggle (alias) component types
      # Switch is the primary component name. Toggle is supported as an alias for backward compatibility.
      class SwitchComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # Switch/Toggle uses 'isOn', 'value', 'checked', or 'bind' for binding
          # Priority: isOn > value > checked > bind
          state_attr = json_data['isOn'] || json_data['value'] || json_data['checked']
          checked = if state_attr
            if state_attr.is_a?(String) && state_attr.match(/@\{([^}]+)\}/)
              variable = $1
              "data.#{variable}"
            else
              # Direct boolean value
              state_attr.to_s
            end
          elsif json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
            variable = $1
            "data.#{variable}"
          else
            'false'
          end

          has_label = json_data['labelAttributes']

          if has_label
            generate_with_label(json_data, depth, required_imports, parent_type, checked)
          else
            generate_switch_only(json_data, depth, required_imports, parent_type, checked)
          end
        end

        def self.generate_switch_only(json_data, depth, required_imports, parent_type, checked)
          code = indent("Switch(", depth)
          code += "\n" + indent("checked = #{checked},", depth + 1)

          # onCheckedChange handler
          binding_variable = nil
          state_attr_val = json_data['isOn'] || json_data['value'] || json_data['checked']
          if state_attr_val.is_a?(String) && state_attr_val.match(/@\{([^}]+)\}/)
            binding_variable = $1
          elsif json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
            binding_variable = $1
          end

          # onToggle and onValueChange are aliases
          # onValueChange (camelCase) -> binding format only (@{functionName})
          handler = json_data['onValueChange'] || json_data['onToggle']
          view_id = json_data['id'] || 'switch'
          if handler
            # onValueChange must be binding format
            if Helpers::ModifierBuilder.is_binding?(handler)
              handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(handler, view_id, 'newValue')
              if binding_variable
                # Both data binding and event handler
                code += "\n" + indent("onCheckedChange = { newValue -> viewModel.updateData(mapOf(\"#{binding_variable}\" to newValue)); #{handler_call} },", depth + 1)
              else
                # Event handler only
                code += "\n" + indent("onCheckedChange = { newValue -> #{handler_call} },", depth + 1)
              end
            else
              code += "\n" + indent("onCheckedChange = { // ERROR: #{handler} - camelCase events require binding format @{functionName} },", depth + 1)
            end
          elsif binding_variable
            # Update the bound variable only
            code += "\n" + indent("onCheckedChange = { newValue -> viewModel.updateData(mapOf(\"#{binding_variable}\" to newValue)) },", depth + 1)
          else
            code += "\n" + indent("onCheckedChange = { },", depth + 1)
          end

          # Build modifiers
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_alignment(json_data, required_imports, parent_type))

          # Add weight modifier if in Row or Column
          if parent_type == 'Row' || parent_type == 'Column'
            modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
          end

          code += Helpers::ModifierBuilder.format(modifiers, depth) if modifiers.any?

          # Switch colors
          # tint and tintColor are aliases for onTintColor
          track_color = json_data['onTintColor'] || json_data['tint'] || json_data['tintColor']
          if track_color || json_data['thumbTintColor']
            required_imports&.add(:switch_colors)
            colors_params = []

            if track_color
              checkedtrackcolor_resolved = Helpers::ResourceResolver.process_color(track_color, required_imports)
              colors_params << "checkedTrackColor = #{checkedtrackcolor_resolved}"
            end

            if json_data['thumbTintColor']
              checkedthumbcolor_resolved = Helpers::ResourceResolver.process_color(json_data['thumbTintColor'], required_imports)
              colors_params << "checkedThumbColor = #{checkedthumbcolor_resolved}"
            end

            if colors_params.any?
              code += ",\n" + indent("colors = SwitchDefaults.colors(", depth + 1)
              code += "\n" + colors_params.map { |param| indent(param, depth + 2) }.join(",\n")
              code += "\n" + indent(")", depth + 1)
            end
          end

          # Handle enabled attribute
          if json_data.key?('enabled')
            if json_data['enabled'].is_a?(String) && json_data['enabled'].start_with?('@{')
              variable = json_data['enabled'].match(/@\{([^}]+)\}/)[1]
              code += ",\n" + indent("enabled = data.#{variable}", depth + 1)
            else
              code += ",\n" + indent("enabled = #{json_data['enabled']}", depth + 1)
            end
          end

          code += "\n" + indent(")", depth)
          code
        end

        def self.generate_with_label(json_data, depth, required_imports, parent_type, checked)
          label_attrs = json_data['labelAttributes']

          # Row container for label + switch
          code = indent("Row(", depth)
          code += "\n" + indent("verticalAlignment = Alignment.CenterVertically,", depth + 1)

          # Build modifiers for Row
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))

          if parent_type == 'Row' || parent_type == 'Column'
            modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
          end

          code += Helpers::ModifierBuilder.format(modifiers, depth) if modifiers.any?
          code += "\n" + indent(") {", depth)

          # Label Text
          label_text = label_attrs['text'] || ''
          code += "\n" + indent("Text(", depth + 1)
          code += "\n" + indent("text = \"#{label_text}\",", depth + 2)

          # Font attributes
          if label_attrs['fontSize']
            code += "\n" + indent("fontSize = #{label_attrs['fontSize']}.sp,", depth + 2)
          end

          if label_attrs['fontColor']
            font_color = Helpers::ResourceResolver.process_color(label_attrs['fontColor'], required_imports)
            code += "\n" + indent("color = #{font_color},", depth + 2)
          end

          if label_attrs['font']
            font_weight = label_attrs['font'].downcase == 'bold' ? 'FontWeight.Bold' : 'FontWeight.Normal'
            code += "\n" + indent("fontWeight = #{font_weight},", depth + 2)
          end

          code += "\n" + indent("modifier = Modifier.weight(1f)", depth + 2)
          code += "\n" + indent(")", depth + 1)

          # Switch
          code += "\n" + indent("Switch(", depth + 1)
          code += "\n" + indent("checked = #{checked},", depth + 2)

          # onCheckedChange handler
          binding_variable = nil
          state_attr_val = json_data['isOn'] || json_data['value'] || json_data['checked']
          if state_attr_val.is_a?(String) && state_attr_val.match(/@\{([^}]+)\}/)
            binding_variable = $1
          elsif json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
            binding_variable = $1
          end

          handler = json_data['onValueChange'] || json_data['onToggle']
          view_id = json_data['id'] || 'switch'
          if handler
            # onValueChange (camelCase) -> binding format only (@{functionName})
            if Helpers::ModifierBuilder.is_binding?(handler)
              handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(handler, view_id, 'newValue')
              if binding_variable
                # Both data binding and event handler
                code += "\n" + indent("onCheckedChange = { newValue -> viewModel.updateData(mapOf(\"#{binding_variable}\" to newValue)); #{handler_call} }", depth + 2)
              else
                # Event handler only
                code += "\n" + indent("onCheckedChange = { newValue -> #{handler_call} }", depth + 2)
              end
            else
              code += "\n" + indent("onCheckedChange = { // ERROR: #{handler} - camelCase events require binding format @{functionName} }", depth + 2)
            end
          elsif binding_variable
            code += "\n" + indent("onCheckedChange = { newValue -> viewModel.updateData(mapOf(\"#{binding_variable}\" to newValue)) }", depth + 2)
          else
            code += "\n" + indent("onCheckedChange = { }", depth + 2)
          end

          # Switch colors
          track_color = json_data['onTintColor'] || json_data['tint'] || json_data['tintColor']
          if track_color || json_data['thumbTintColor']
            required_imports&.add(:switch_colors)
            colors_params = []

            if track_color
              checkedtrackcolor_resolved = Helpers::ResourceResolver.process_color(track_color, required_imports)
              colors_params << "checkedTrackColor = #{checkedtrackcolor_resolved}"
            end

            if json_data['thumbTintColor']
              checkedthumbcolor_resolved = Helpers::ResourceResolver.process_color(json_data['thumbTintColor'], required_imports)
              colors_params << "checkedThumbColor = #{checkedthumbcolor_resolved}"
            end

            if colors_params.any?
              code += ",\n" + indent("colors = SwitchDefaults.colors(", depth + 2)
              code += "\n" + colors_params.map { |param| indent(param, depth + 3) }.join(",\n")
              code += "\n" + indent(")", depth + 2)
            end
          end

          # Handle enabled attribute
          if json_data.key?('enabled')
            if json_data['enabled'].is_a?(String) && json_data['enabled'].start_with?('@{')
              variable = json_data['enabled'].match(/@\{([^}]+)\}/)[1]
              code += ",\n" + indent("enabled = data.#{variable}", depth + 2)
            else
              code += ",\n" + indent("enabled = #{json_data['enabled']}", depth + 2)
            end
          end

          code += "\n" + indent(")", depth + 1)
          code += "\n" + indent("}", depth)
          code
        end

        private

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
