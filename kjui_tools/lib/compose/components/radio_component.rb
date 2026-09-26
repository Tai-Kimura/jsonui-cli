# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/binding_expression'
require_relative '../helpers/static_seed'
require_relative '../helpers/bound_value'
require_relative '../helpers/font_spec_helper'
require_relative '../helpers/resource_resolver'
require_relative '../../core/string_literals'
require_relative '../../core/layout_path'

module KjuiTools
  module Compose
    module Components
      class RadioComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # Handle Radio group with items FIRST (higher priority)
          if json_data['items']
            return generate_radio_group_with_items(json_data, depth, required_imports, parent_type)
          end
          
          # Handle individual Radio item (not a group). `label` is the
          # cross-platform spelling of the row text (web's ToggleConverter and
          # sjui read it too).
          if json_data['group'] || json_data['text'] || json_data['label']
            return generate_radio_item(json_data, depth, required_imports, parent_type)
          end
          # Radio uses 'bind' for selected value
          selected = if json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
            variable = $1
            "data.#{variable}"
          else
            '""'
          end
          
          code = indent("Column(", depth)
          # `enabled` is the Radio's own controls' parameter — each RadioButton,
          # and the row that selects it: a disabled Radio neither selects nor calls
          # the declared onClick (operation_click_call).
          enabled = Helpers::ModifierBuilder.enabled_expression(json_data)
          row_enabled = enabled ? "(enabled = #{enabled})" : ''

          # Build modifiers
          modifiers = stage_modifiers(json_data, parent_type, required_imports)
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          code += Helpers::ModifierBuilder.format(modifiers, depth) if modifiers.any?
          code += "\n" + indent(") {", depth)
          
          # Radio options
          if json_data['options']
            if json_data['options'].is_a?(Array)
              json_data['options'].each do |option|
                option_value = option.is_a?(Hash) ? option['value'] : option
                option_label = option.is_a?(Hash) ? option['label'] : option
                value_literal = JsonUIShared::StringLiterals.kotlin(option_value)
                
                code += "\n" + indent("Row(", depth + 1)
                code += "\n" + indent("verticalAlignment = Alignment.CenterVertically,", depth + 2)
                code += "\n" + indent("modifier = Modifier", depth + 2)
                code += "\n" + indent("    .fillMaxWidth()", depth + 2)
                code += "\n" + indent("    .clickable#{row_enabled} {", depth + 2)
                
                view_id = json_data['id'] || 'radio'
                if json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
                  variable = $1
                  if json_data['onValueChange'] && Helpers::ModifierBuilder.is_binding?(json_data['onValueChange'])
                    handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(json_data['onValueChange'], view_id, value_literal)
                    code += "\n" + indent("        viewModel.updateData(mapOf(\"#{variable}\" to #{value_literal}))", depth + 2)
                    code += "\n" + indent("        #{handler_call}", depth + 2)
                  else
                    code += "\n" + indent("        viewModel.updateData(mapOf(\"#{variable}\" to #{value_literal}))", depth + 2)
                  end
                elsif json_data['onValueChange']
                  # onValueChange (camelCase) -> binding format only (@{functionName})
                  if Helpers::ModifierBuilder.is_binding?(json_data['onValueChange'])
                    handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(json_data['onValueChange'], view_id, value_literal)
                    code += "\n" + indent("        #{handler_call}", depth + 2)
                  else
                    code += "\n" + indent("        // ERROR: #{json_data['onValueChange']} - camelCase events require binding format @{functionName}", depth + 2)
                  end
                end
                
                # The declared onClick, from the selection (operation_click_call).
                if (click = Helpers::ModifierBuilder.operation_click_call(json_data))
                  code += "\n" + indent("        #{click}", depth + 2)
                end
                code += "\n" + indent("    }", depth + 2)
                code += "\n" + indent(") {", depth + 1)
                
                # RadioButton
                code += "\n" + indent("RadioButton(", depth + 2)
                code += "\n" + indent("selected = (#{selected} == #{value_literal}),", depth + 3)
                code += "\n" + indent("enabled = #{enabled},", depth + 3) if enabled
                code += "\n" + indent("onClick = {", depth + 3)
                
                if json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
                  variable = $1
                  if json_data['onValueChange'] && Helpers::ModifierBuilder.is_binding?(json_data['onValueChange'])
                    handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(json_data['onValueChange'], view_id, value_literal)
                    code += "\n" + indent("viewModel.updateData(mapOf(\"#{variable}\" to #{value_literal}))", depth + 4)
                    code += "\n" + indent("#{handler_call}", depth + 4)
                  else
                    code += "\n" + indent("viewModel.updateData(mapOf(\"#{variable}\" to #{value_literal}))", depth + 4)
                  end
                elsif json_data['onValueChange']
                  # onValueChange (camelCase) -> binding format only (@{functionName})
                  if Helpers::ModifierBuilder.is_binding?(json_data['onValueChange'])
                    handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(json_data['onValueChange'], view_id, value_literal)
                    code += "\n" + indent("#{handler_call}", depth + 4)
                  else
                    code += "\n" + indent("// ERROR: #{json_data['onValueChange']} - camelCase events require binding format @{functionName}", depth + 4)
                  end
                end

                if (click = Helpers::ModifierBuilder.operation_click_call(json_data))
                  code += "\n" + indent(click, depth + 4)
                end
                code += "\n" + indent("}", depth + 3)
                
                # RadioButton colors
                if json_data['selectedColor'] || json_data['checkedColor'] || json_data['unselectedColor'] || json_data['uncheckedColor'] || json_data['iconColor']
                  required_imports&.add(:radio_colors)
                  colors_params = []
                  
                  selected = json_data['selectedColor'] || json_data['checkedColor']
                  if selected
                    selectedcolor_resolved = Helpers::ResourceResolver.process_color(selected, required_imports)
                    colors_params << "selectedColor = #{selectedcolor_resolved}"
                  end
                  
                  # `uncheckedColor` is the cross-platform spelling of the
                  # same colour; the Compose-native name wins when both exist.
                  # iconColor tints the (unselected) glyph as the last resort.
                  unselected = json_data['unselectedColor'] || json_data['uncheckedColor'] || json_data['iconColor']
                  if unselected
                    unselectedcolor_resolved = Helpers::ResourceResolver.process_color(unselected, required_imports)
                    colors_params << "unselectedColor = #{unselectedcolor_resolved}"
                  end
                  
                  if colors_params.any?
                    code += ",\n" + indent("colors = RadioButtonDefaults.colors(", depth + 3)
                    code += "\n" + colors_params.map { |param| indent(param, depth + 4) }.join(",\n")
                    code += "\n" + indent(")", depth + 3)
                  end
                end
                
                code += "\n" + indent(")", depth + 2)
                
                # Label text
                code += "\n" + indent("Spacer(modifier = Modifier.width(8.dp))", depth + 2)
                code += "\n" + indent("Text(#{JsonUIShared::StringLiterals.kotlin(option_label)})", depth + 2)
                
                code += "\n" + indent("}", depth + 1)
              end
            elsif json_data['options'].is_a?(String) && json_data['options'].match(/@\{([^}]+)\}/)
              # Dynamic options from data binding
              options_var = $1
              code += "\n" + indent("data.#{options_var}.forEach { option ->", depth + 1)
              code += "\n" + indent("Row(", depth + 2)
              code += "\n" + indent("verticalAlignment = Alignment.CenterVertically,", depth + 3)
              code += "\n" + indent("modifier = Modifier.fillMaxWidth().clickable#{row_enabled} {", depth + 3)
              
              if json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
                variable = $1
                code += "\n" + indent("viewModel.updateData(mapOf(\"#{variable}\" to option))", depth + 4)
              end
              
              if (click = Helpers::ModifierBuilder.operation_click_call(json_data))
                code += "\n" + indent(click, depth + 4)
              end
              code += "\n" + indent("}", depth + 3)
              code += "\n" + indent(") {", depth + 2)
              code += "\n" + indent("RadioButton(", depth + 3)
              code += "\n" + indent("selected = (#{selected} == option),", depth + 4)
              code += "\n" + indent("enabled = #{enabled},", depth + 4) if enabled
              code += "\n" + indent("onClick = {", depth + 4)
              
              if json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
                variable = $1
                code += "\n" + indent("viewModel.updateData(mapOf(\"#{variable}\" to option))", depth + 5)
              end
              
              if (click = Helpers::ModifierBuilder.operation_click_call(json_data))
                code += "\n" + indent(click, depth + 5)
              end
              code += "\n" + indent("}", depth + 4)
              code += "\n" + indent(")", depth + 3)
              code += "\n" + indent("Spacer(modifier = Modifier.width(8.dp))", depth + 3)
              code += "\n" + indent("Text(option)", depth + 3)
              code += "\n" + indent("}", depth + 2)
              code += "\n" + indent("}", depth + 1)
            end
          end
          
          code += "\n" + indent("}", depth)
          code
        end
        
        private
        
        # The node's common stages, in the View order: testTag → (blocker) →
        # margins → size → offset → alpha → shadow → background → click →
        # padding — the same list for the options Column, a Radio item's Row
        # and an items Column. The item Row and the items Column carried the
        # margins alone and the options Column no size, shadow, background or
        # click: all declared on `common` and dropped
        # (kjui-dynamic-components-that-skip-the-common-modifiers). The blocker
        # stays ahead of the margins where the options Column always had it,
        # so the click stage is the click and the disabled semantics, not
        # build_clickable's blocker again. The RadioButton's own selection is
        # its onClick, as before; a declared onClick is the node's.
        def self.stage_modifiers(json_data, parent_type, required_imports)
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          # userInteractionEnabled / touchDisabledState stop this node and
          # what is in it (ModifierBuilder.build_interaction_blocker).
          modifiers.concat(Helpers::ModifierBuilder.build_interaction_blocker(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_shadow(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          # The node's own long press, pan and pinch, at the click slot and
          # gated like it (gesture_gate: userInteractionEnabled and enabled) —
          # declared on `common` and dropped here
          # (kjui-dynamic-components-that-skip-the-common-modifiers, B6).
          modifiers.concat(Helpers::ModifierBuilder.build_gestures(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_disabled_semantics(
            json_data, Helpers::ModifierBuilder.enabled_expression(json_data), required_imports
          ))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers
        end

        def self.generate_radio_item(json_data, depth, required_imports, parent_type)
          group = json_data['group'] || 'default'
          # The item's value when no id names it: its position in the layout
          # (shared/core/layout_path.rb — `radio_0_2_1`), the same on every
          # build and unique within the view. It was `"radio_#{rand(1000)}"`:
          # every build emitted different Kotlin, and two items could draw the
          # same number (kjui-radio-default-id-is-random). A node emitted on
          # its own, with no tree around it, is its own root.
          id = json_data['id'] || "radio_#{json_data[JsonUIShared::LayoutPath::KEY] || '0'}"
          id_literal = JsonUIShared::StringLiterals.kotlin(id)
          # `text`/`label` are `["string", "binding"]`. They used to be
          # interpolated straight into the Kotlin literal, so a bound label put
          # the characters `@{...}` on screen (plan 49 lane C: Radio.text,
          # Radio.label). `text_expr` is the emit; `text` stays the raw value so
          # the "is there a label at all" tests below are unchanged.
          text = json_data['text'] || json_data['label'] || ''
          text_expr = Helpers::BoundValue.text(text)
          
          # Get the selected state from binding
          selected_var = "selectedRadiogroup"  # Default variable name
          if group.downcase != 'default'
            # Use group name as part of the variable
            selected_var = "selected#{group.capitalize}"
          end
          # `checked` is declared `["boolean", "binding"]` — "initial checked
          # state" — and no converter read the spelling at all (plan 49 lane C:
          # Radio.checked, C0 unread + C1 dropped). When it IS declared it is
          # the authority on this item's selected state; the group variable is
          # the fallback for the (usual) case where it is not.
          selected_expr = radio_selected_expr(json_data, selected_var, id)
          on_select = "viewModel.updateData(mapOf(\"#{selected_var}\" to #{id_literal}))"

          # A group the layout does not bind — no `selectedValue` on the item —
          # keeps its selection in the view's own map, seeded by the checked
          # item while nothing is chosen (ticket
          # static-valued-controls-do-not-change-on-a-users-tap: the generated
          # updateData had no branch for `selected<Group>`, so a tap did
          # nothing). The map spans every item of the group, whichever section
          # an item lands in (ComposeBuilder#provide_radio_groups).
          local_group = !json_data.key?('selectedValue')
          if local_group
            required_imports&.add(:radio_group_selections)
            group_literal = JsonUIShared::StringLiterals.kotlin(group)
            token = Helpers::BoundValue.text(json_data['value'] || id)
            selected_expr = radio_selected_expr(json_data, selected_var, id,
                                                chosen: "radioGroups[#{group_literal}]")
            on_select = "radioGroups[#{group_literal}] = #{token}"
          end

          # The item's own operation: select it (on_select — the group's Data
          # property, or the view's own map for a group the layout does not
          # bind), then the declared onClick (ModifierBuilder.with_operation_click)
          # — RadioButton, Checkbox or IconButton alike.
          # `enabled` is the item's own control's parameter: a disabled item
          # neither selects nor calls the declared onClick.
          enabled = Helpers::ModifierBuilder.enabled_expression(json_data)
          select_lambda = Helpers::ModifierBuilder.with_operation_click("{ #{on_select} }", json_data)

          code = indent("Row(", depth)
          code += "\n" + indent("    verticalAlignment = Alignment.CenterVertically,", depth)
          
          # Build modifiers — every common stage, not the margins alone
          # (stage_modifiers). A multi-line modifier (the blocker's
          # pointerInput) keeps its own indentation under the chain.
          modifiers = stage_modifiers(json_data, parent_type, required_imports)
          
          if modifiers.any?
            code += "\n" + indent("    modifier = Modifier", depth)
            modifiers.each do |mod|
              code += "\n" + indent(indent(mod, 2), depth)
            end
          end
          
          code += "\n" + indent(") {", depth)
          code += "\n" + indent("    val radioGroups = LocalRadioGroupSelections.current", depth) if local_group

          # Handle custom icons or default components
          # If icon is "circle" or selectedIcon is "checkmark.circle.fill", use default RadioButton
          if (json_data['icon'] == 'circle' || !json_data['icon']) && 
             (json_data['selectedIcon'] == 'checkmark.circle.fill' || !json_data['selectedIcon'])
            # Use default RadioButton for standard radio appearance
            code += "\n" + indent("    RadioButton(", depth)
            code += "\n" + indent("        selected = #{selected_expr},", depth)
            code += "\n" + indent("        onClick = #{select_lambda}", depth)
            code += ",\n" + indent("        enabled = #{enabled}", depth) if enabled
            icon_appearance_args(json_data, required_imports, :radio).each do |arg|
              code += ",\n" + indent("        #{arg}", depth)
            end
            code += "\n" + indent("    )", depth)
          elsif json_data['icon'] == 'square' && 
                (json_data['selectedIcon'] == 'checkmark.square.fill' || !json_data['selectedIcon'])
            # Use default Checkbox for square appearance
            required_imports&.add(:checkbox)
            code += "\n" + indent("    Checkbox(", depth)
            code += "\n" + indent("        checked = #{selected_expr},", depth)
            code += "\n" + indent("        onCheckedChange = #{select_lambda}", depth)
            code += ",\n" + indent("        enabled = #{enabled}", depth) if enabled
            icon_appearance_args(json_data, required_imports, :checkbox).each do |arg|
              code += ",\n" + indent("        #{arg}", depth)
            end
            code += "\n" + indent("    )", depth)
          elsif json_data['icon'] || json_data['selectedIcon']
            # Use IconButton with custom icons only for non-standard icons
            required_imports&.add(:icon_button)
            required_imports&.add(:icons)
            
            icon = map_icon_name(json_data['icon'] || 'star')
            selected_icon = map_icon_name(json_data['selectedIcon'] || 'star.fill')
            
            code += "\n" + indent("    val isSelected = #{selected_expr}", depth)
            code += "\n" + indent("    IconButton(", depth)
            code += "\n" + indent("        onClick = #{select_lambda}", depth)
            code += ",\n" + indent("        enabled = #{enabled}", depth) if enabled
            code += "\n" + indent("    ) {", depth)
            code += "\n" + indent("        Icon(", depth)
            code += "\n" + indent("            imageVector = if (isSelected) #{selected_icon} else #{icon},", depth)
            code += "\n" + indent("            contentDescription = #{text_expr},", depth)
            
            if json_data['iconSize']
              code += "\n" + indent("            modifier = Modifier.size(#{json_data['iconSize'].to_i}.dp),", depth)
            end

            if json_data['iconColor']
              # One tint for the whole glyph, so both states share it.
              icon_color = Helpers::ResourceResolver.process_color(json_data['iconColor'], required_imports)
              code += "\n" + indent("            tint = #{icon_color}", depth)
            elsif json_data['selectedColor'] || json_data['tintColor']
              color = json_data['selectedColor'] || json_data['tintColor']
              selected_color = Helpers::ResourceResolver.process_color(color, required_imports)
              code += "\n" + indent("            tint = if (isSelected) #{selected_color} else Color.Gray", depth)
            else
              code += "\n" + indent("            tint = if (isSelected) MaterialTheme.colorScheme.primary else Color.Gray", depth)
            end
            
            code += "\n" + indent("        )", depth)
            code += "\n" + indent("    }", depth)
          else
            # Default RadioButton
            code += "\n" + indent("    RadioButton(", depth)
            code += "\n" + indent("        selected = #{selected_expr},", depth)
            code += "\n" + indent("        onClick = #{select_lambda}", depth)
            code += ",\n" + indent("        enabled = #{enabled}", depth) if enabled
            icon_appearance_args(json_data, required_imports, :radio).each do |arg|
              code += ",\n" + indent("        #{arg}", depth)
            end
            code += "\n" + indent("    )", depth)
          end
          
          # Add text label
          if text && !text.empty?
            # `spacing` is the declared icon/label gap and was hard-coded at
            # 8.dp, so no value of it could reach the output (plan 49 lane C:
            # Radio.spacing, C0 unread + C1 dropped).
            code += "\n" + indent("    Spacer(modifier = Modifier.width(#{radio_spacing_dp(json_data)}))", depth)
            # Add text with color
            if json_data['fontColor'] || json_data['textColor']
              text_color = json_data['fontColor'] || json_data['textColor']
              color_resolved = Helpers::ResourceResolver.process_color(text_color, required_imports)
              code += "\n" + indent("    Text(#{text_expr}, color = #{color_resolved}#{label_font_args(json_data, required_imports)})", depth)
            else
              # Default to black color
              code += "\n" + indent("    Text(#{text_expr}, color = Color.Black#{label_font_args(json_data, required_imports)})", depth)
            end
          end
          
          code += "\n" + indent("}", depth)
          code
        end
        
        def self.generate_radio_group_with_items(json_data, depth, required_imports, parent_type)
          # `items` is declared ["array", "binding"]: an array is the options,
          # written out one by one; a binding is a list the data holds, drawn
          # with forEach — what DynamicRadioComponent.itemsOf does with it.
          # Until 1.8.121 a bound `items` raised NoMethodError (`each` on a
          # String) and took the build down (ticket
          # kjui-codegen-table-crashes-on-an-items-array).
          items = json_data['items']
          bound_items = if items.is_a?(String) && items.match?(/@\{[^}]+\}/)
                          Helpers::BindingExpression.value_access(items[/@\{([^}]+)\}/, 1])
                        end
          # [the option as Kotlin, its text]
          options = if bound_items
                      [['item', 'item.toString()']]
                    else
                      Array(items).map { |item| [JsonUIShared::StringLiterals.kotlin(item)] * 2 }
                    end
          selected_value = json_data['selectedValue']
          
          # Add required import for clickable
          required_imports&.add(:clickable)
          
          # Extract binding variable. A STATIC `selectedValue` used to fall
          # through to the empty string, so no value of it could reach the
          # output — web settled this as `selectedValue === (value || id)`
          # (plan 44 Phase 0) and reads both forms (plan 49 lane C, from D/G).
          selected_var = if selected_value && selected_value.match(/@\{([^}]+)\}/)
            "data.#{$1}"
          elsif selected_value
            Helpers::BoundValue.text(selected_value)
          else
            '""'
          end

          # A static selection (or none) is the seed of the group's own state
          # (Helpers::StaticSeed); a bound one is the view model's.
          unless selected_var.start_with?('data.')
            return Helpers::StaticSeed.wrap(selected_var, depth, required_imports) do |d, state|
              radio_group_with_items_body(json_data, d, required_imports, parent_type, state, state,
                                          options: options, bound_items: bound_items)
            end
          end
          radio_group_with_items_body(json_data, depth, required_imports, parent_type, selected_var, nil,
                                      options: options, bound_items: bound_items)
        end

        # The group, reading `selected_var`; a tap writes `seeded` (the state a
        # static selection seeded) or the bound value. `options` / `bound_items`
        # are the items as the caller read them — an array written out one by
        # one, or a bound list drawn with forEach. The body was extracted from
        # the caller (static seeding) while the caller gained those two
        # (the array / binding forms); the two merged without a conflict and
        # every Radio with `items` raised NameError on `options`. `parent_type`
        # is for the common stages (stage_modifiers).
        def self.radio_group_with_items_body(json_data, depth, required_imports, parent_type, selected_var, seeded,
                                             options:, bound_items:)
          selected_value = json_data['selectedValue']
          # `enabled` is the Radio's own controls' parameter — each RadioButton,
          # and the row that selects it: a disabled Radio neither selects nor calls
          # the declared onClick (operation_click_call).
          enabled = Helpers::ModifierBuilder.enabled_expression(json_data)
          row_enabled = enabled ? "(enabled = #{enabled})" : ''
          code = indent("Column(", depth)
          
          # Build modifiers — every common stage, not the margins alone
          # (stage_modifiers). A multi-line modifier (the blocker's
          # pointerInput) keeps its own indentation under the chain.
          modifiers = stage_modifiers(json_data, parent_type, required_imports)
          
          if modifiers.any?
            code += "\n" + indent("    modifier = Modifier", depth)
            modifiers.each do |mod|
              code += "\n" + indent(indent(mod, 2), depth)
            end
          end
          
          code += "\n" + indent(") {", depth)
          
          # Add label if present
          if json_data['text']
            if json_data['fontColor'] || json_data['textColor']
              text_color = json_data['fontColor'] || json_data['textColor']
              color_resolved = Helpers::ResourceResolver.process_color(text_color, required_imports)
              code += "\n" + indent("    Text(#{JsonUIShared::StringLiterals.kotlin(json_data['text'])}, color = #{color_resolved})", depth)
            else
              # Default to black color
              code += "\n" + indent("    Text(#{JsonUIShared::StringLiterals.kotlin(json_data['text'])}, color = Color.Black)", depth)
            end
            code += "\n" + indent("    Spacer(modifier = Modifier.height(8.dp))", depth)
          end
          
          # Generate radio items
          rows_from = code.length
          options.each do |item_literal, item_text|
            code += "\n" + indent("    Row(", depth)
            code += "\n" + indent("        verticalAlignment = Alignment.CenterVertically,", depth)
            code += "\n" + indent("        modifier = Modifier", depth)
            code += "\n" + indent("            .fillMaxWidth()", depth)
            code += "\n" + indent("            .clickable#{row_enabled} {", depth)
            
            if seeded
              code += "\n" + indent("                #{seeded} = #{item_literal}", depth)
            elsif selected_value && selected_value.match(/@\{([^}]+)\}/)
              variable = $1
              code += "\n" + indent("                viewModel.updateData(mapOf(\"#{variable}\" to #{item_literal}))", depth)
            end
            
            if (click = Helpers::ModifierBuilder.operation_click_call(json_data))
              code += "\n" + indent("                #{click}", depth)
            end
            code += "\n" + indent("            }", depth)
            code += "\n" + indent("    ) {", depth)
            code += "\n" + indent("        RadioButton(", depth)
            code += "\n" + indent("            selected = #{selected_var} == #{item_literal},", depth)
            code += "\n" + indent("            enabled = #{enabled},", depth) if enabled
            code += "\n" + indent("            onClick = {", depth)
            
            if seeded
              code += "\n" + indent("                #{seeded} = #{item_literal}", depth)
            elsif selected_value && selected_value.match(/@\{([^}]+)\}/)
              variable = $1
              code += "\n" + indent("                viewModel.updateData(mapOf(\"#{variable}\" to #{item_literal}))", depth)
            end
            
            if (click = Helpers::ModifierBuilder.operation_click_call(json_data))
              code += "\n" + indent("                #{click}", depth)
            end
            code += "\n" + indent("            }", depth)
            code += "\n" + indent("        )", depth)
            code += "\n" + indent("        Spacer(modifier = Modifier.width(#{radio_spacing_dp(json_data)}))", depth)
            # The option's label: fontColor, and fontSize / font as the single
            # radio's label reads them (label_font_args) — the options drew
            # the colour only.
            if json_data['fontColor'] || json_data['textColor']
              text_color = json_data['fontColor'] || json_data['textColor']
              color_resolved = Helpers::ResourceResolver.process_color(text_color, required_imports)
              code += "\n" + indent("        Text(#{item_text}, color = #{color_resolved}#{label_font_args(json_data, required_imports)})", depth)
            else
              # Default to black color
              code += "\n" + indent("        Text(#{item_text}, color = Color.Black#{label_font_args(json_data, required_imports)})", depth)
            end
            code += "\n" + indent("    }", depth)
          end
          if bound_items
            # The one row, drawn for each item the data holds.
            rows = code.slice!(rows_from..)
            code += "\n" + indent("    #{bound_items}.forEach { item ->", depth) +
                    rows.gsub("\n", "\n    ") + "\n" + indent("    }", depth)
          end
          
          code += "\n" + indent("}", depth)
          code
        end
        
        # `iconSize` / `iconColor` as extra arguments for the default Material
        # controls.
        #
        # iconColor is a single tint for the whole glyph, so it applies to BOTH
        # states — unlike selectedColor / tintColor, which only set the selected
        # one. For a Checkbox the glyph is the tick, hence checkmarkColor.
        def self.icon_appearance_args(json_data, required_imports, control)
          args = []
          # iconSize sizes the GLYPH: Material draws its glyph at a fixed
          # 20dp, so a bare .size(N) just clips it (measured: the arc corner
          # of a 20dp circle inside an 8dp box). Scaling by N/20 inside the
          # N-dp box draws the glyph at the declared size.
          if json_data['iconSize']
            required_imports&.add(:scale)
            size = json_data['iconSize'].to_i
            args << format("modifier = Modifier.size(%d.dp).scale(%.2ff)", size, size / 20.0)
          end
          # Per-state colours: selectedColor/uncheckedColor (the
          # cross-platform pair) win over the single iconColor override.
          icon_color = json_data['iconColor'] &&
                       Helpers::ResourceResolver.process_color(json_data['iconColor'], required_imports)
          case control
          when :radio
            # `checkedColor` is the cross-platform spelling of selectedColor
            # and was honoured at the group level but not here, while its pair
            # `uncheckedColor` WAS honoured just below — an asymmetric alias
            # (plan 49 lane C: Radio.checkedColor).
            selected_decl = json_data['selectedColor'] || json_data['checkedColor']
            selected = selected_decl &&
                       Helpers::ResourceResolver.process_color(selected_decl, required_imports)
            unselected = (json_data['unselectedColor'] || json_data['uncheckedColor']) &&
                         Helpers::ResourceResolver.process_color(json_data['unselectedColor'] || json_data['uncheckedColor'], required_imports)
            selected ||= icon_color
            unselected ||= icon_color
            if selected || unselected
              required_imports&.add(:radio_colors)
              parts = []
              parts << "selectedColor = #{selected}" if selected
              parts << "unselectedColor = #{unselected}" if unselected
              args << "colors = RadioButtonDefaults.colors(#{parts.join(', ')})"
            end
          when :checkbox
            if icon_color
              required_imports&.add(:checkbox_colors)
              args << "colors = CheckboxDefaults.colors(checkmarkColor = #{icon_color})"
            end
          end
          args
        end

        def self.map_icon_name(icon_name)
          # Map iOS SF Symbols to Material Icons
          icon_map = {
            'circle' => 'Icons.Outlined.PanoramaFishEye',  # Using PanoramaFishEye as it's a hollow circle
            'checkmark.circle.fill' => 'Icons.Filled.CheckCircle',
            'star' => 'Icons.Outlined.Star',
            'star.fill' => 'Icons.Filled.Star',
            'heart' => 'Icons.Outlined.FavoriteBorder',
            'heart.fill' => 'Icons.Filled.Favorite',
            'square' => 'Icons.Outlined.CheckBoxOutlineBlank',
            'checkmark.square.fill' => 'Icons.Default.CheckBox'  # Use Default.CheckBox instead of Filled.CheckBox
          }
          
          icon_map[icon_name] || 'Icons.Outlined.Star'  # Default fallback to star
        end
        
        # Label font args mirroring the dynamic component: `font` is the
        # weight spelling (bold/semibold/medium), `fontSize` a declared sp
        # size. Both were dropped on the codegen label (33 cross-effect;
        # dynamic reads them since the parse-but-never-read wave).
        def self.label_font_args(json_data, required_imports)
          args = ''
          # The local three-way `case` both duplicated the shared weight
          # vocabulary (40: duplicated vocabulary drifts) and could not match a
          # `"@{...}"`, so a bound font emitted no weight at all.
          weight = json_data['font'] && Helpers::FontSpecHelper.weight_expression(json_data['font'])
          if weight
            required_imports&.add(:font_weight)
            args += ", fontWeight = #{weight}"
          end
          if json_data['fontSize']
            # `#{...}.sp` raw put `@{v}.sp` in code position.
            required_imports&.add(:text_unit) if Helpers::BoundValue.bound?(json_data['fontSize'])
            args += ", fontSize = #{Helpers::BoundValue.sp(json_data['fontSize'], null_expr: 'TextUnit.Unspecified')}"
          end
          args
        end

        # This item's selected state. A declared `checked` wins; otherwise the
        # group's selection variable decides, which is what every branch used
        # to hard-code.
        # `chosen` is where the group's choice is read: the Data property by
        # default, the view's own map for a group the layout does not bind
        # (nil there until something is chosen).
        def self.radio_selected_expr(json_data, selected_var, id, chosen: nil)
          # Precedence: `selectedValue` > group > `checked`.
          #
          # `value` is this item's identity — the token the selection is
          # compared against — and it defaulted to the view id because no
          # converter read the spelling. `selectedValue` is the group's current
          # selection, declared on the item; web is canonical and settled on
          # `checked = selectedValue === (value || id)` (plan 44 Phase 0), so a
          # STATIC selectedValue decides with no binding at all.
          #
          # `checked` is a SEED, not an override. The SSoT calls it the
          # "Initial checked state", and rjui reaches for it only when the
          # selection attributes came back empty (`state_attrs = checked_attr
          # if state_attrs.empty?`, radio_converter.rb:104, with :153 spelling
          # out "a single radio with no group selection still honours
          # `checked`"). This method used to let `checked` win outright, which
          # pinned `selected = true` on a radio that a group was driving — the
          # radio then never switched again. Plan 49 lane C, G's pushback:
          # three sources against one, and this was the one.
          #
          # The answer to the pinning was NOT to drop the seed when a group is
          # named. The declared precedence is `bound selectedValue > literal
          # selectedValue > checked` and carries no group term — `group` picks
          # WHICH key holds the selection, it is not a rival to the seed. The
          # unset-group guard is what stops the pinning, and it guards both
          # arms alike: the seed shows until the group has chosen, then steps
          # aside. Dropping it outright drew an unselected glyph on android
          # where ios and web drew the seed (Radio/checked__true_with_group);
          # this now matches the dynamic path (DynamicRadioComponent
          # #itemIsSelected, KotlinJsonUI f3bdd90) expression for expression.
          #
          # "Unset" is `.isEmpty()`, not `== null`: the group property is
          # generated as a non-null `String` defaulting to `""`
          # (data_model_updater_core.rb), so a null test would be a
          # compiler-warned always-false — and the gate wants zero warnings.
          # The dynamic path reads a map with no key, hence its `== null`.
          token = Helpers::BoundValue.text(json_data['value'] || id)
          selected_value = json_data['selectedValue']

          if selected_value
            return "#{Helpers::BoundValue.text(selected_value)} == #{token}" unless Helpers::ModifierBuilder.is_binding?(selected_value)

            return "data.#{Helpers::ModifierBuilder.extract_binding_property(selected_value)} == #{token}"
          end

          group_test = "#{chosen || "data.#{selected_var}"} == #{token}"
          return group_test unless json_data.key?('checked')

          seed = case Helpers::BoundValue.bool(json_data['checked'])
                 when :on then 'true'
                 when :off then 'false'
                 else Helpers::BoundValue.bool(json_data['checked'])
                 end
          # A seed that is statically off adds nothing to the group state.
          return group_test if seed == 'false'

          unset = chosen ? "#{chosen} == null" : "data.#{selected_var}.isEmpty()"
          return "#{group_test} || #{unset}" if seed == 'true'

          "#{group_test} || (#{seed} && #{unset})"
        end

        # The declared icon/label gap, `["number", "binding"]`, default 8.
        def self.radio_spacing_dp(json_data)
          Helpers::BoundValue.dp(json_data['spacing'] || 8)
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