# frozen_string_literal: true

require_relative '../helpers/bound_value'
require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'

module KjuiTools
  module Compose
    module Components
      class SelectBoxComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          required_imports&.add(:selectbox_component)
          
          # Check if this is a date picker
          is_date_picker = json_data['selectItemType'] == 'Date'
          
          # SelectBox uses 'selectedItem', 'selectedDate', or 'bind' for selected value
          # For date pickers, selectedDate takes priority
          selected = if is_date_picker && json_data['selectedDate'] && json_data['selectedDate'].match(/@\{([^}]+)\}/)
            variable = $1
            "data.#{variable}"
          elsif json_data['selectedItem'] && json_data['selectedItem'].match(/@\{([^}]+)\}/)
            variable = $1
            "data.#{variable}"
          elsif json_data['selectedValue'] && json_data['selectedValue'].match(/@\{([^}]+)\}/)
            # `selectedValue` is the cross-platform spelling of the same
            # two-way selection binding (web reads it; selectedItem wins).
            variable = $1
            "data.#{variable}"
          elsif json_data['selectedIndex'].is_a?(String) && json_data['selectedIndex'].match(/@\{([^}]+)\}/)
            index_var = $1
            items = json_data['items']
            if items.is_a?(String) && items.match(/@\{([^}]+)\}/)
              items_var = $1
              "data.#{items_var}.getOrElse(data.#{index_var}) { \"\" }"
            elsif items.is_a?(Array)
              items_literal = items.map { |i| "\"#{i}\"" }.join(", ")
              "listOf(#{items_literal}).getOrElse(data.#{index_var}) { \"\" }"
            else
              "\"\""
            end
          elsif json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
            variable = $1
            "data.#{variable}"
          elsif json_data['selectedIndex'].is_a?(Integer) && json_data['items'].is_a?(Array)
            # Static selectedIndex: display the addressed item, as dynamic
            # mode does. (An Integer here used to crash the converter —
            # `.match` on 1:Integer — leaving the template scaffold in place;
            # caught by the codegen parity host on SelectBox/selectedIndex.)
            item = json_data['items'][json_data['selectedIndex']]
            item.nil? ? '""' : "\"#{item}\""
          elsif json_data['selectedItem'] || json_data['selectedValue'] || json_data['selectedDate']
            # STATIC selections were dropped: every branch above tests for a
            # `@{...}`, so a plain `selectedValue: "Two"` fell through to the
            # empty string (plan 49 lane C, handed over from D). Same priority
            # as the bound branches.
            static_selected = json_data['selectedDate'] || json_data['selectedItem'] || json_data['selectedValue']
            Helpers::BoundValue.text(static_selected)
          else
            '""'
          end
          
          # Use DateSelectBox for date type
          if is_date_picker
            required_imports&.add(:date_selectbox_component)
            code = indent("DateSelectBox(", depth)
          else
            code = indent("SelectBox(", depth)
          end
          code += "\n" + indent("value = #{selected},", depth + 1)
          
          # Handle onValueChange callback
          # For date pickers, check selectedDate first
          binding_variable = nil
          is_index_binding = false
          if is_date_picker && json_data['selectedDate'] && json_data['selectedDate'].match(/@\{([^}]+)\}/)
            binding_variable = $1
          elsif json_data['selectedItem'] && json_data['selectedItem'].match(/@\{([^}]+)\}/)
            binding_variable = $1
          elsif json_data['selectedValue'] && json_data['selectedValue'].match(/@\{([^}]+)\}/)
            binding_variable = $1
          elsif json_data['selectedIndex'].is_a?(String) && json_data['selectedIndex'].match(/@\{([^}]+)\}/)
            binding_variable = $1
            is_index_binding = true
          elsif json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
            binding_variable = $1
          end

          view_id = json_data['id'] || 'selectbox'
          if json_data['onValueChange']
            # onValueChange (camelCase) -> binding format only (@{functionName})
            if Helpers::ModifierBuilder.is_binding?(json_data['onValueChange'])
              handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(json_data['onValueChange'], view_id, 'newValue')
              if binding_variable
                code += "\n" + indent("onValueChange = { newValue ->", depth + 1)
                if is_index_binding
                  # selectedIndex: convert String value back to Int index
                  items = json_data['items']
                  if items.is_a?(String) && items.match(/@\{([^}]+)\}/)
                    items_var = $1
                    code += "\n" + indent("val index = data.#{items_var}.indexOf(newValue)", depth + 2)
                  elsif items.is_a?(Array)
                    items_literal = items.map { |i| "\"#{i}\"" }.join(", ")
                    code += "\n" + indent("val index = listOf(#{items_literal}).indexOf(newValue)", depth + 2)
                  else
                    code += "\n" + indent("val index = 0", depth + 2)
                  end
                  code += "\n" + indent("viewModel.updateData(mapOf(\"#{binding_variable}\" to index))", depth + 2)
                else
                  code += "\n" + indent("viewModel.updateData(mapOf(\"#{binding_variable}\" to newValue))", depth + 2)
                end
                code += "\n" + indent("#{handler_call}", depth + 2)
                code += "\n" + indent("},", depth + 1)
              else
                code += "\n" + indent("onValueChange = { newValue -> #{handler_call} },", depth + 1)
              end
            else
              code += "\n" + indent("onValueChange = { // ERROR: #{json_data['onValueChange']} - camelCase events require binding format @{functionName} },", depth + 1)
            end
          elsif binding_variable
            code += "\n" + indent("onValueChange = { newValue ->", depth + 1)
            code += "\n" + indent("viewModel.updateData(mapOf(\"#{binding_variable}\" to newValue))", depth + 2)
            code += "\n" + indent("},", depth + 1)
          else
            code += "\n" + indent("onValueChange = { },", depth + 1)
          end
          
          # For date picker, add date-specific parameters
          if is_date_picker
            # Date picker mode (date, time, dateAndTime)
            if json_data['datePickerMode']
              code += "\n" + indent("datePickerMode = \"#{json_data['datePickerMode']}\",", depth + 1)
            end
            
            # Date picker style
            if json_data['datePickerStyle']
              code += "\n" + indent("datePickerStyle = \"#{json_data['datePickerStyle']}\",", depth + 1)
            end
            
            # Date format (or dateStringFormat)
            date_format = json_data['dateFormat'] || json_data['dateStringFormat']
            if date_format
              code += "\n" + indent("dateFormat = \"#{date_format}\",", depth + 1)
            end
            
            # Minute interval for time pickers
            if json_data['minuteInterval']
              code += "\n" + indent("minuteInterval = #{json_data['minuteInterval']},", depth + 1)
            end
            
            # Minimum date
            if json_data['minimumDate']
              # A bound date used to be interpolated into the string literal,
              # putting the characters `@{...}` into the picker bound (plan 49
              # lane C, handed over from D).
              code += "\n" + indent("minimumDate = #{Helpers::BoundValue.text(json_data['minimumDate'])},", depth + 1)
            end
            
            # Maximum date
            if json_data['maximumDate']
              code += "\n" + indent("maximumDate = #{Helpers::BoundValue.text(json_data['maximumDate'])},", depth + 1)
            end
          else
            # Options (use 'items' or 'options') - only for non-date SelectBox
            options_data = json_data['items'] || json_data['options']
            if options_data
            if options_data.is_a?(String) && options_data.match(/@\{([^}]+)\}/)
              # Dynamic options from data binding
              options_var = $1
              code += "\n" + indent("options = data.#{options_var},", depth + 1)
            elsif options_data.is_a?(Array)
              # Static options array
              options_list = options_data.map do |option|
                if option.is_a?(Hash)
                  "\"#{option['label'] || option['value']}\""
                else
                  "\"#{option}\""
                end
              end.join(", ")
              code += "\n" + indent("options = listOf(#{options_list}),", depth + 1)
            else
              code += "\n" + indent("options = emptyList(),", depth + 1)
            end
            else
              code += "\n" + indent("options = emptyList(),", depth + 1)
            end
          end
          
          # Add placeholder text — spec canonical `prompt` (primary) plus the
          # `hint` / `placeholder` aliases. Routed through process_text so a
          # snake_case key like "select_box_prompt" resolves to
          # stringResource(R.string.select_box_prompt) for proper localization.
          prompt_value = json_data['prompt'] || json_data['hint'] || json_data['placeholder']
          if prompt_value
            resolved = Helpers::ResourceResolver.process_text(prompt_value, required_imports)
            code += "\n" + indent("placeholder = #{resolved},", depth + 1)
          end
          
          # Add enabled state if specified
          if json_data['disabled']
            code += "\n" + indent("enabled = false,", depth + 1)
          elsif json_data['enabled'] == false
            code += "\n" + indent("enabled = false,", depth + 1)
          end
          
          # Add style parameters
          if json_data['background']
            bg_color = Helpers::ResourceResolver.process_color(json_data['background'], required_imports)
            code += "\n" + indent("backgroundColor = #{bg_color},", depth + 1)
          end
          
          if json_data['borderColor']
            border_color = Helpers::ResourceResolver.process_color(json_data['borderColor'], required_imports)
            code += "\n" + indent("borderColor = #{border_color},", depth + 1)
          end
          
          # `labelAttributes` styles the closed-state label; on this
          # component the collapsed text IS the label, so its keys win over
          # the component-level ones (same precedence the web converter uses).
          # The library surface today carries colour and size; `font` /
          # `textAlign` have no SelectBox parameter yet.
          label_attrs = json_data['labelAttributes'].is_a?(Hash) ? json_data['labelAttributes'] : {}
          label_font_color = label_attrs['fontColor'] || json_data['fontColor']
          if label_font_color
            text_color = Helpers::ResourceResolver.process_color(label_font_color, required_imports)
            code += "\n" + indent("textColor = #{text_color},", depth + 1)
          end
          
          if json_data['hintColor']
            hint_color = Helpers::ResourceResolver.process_color(json_data['hintColor'], required_imports)
            code += "\n" + indent("hintColor = #{hint_color},", depth + 1)
          end
          
          if json_data['cornerRadius']
            code += "\n" + indent("cornerRadius = #{json_data['cornerRadius']},", depth + 1)
          end

          # Font styling
          label_font_size = label_attrs['fontSize'] || json_data['fontSize']
          if label_font_size
            code += "\n" + indent("fontSize = #{label_font_size},", depth + 1)
          end

          if json_data['font']
            font_weight = case json_data['font'].to_s.downcase
            when 'bold'
              'FontWeight.Bold'
            when 'semibold'
              'FontWeight.SemiBold'
            when 'medium'
              'FontWeight.Medium'
            when 'light'
              'FontWeight.Light'
            when 'thin'
              'FontWeight.Thin'
            else
              'FontWeight.Normal'
            end
            code += "\n" + indent("fontWeight = #{font_weight},", depth + 1)
          end
          
          # Add cancel button background color if specified
          if json_data['cancelButtonBackgroundColor']
            cancel_bg = Helpers::ResourceResolver.process_color(json_data['cancelButtonBackgroundColor'], required_imports)
            code += "\n" + indent("cancelButtonBackgroundColor = #{cancel_bg},", depth + 1)
          end
          
          # Add cancel button text color if specified
          if json_data['cancelButtonTextColor']
            cancel_text = Helpers::ResourceResolver.process_color(json_data['cancelButtonTextColor'], required_imports)
            code += "\n" + indent("cancelButtonTextColor = #{cancel_text},", depth + 1)
          end
          
          # Build modifiers
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))

          # Ensure fillMaxWidth if width is not specified for date pickers
          if is_date_picker && !json_data['width']
            modifiers << ".fillMaxWidth()"
          end

          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, nil, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          # padding is passed as contentPadding parameter, not modifier
          modifiers.concat(Helpers::ModifierBuilder.build_alignment(json_data, required_imports, parent_type))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          if modifiers.any? && !modifiers.include?('SKIP_RENDER')
            code += Helpers::ModifierBuilder.format(modifiers, depth)
          end

          # contentPadding as component parameter (not modifier)
          paddings = json_data['paddings'] || json_data['padding']
          if paddings
            if paddings.is_a?(Array) && paddings.length == 4
              # JSON 4-element order is [top, right, bottom, left] (same as
              # ModifierBuilder padding): right -> end, left -> start.
              code += ",\n" + indent("contentPadding = PaddingValues(top = #{paddings[0]}.dp, end = #{paddings[1]}.dp, bottom = #{paddings[2]}.dp, start = #{paddings[3]}.dp)", depth + 1)
            elsif paddings.is_a?(Array) && paddings.length == 2
              code += ",\n" + indent("contentPadding = PaddingValues(horizontal = #{paddings[1]}.dp, vertical = #{paddings[0]}.dp)", depth + 1)
            elsif paddings.is_a?(Array) && paddings.length == 1
              code += ",\n" + indent("contentPadding = PaddingValues(#{paddings[0]}.dp)", depth + 1)
            elsif paddings.is_a?(Numeric)
              code += ",\n" + indent("contentPadding = PaddingValues(#{paddings}.dp)", depth + 1)
            end
          end

          code += "\n" + indent(")", depth)
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