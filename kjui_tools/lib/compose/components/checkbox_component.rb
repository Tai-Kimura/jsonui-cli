# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'

module KjuiTools
  module Compose
    module Components
      # CheckBox Component Generator
      # CheckBox is the primary component name. Check is supported as an alias for backward compatibility.
      # Both "CheckBox" and "Check" JSON types map to this component.
      class CheckboxComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # CheckBox uses 'isOn', 'checked', or 'bind' for binding
          # Priority: isOn > checked > bind
          state_attr = json_data['isOn'] || json_data['checked']
          checked = if state_attr
            if state_attr.is_a?(String) && state_attr.match(/@\{([^}]+)\}/)
              variable = $1
              "data.#{variable}"
            else
              state_attr.to_s
            end
          elsif json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
            variable = $1
            "data.#{variable}"
          else
            'false'
          end

          has_label = json_data['label'] || json_data['text']
          has_custom_icon = json_data['icon'] || json_data['selectedIcon']

          # If custom icons are specified, use IconToggleButton instead of Checkbox
          if has_custom_icon
            return generate_icon_checkbox(json_data, depth, required_imports, parent_type, checked)
          end

          if has_label
            # Checkbox with label
            code = indent("Row(", depth)
            code += "\n" + indent("verticalAlignment = Alignment.CenterVertically,", depth + 1)

            # Build modifiers for Row
            modifiers = []
            modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
            modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
            modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
            modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))

            code += Helpers::ModifierBuilder.format(modifiers, depth) if modifiers.any?
            code += "\n" + indent(") {", depth)

            # Checkbox
            code += "\n" + indent("Checkbox(", depth + 1)
            code += "\n" + indent("checked = #{checked},", depth + 2)

            # onCheckedChange handler
            binding_variable = nil
            state_attr_val = json_data['isOn'] || json_data['checked']
            if state_attr_val.is_a?(String) && state_attr_val.match(/@\{([^}]+)\}/)
              binding_variable = $1
            elsif json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
              binding_variable = $1
            end

            view_id = json_data['id'] || 'checkbox'
            if json_data['onValueChange']
              # onValueChange (camelCase) -> binding format only (@{functionName})
              if Helpers::ModifierBuilder.is_binding?(json_data['onValueChange'])
                handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(json_data['onValueChange'], view_id, 'it')
                if binding_variable
                  code += "\n" + indent("onCheckedChange = { newValue -> viewModel.updateData(mapOf(\"#{binding_variable}\" to newValue)); #{handler_call} }", depth + 2)
                else
                  code += "\n" + indent("onCheckedChange = { #{handler_call} }", depth + 2)
                end
              else
                code += "\n" + indent("onCheckedChange = { // ERROR: #{json_data['onValueChange']} - camelCase events require binding format @{functionName} }", depth + 2)
              end
            elsif binding_variable
              code += "\n" + indent("onCheckedChange = { newValue -> viewModel.updateData(mapOf(\"#{binding_variable}\" to newValue)) }", depth + 2)
            else
              code += "\n" + indent("onCheckedChange = { }", depth + 2)
            end

            code += "\n" + indent(")", depth + 1)

            # Spacer with configurable spacing
            spacing = json_data['spacing'] || 8
            code += "\n" + indent("Spacer(modifier = Modifier.width(#{spacing}.dp))", depth + 1)

            # Label text with font attributes
            label_text = json_data['label'] || json_data['text']
            text_params = ["text = \"#{label_text}\""]

            if json_data['fontSize']
              text_params << "fontSize = #{json_data['fontSize']}.sp"
            end

            if json_data['fontColor']
              font_color = Helpers::ResourceResolver.process_color(json_data['fontColor'], required_imports)
              text_params << "color = #{font_color}"
            end

            if json_data['font']
              font_weight = json_data['font'].downcase == 'bold' ? 'FontWeight.Bold' : 'FontWeight.Normal'
              text_params << "fontWeight = #{font_weight}"
            end

            if text_params.size == 1
              code += "\n" + indent("Text(\"#{label_text}\")", depth + 1)
            else
              code += "\n" + indent("Text(", depth + 1)
              code += "\n" + text_params.map { |param| indent(param, depth + 2) }.join(",\n")
              code += "\n" + indent(")", depth + 1)
            end

            code += "\n" + indent("}", depth)
          else
            # Checkbox without label
            code = indent("Checkbox(", depth)
            code += "\n" + indent("checked = #{checked},", depth + 1)

            # onCheckedChange handler
            binding_variable = nil
            state_attr_val = json_data['isOn'] || json_data['checked']
            if state_attr_val.is_a?(String) && state_attr_val.match(/@\{([^}]+)\}/)
              binding_variable = $1
            elsif json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
              binding_variable = $1
            end

            view_id = json_data['id'] || 'checkbox'
            if json_data['onValueChange']
              # onValueChange (camelCase) -> binding format only (@{functionName})
              if Helpers::ModifierBuilder.is_binding?(json_data['onValueChange'])
                handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(json_data['onValueChange'], view_id, 'it')
                if binding_variable
                  code += "\n" + indent("onCheckedChange = { newValue -> viewModel.updateData(mapOf(\"#{binding_variable}\" to newValue)); #{handler_call} },", depth + 1)
                else
                  code += "\n" + indent("onCheckedChange = { #{handler_call} },", depth + 1)
                end
              else
                code += "\n" + indent("onCheckedChange = { // ERROR: #{json_data['onValueChange']} - camelCase events require binding format @{functionName} },", depth + 1)
              end
            elsif binding_variable
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

          # iconSize with no custom icon: there is no separate glyph to size, so
          # it sizes the Checkbox itself.
          modifiers << ".size(#{json_data['iconSize'].to_i}.dp)" if json_data['iconSize']

            code += Helpers::ModifierBuilder.format(modifiers, depth) if modifiers.any?

            # Checkbox colors
            checked_color_value = json_data['checkColor'] || json_data['checkedColor'] || json_data['tintColor'] || json_data['onTintColor']
            if checked_color_value || json_data['uncheckedColor'] || json_data['iconColor']
              required_imports&.add(:checkbox_colors)
              colors_params = []

              if checked_color_value
                checked_color = Helpers::ResourceResolver.process_color(checked_color_value, required_imports)
                colors_params << "checkedColor = #{checked_color}"
              end

              if json_data['uncheckedColor']
                unchecked_color = Helpers::ResourceResolver.process_color(json_data['uncheckedColor'], required_imports)
                colors_params << "uncheckedColor = #{unchecked_color}"
              end

              # For a Material Checkbox the "icon" is the tick, so iconColor maps
              # to checkmarkColor rather than to the box.
              if json_data['iconColor']
                icon_color = Helpers::ResourceResolver.process_color(json_data['iconColor'], required_imports)
                colors_params << "checkmarkColor = #{icon_color}"
              end

              if colors_params.any?
                code += ",\n" + indent("colors = CheckboxDefaults.colors(", depth + 1)
                code += "\n" + colors_params.map { |param| indent(param, depth + 2) }.join(",\n")
                code += "\n" + indent(")", depth + 1)
              end
            end

            # Handle enabled attribute
            if json_data.key?('enabled')
              if json_data['enabled'].is_a?(String) && json_data['enabled'].start_with?('@{')
                inner_expr = json_data['enabled'].match(/@\{([^}]+)\}/)[1]
                code += ",\n" + indent("enabled = #{Helpers::BindingExpression.value_access(inner_expr, negatable: true)}", depth + 1)
              else
                code += ",\n" + indent("enabled = #{json_data['enabled']}", depth + 1)
              end
            end

            code += "\n" + indent(")", depth)
          end

          code
        end

        private

        # Generate checkbox with custom icon/selectedIcon
        def self.generate_icon_checkbox(json_data, depth, required_imports, parent_type, checked)
          required_imports&.add(:icon_toggle_button)
          required_imports&.add(:icon)

          # Each state falls back to the OTHER supplied asset, not to a Material
          # icon name: this branch only runs when the layout named at least one
          # drawable, and `R.drawable.check_box` does not exist in the app.
          icon = json_data['icon'] || json_data['selectedIcon']
          selected_icon = json_data['selectedIcon'] || json_data['icon']

          # Resolve icon names to drawable resources
          required_imports&.add(:painter_resource)
          required_imports&.add(:r_class)
          icon_res = "R.drawable.#{Helpers::ResourceResolver.drawable_name(icon)}"
          selected_icon_res = "R.drawable.#{Helpers::ResourceResolver.drawable_name(selected_icon)}"

          code = indent("IconToggleButton(", depth)
          code += "\n" + indent("checked = #{checked},", depth + 1)

          # onCheckedChange handler
          binding_variable = nil
          state_attr_val = json_data['isOn'] || json_data['checked']
          if state_attr_val.is_a?(String) && state_attr_val.match(/@\{([^}]+)\}/)
            binding_variable = $1
          elsif json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
            binding_variable = $1
          end

          view_id = json_data['id'] || 'checkbox'
          if json_data['onValueChange']
            # onValueChange (camelCase) -> binding format only (@{functionName})
            if Helpers::ModifierBuilder.is_binding?(json_data['onValueChange'])
              handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(json_data['onValueChange'], view_id, 'it')
              if binding_variable
                code += "\n" + indent("onCheckedChange = { newValue -> viewModel.updateData(mapOf(\"#{binding_variable}\" to newValue)); #{handler_call} },", depth + 1)
              else
                code += "\n" + indent("onCheckedChange = { #{handler_call} },", depth + 1)
              end
            else
              code += "\n" + indent("onCheckedChange = { /* ERROR: #{json_data['onValueChange']} - camelCase events require binding format @{functionName} */ },", depth + 1)
            end
          elsif binding_variable
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

          code += Helpers::ModifierBuilder.format(modifiers, depth) if modifiers.any?

          code += "\n" + indent(") {", depth)

          # Icon content - switch based on checked state
          code += "\n" + indent("Icon(", depth + 1)
          code += "\n" + indent("painter = painterResource(id = if (#{checked}) #{selected_icon_res} else #{icon_res}),", depth + 2)
          code += "\n" + indent("contentDescription = null", depth + 2)

          # Icon size. IconToggleButton keeps its own 48dp touch target, so this
          # sizes the glyph inside it rather than the control.
          if json_data['iconSize']
            code += ",\n" + indent("modifier = Modifier.size(#{json_data['iconSize'].to_i}.dp)", depth + 2)
          end

          # Icon tint. `iconColor` is the declared attribute for this; fontColor
          # stays as the fallback it has always been. When neither is
          # declared, Color.Unspecified keeps the asset's OWN colors — the
          # dynamic component always passes `tint ?: Color.Unspecified`,
          # while omitting the argument here left Icon()'s default
          # LocalContentColor tint painting custom icons black (parity
          # family kjui-codegen-selection-icon-placement).
          tint_value = json_data['iconColor'] || json_data['fontColor']
          if tint_value
            icon_color = Helpers::ResourceResolver.process_color(tint_value, required_imports)
            code += ",\n" + indent("tint = #{icon_color}", depth + 2)
          else
            code += ",\n" + indent("tint = Color.Unspecified", depth + 2)
          end

          code += "\n" + indent(")", depth + 1)
          code += "\n" + indent("}", depth)

          code
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
