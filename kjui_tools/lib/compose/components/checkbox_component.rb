# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/bound_value'
require_relative '../helpers/font_spec_helper'
require_relative '../helpers/resource_resolver'
require_relative '../../core/normalization'

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
          # `value` is declared as a state alias of isOn/checked and was read
          # by nobody on Compose (plan 49 lane C, handed over from D). It sits
          # last so the more specific spellings keep winning.
          state_attr = json_data['isOn'] || json_data['checked'] || json_data['value']
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
          # 'src' is the common spelling of the unchecked icon (33).
          has_custom_icon = json_data['src'] || json_data['icon'] ||
                            Core::Normalization.attr_lookup(json_data, 'selectedIcon', 'onSrc')

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

            # iconSize on the labeled default checkbox sizes the box itself —
            # the dynamic labeled path does the same (it was only emitted on
            # the unlabeled branch; 32 parity re-measure).
            if json_data['iconSize']
              code += ",\n" + indent("modifier = Modifier.size(#{icon_size_dp(json_data['iconSize'])})", depth + 2)
            end

            # The colour and `enabled` arguments used to exist ONLY on the
            # unlabeled branch, and the fixture base carries `text`, so they
            # were unreachable for every measurement (plan 49 lane C: 4 of the
            # CheckBox entries; 32 closed `iconSize` the same way and left
            # these four behind — see the comment above).
            code += checkbox_colors_arg(json_data, required_imports, depth + 1)
            code += checkbox_enabled_arg(json_data, depth + 1)

            code += "\n" + indent(")", depth + 1)

            # Spacer with configurable spacing
            spacing = json_data['spacing'] || 8
            code += "\n" + indent("Spacer(modifier = Modifier.width(#{Helpers::BoundValue.dp(spacing)}))", depth + 1)

            # Label text with font attributes
            label_text = json_data['label'] || json_data['text']
            # A bound label used to be interpolated into the string literal, so
            # the characters `@{...}` reached the screen.
            label_expr = Helpers::BoundValue.text(label_text)
            text_params = ["text = #{label_expr}"]

            if json_data['fontSize']
              required_imports&.add(:text_unit) if Helpers::BoundValue.bound?(json_data['fontSize'])
              text_params << "fontSize = #{Helpers::BoundValue.sp(json_data['fontSize'], null_expr: 'TextUnit.Unspecified')}"
            end

            if json_data['fontColor']
              font_color = Helpers::ResourceResolver.process_color(json_data['fontColor'], required_imports)
              text_params << "color = #{font_color}"
            end

            if json_data['font']
              text_params << "fontWeight = #{Helpers::FontSpecHelper.weight_expression(json_data['font'])}"
            end

            if text_params.size == 1
              code += "\n" + indent("Text(#{label_expr})", depth + 1)
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
          modifiers << ".size(#{icon_size_dp(json_data['iconSize'])})" if json_data['iconSize']

            code += Helpers::ModifierBuilder.format(modifiers, depth) if modifiers.any?

            code += checkbox_colors_arg(json_data, required_imports, depth)
            code += checkbox_enabled_arg(json_data, depth)

            code += "\n" + indent(")", depth)
          end

          code
        end

        # `colors = CheckboxDefaults.colors(...)`. Extracted so the LABELLED
        # branch can emit it too — it never did, and the conformance fixture
        # base carries `text`, so `checkedColor` / `uncheckedColor` /
        # `iconColor` measured as unread on android (plan 49 lane C).
        def self.checkbox_colors_arg(json_data, required_imports, depth)
          checked_color_value = json_data['checkColor'] || json_data['checkedColor'] || json_data['tintColor'] || json_data['onTintColor']
          return '' unless checked_color_value || json_data['uncheckedColor'] || json_data['iconColor']

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

          return '' if colors_params.empty?

          code = ",\n" + indent("colors = CheckboxDefaults.colors(", depth + 1)
          code += "\n" + colors_params.map { |param| indent(param, depth + 2) }.join(",\n")
          code + "\n" + indent(")", depth + 1)
        end

        # `iconSize` is `["number", "binding"]`. The static path keeps its
        # `.to_i` truncation so existing output is unchanged; a binding takes
        # the canonical Dp emitter instead of truncating to 0.
        def self.icon_size_dp(value)
          return Helpers::BoundValue.dp(value) if Helpers::BoundValue.bound?(value)

          "#{value.to_i}.dp"
        end

        # `enabled = ...`. Same story as the colours: unlabelled branch only.
        def self.checkbox_enabled_arg(json_data, depth)
          return '' unless json_data.key?('enabled')

          state = Helpers::BoundValue.bool(json_data['enabled'])
          expr = case state
                 when :on then 'true'
                 when :off then 'false'
                 else state
                 end
          ",\n" + indent("enabled = #{expr}", depth + 1)
        end

        private

        # Generate checkbox with custom icon/selectedIcon
        def self.generate_icon_checkbox(json_data, depth, required_imports, parent_type, checked)
          required_imports&.add(:icon_toggle_button)
          required_imports&.add(:icon)

          # Each state falls back to the OTHER supplied asset, not to a Material
          # icon name: this branch only runs when the layout named at least one
          # drawable, and `R.drawable.check_box` does not exist in the app.
          # `onSrc` is the declared alias of selectedIcon (raw L0 layouts only;
          # the normalizer rewrites it for L1).
          selected_icon_decl = Core::Normalization.attr_lookup(json_data, 'selectedIcon', 'onSrc')
          icon = json_data['icon'] || json_data['src'] || selected_icon_decl
          selected_icon = selected_icon_decl || json_data['icon'] || json_data['src']

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

          # Build modifiers — declared width/height must reach the control
          # (the dynamic renderer's buildModifier applies size in the same
          # slot); dropping them left the button at its 48dp default, which
          # shifted the glyph and let the button's shape clip it.
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports))
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
