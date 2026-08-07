# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/bound_value'
require_relative '../helpers/font_spec_helper'
require_relative '../helpers/resource_resolver'

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

          # Build modifiers
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          code += Helpers::ModifierBuilder.format(modifiers, depth) if modifiers.any?
          code += "\n" + indent(") {", depth)
          
          # Radio options
          if json_data['options']
            if json_data['options'].is_a?(Array)
              json_data['options'].each do |option|
                option_value = option.is_a?(Hash) ? option['value'] : option
                option_label = option.is_a?(Hash) ? option['label'] : option
                
                code += "\n" + indent("Row(", depth + 1)
                code += "\n" + indent("verticalAlignment = Alignment.CenterVertically,", depth + 2)
                code += "\n" + indent("modifier = Modifier", depth + 2)
                code += "\n" + indent("    .fillMaxWidth()", depth + 2)
                code += "\n" + indent("    .clickable {", depth + 2)
                
                view_id = json_data['id'] || 'radio'
                if json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
                  variable = $1
                  if json_data['onValueChange'] && Helpers::ModifierBuilder.is_binding?(json_data['onValueChange'])
                    handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(json_data['onValueChange'], view_id, "\"#{option_value}\"")
                    code += "\n" + indent("        viewModel.updateData(mapOf(\"#{variable}\" to \"#{option_value}\"))", depth + 2)
                    code += "\n" + indent("        #{handler_call}", depth + 2)
                  else
                    code += "\n" + indent("        viewModel.updateData(mapOf(\"#{variable}\" to \"#{option_value}\"))", depth + 2)
                  end
                elsif json_data['onValueChange']
                  # onValueChange (camelCase) -> binding format only (@{functionName})
                  if Helpers::ModifierBuilder.is_binding?(json_data['onValueChange'])
                    handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(json_data['onValueChange'], view_id, "\"#{option_value}\"")
                    code += "\n" + indent("        #{handler_call}", depth + 2)
                  else
                    code += "\n" + indent("        // ERROR: #{json_data['onValueChange']} - camelCase events require binding format @{functionName}", depth + 2)
                  end
                end
                
                code += "\n" + indent("    }", depth + 2)
                code += "\n" + indent(") {", depth + 1)
                
                # RadioButton
                code += "\n" + indent("RadioButton(", depth + 2)
                code += "\n" + indent("selected = (#{selected} == \"#{option_value}\"),", depth + 3)
                code += "\n" + indent("onClick = {", depth + 3)
                
                if json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
                  variable = $1
                  if json_data['onValueChange'] && Helpers::ModifierBuilder.is_binding?(json_data['onValueChange'])
                    handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(json_data['onValueChange'], view_id, "\"#{option_value}\"")
                    code += "\n" + indent("viewModel.updateData(mapOf(\"#{variable}\" to \"#{option_value}\"))", depth + 4)
                    code += "\n" + indent("#{handler_call}", depth + 4)
                  else
                    code += "\n" + indent("viewModel.updateData(mapOf(\"#{variable}\" to \"#{option_value}\"))", depth + 4)
                  end
                elsif json_data['onValueChange']
                  # onValueChange (camelCase) -> binding format only (@{functionName})
                  if Helpers::ModifierBuilder.is_binding?(json_data['onValueChange'])
                    handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(json_data['onValueChange'], view_id, "\"#{option_value}\"")
                    code += "\n" + indent("#{handler_call}", depth + 4)
                  else
                    code += "\n" + indent("// ERROR: #{json_data['onValueChange']} - camelCase events require binding format @{functionName}", depth + 4)
                  end
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
                code += "\n" + indent("Text(\"#{option_label}\")", depth + 2)
                
                code += "\n" + indent("}", depth + 1)
              end
            elsif json_data['options'].is_a?(String) && json_data['options'].match(/@\{([^}]+)\}/)
              # Dynamic options from data binding
              options_var = $1
              code += "\n" + indent("data.#{options_var}.forEach { option ->", depth + 1)
              code += "\n" + indent("Row(", depth + 2)
              code += "\n" + indent("verticalAlignment = Alignment.CenterVertically,", depth + 3)
              code += "\n" + indent("modifier = Modifier.fillMaxWidth().clickable {", depth + 3)
              
              if json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
                variable = $1
                code += "\n" + indent("viewModel.updateData(mapOf(\"#{variable}\" to option))", depth + 4)
              end
              
              code += "\n" + indent("}", depth + 3)
              code += "\n" + indent(") {", depth + 2)
              code += "\n" + indent("RadioButton(", depth + 3)
              code += "\n" + indent("selected = (#{selected} == option),", depth + 4)
              code += "\n" + indent("onClick = {", depth + 4)
              
              if json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
                variable = $1
                code += "\n" + indent("viewModel.updateData(mapOf(\"#{variable}\" to option))", depth + 5)
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
        
        def self.generate_radio_item(json_data, depth, required_imports, parent_type)
          group = json_data['group'] || 'default'
          id = json_data['id'] || "radio_#{rand(1000)}"
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
          
          code = indent("Row(", depth)
          code += "\n" + indent("    verticalAlignment = Alignment.CenterVertically,", depth)
          
          # Build modifiers
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          
          if modifiers.any?
            code += "\n" + indent("    modifier = Modifier", depth)
            modifiers.each do |mod|
              code += "\n" + indent("        #{mod}", depth)
            end
          end
          
          code += "\n" + indent(") {", depth)
          
          # Handle custom icons or default components
          # If icon is "circle" or selectedIcon is "checkmark.circle.fill", use default RadioButton
          if (json_data['icon'] == 'circle' || !json_data['icon']) && 
             (json_data['selectedIcon'] == 'checkmark.circle.fill' || !json_data['selectedIcon'])
            # Use default RadioButton for standard radio appearance
            code += "\n" + indent("    RadioButton(", depth)
            code += "\n" + indent("        selected = #{selected_expr},", depth)
            code += "\n" + indent("        onClick = { viewModel.updateData(mapOf(\"#{selected_var}\" to \"#{id}\")) }", depth)
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
            code += "\n" + indent("        onCheckedChange = { viewModel.updateData(mapOf(\"#{selected_var}\" to \"#{id}\")) }", depth)
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
            code += "\n" + indent("        onClick = { viewModel.updateData(mapOf(\"#{selected_var}\" to \"#{id}\")) }", depth)
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
            code += "\n" + indent("        onClick = { viewModel.updateData(mapOf(\"#{selected_var}\" to \"#{id}\")) }", depth)
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
          items = json_data['items']
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
          
          code = indent("Column(", depth)
          
          # Build modifiers
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          
          if modifiers.any?
            code += "\n" + indent("    modifier = Modifier", depth)
            modifiers.each do |mod|
              code += "\n" + indent("        #{mod}", depth)
            end
          end
          
          code += "\n" + indent(") {", depth)
          
          # Add label if present
          if json_data['text']
            if json_data['fontColor'] || json_data['textColor']
              text_color = json_data['fontColor'] || json_data['textColor']
              color_resolved = Helpers::ResourceResolver.process_color(text_color, required_imports)
              code += "\n" + indent("    Text(\"#{json_data['text']}\", color = #{color_resolved})", depth)
            else
              # Default to black color
              code += "\n" + indent("    Text(\"#{json_data['text']}\", color = Color.Black)", depth)
            end
            code += "\n" + indent("    Spacer(modifier = Modifier.height(8.dp))", depth)
          end
          
          # Generate radio items
          items.each do |item|
            code += "\n" + indent("    Row(", depth)
            code += "\n" + indent("        verticalAlignment = Alignment.CenterVertically,", depth)
            code += "\n" + indent("        modifier = Modifier", depth)
            code += "\n" + indent("            .fillMaxWidth()", depth)
            code += "\n" + indent("            .clickable {", depth)
            
            if selected_value && selected_value.match(/@\{([^}]+)\}/)
              variable = $1
              code += "\n" + indent("                viewModel.updateData(mapOf(\"#{variable}\" to \"#{item}\"))", depth)
            end
            
            code += "\n" + indent("            }", depth)
            code += "\n" + indent("    ) {", depth)
            code += "\n" + indent("        RadioButton(", depth)
            code += "\n" + indent("            selected = #{selected_var} == \"#{item}\",", depth)
            code += "\n" + indent("            onClick = {", depth)
            
            if selected_value && selected_value.match(/@\{([^}]+)\}/)
              variable = $1
              code += "\n" + indent("                viewModel.updateData(mapOf(\"#{variable}\" to \"#{item}\"))", depth)
            end
            
            code += "\n" + indent("            }", depth)
            code += "\n" + indent("        )", depth)
            code += "\n" + indent("        Spacer(modifier = Modifier.width(#{radio_spacing_dp(json_data)}))", depth)
            # Add text with black color
            if json_data['fontColor'] || json_data['textColor']
              text_color = json_data['fontColor'] || json_data['textColor']
              color_resolved = Helpers::ResourceResolver.process_color(text_color, required_imports)
              code += "\n" + indent("        Text(\"#{item}\", color = #{color_resolved})", depth)
            else
              # Default to black color
              code += "\n" + indent("        Text(\"#{item}\", color = Color.Black)", depth)
            end
            code += "\n" + indent("    }", depth)
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
        def self.radio_selected_expr(json_data, selected_var, id)
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

          group_test = "data.#{selected_var} == #{token}"
          return group_test unless json_data.key?('checked')

          seed = case Helpers::BoundValue.bool(json_data['checked'])
                 when :on then 'true'
                 when :off then 'false'
                 else Helpers::BoundValue.bool(json_data['checked'])
                 end
          # A seed that is statically off adds nothing to the group state.
          return group_test if seed == 'false'

          unset = "data.#{selected_var}.isEmpty()"
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