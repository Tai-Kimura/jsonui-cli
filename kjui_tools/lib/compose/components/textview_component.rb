# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'
require_relative '../helpers/font_spec_helper'

module KjuiTools
  module Compose
    module Components
      class TextViewComponent
        @counter ||= 0

        def self.next_resolved_var
          @counter += 1
          "resolved_textview#{@counter}"
        end

        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # TextView is multi-line text input (like TextArea)
          # Uses 'text' for value and supports both 'hint' and 'placeholder' (hint is primary)
          value = process_data_binding(json_data['text'] || '')
          placeholder_text = json_data['hint'] || json_data['placeholder'] || ''
          placeholder = placeholder_text.empty? ? nil : Helpers::ResourceResolver.process_text(placeholder_text, required_imports)

          # Check if we need to wrap in Box for margins
          has_margins = json_data['margins'] || json_data['topMargin'] || json_data['bottomMargin'] ||
                       json_data['leftMargin'] || json_data['rightMargin']

          # Always use CustomTextField
          required_imports&.add(:custom_textfield)

          # For data-bound TextViews, use a local remember state to avoid
          # BasicTextField resetting on async StateFlow recomposition.
          code = ""
          has_data_binding = json_data['text'] && json_data['text'].match(/@\{([^}]+)\}/)
          local_state_var = nil

          # TextFieldState-based API (Compose BOM 2026.03.00+)
          required_imports&.add(:text_field_state)
          required_imports&.add(:launched_effect)
          state_var = "textFieldState_#{json_data['id'] || 'textview'}"
          code += indent("val #{state_var} = rememberTextFieldState(initialText = #{value})", depth) + "\n"

          if has_data_binding
            variable = extract_variable_name(json_data['text'])
            view_id = json_data['id'] || 'textview'
            # Sync external → state
            code += indent("LaunchedEffect(#{value}) { if (#{state_var}.text.toString() != #{value}) #{state_var}.edit { replace(0, length, #{value}) } }", depth) + "\n"
            # Sync state → external
            if json_data['onTextChange']
              if Helpers::ModifierBuilder.is_binding?(json_data['onTextChange'])
                handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(json_data['onTextChange'], view_id, 'newValue')
                code += indent("LaunchedEffect(#{state_var}.text) { val newValue = #{state_var}.text.toString(); if (newValue != #{value}) { viewModel.updateData(mapOf(\"#{variable}\" to newValue)); #{handler_call} } }", depth) + "\n"
              else
                code += indent("LaunchedEffect(#{state_var}.text) { val newValue = #{state_var}.text.toString(); if (newValue != #{value}) { viewModel.updateData(mapOf(\"#{variable}\" to newValue)); data.#{json_data['onTextChange']}?.invoke() } }", depth) + "\n"
              end
            else
              code += indent("LaunchedEffect(#{state_var}.text) { val newValue = #{state_var}.text.toString(); if (newValue != #{value}) viewModel.updateData(mapOf(\"#{variable}\" to newValue)) }", depth) + "\n"
            end
          elsif json_data['onTextChange']
            view_id = json_data['id'] || 'textview'
            if Helpers::ModifierBuilder.is_binding?(json_data['onTextChange'])
              handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(json_data['onTextChange'], view_id, 'newValue')
              code += indent("LaunchedEffect(#{state_var}.text) { val newValue = #{state_var}.text.toString(); #{handler_call} }", depth) + "\n"
            else
              code += indent("LaunchedEffect(#{state_var}.text) { data.#{json_data['onTextChange']}?.invoke() }", depth) + "\n"
            end
          end

          # Build FontSpec resolve block ahead of CustomTextField(...) so the
          # textStyle parameter can reference the resolved local. Emits only when
          # at least one font attribute is set.
          tv_font_args = Helpers::FontSpecHelper.build_font_spec_args(json_data, required_imports)
          tv_resolved_var = nil
          if tv_font_args[:has_any]
            tv_resolved_var = next_resolved_var
            code += Helpers::FontSpecHelper.emit_resolve_block(tv_resolved_var, tv_font_args, depth, required_imports) + "\n"
          end

          if has_margins
            required_imports&.add(:box)
            code += indent("CustomTextFieldWithMargins(", depth)
          else
            code += indent("CustomTextField(", depth)
          end

          code += "\n" + indent("state = #{state_var},", depth + 1)

          # For CustomTextFieldWithMargins, we need to specify modifiers differently
          if has_margins
            # Box modifier with margins
            box_modifiers = []
            box_modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
            box_modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
            box_modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
            box_modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
            if box_modifiers.any?
              code += "\n" + indent("boxModifier = Modifier", depth + 1)
              box_modifiers.each do |mod|
                code += "\n" + indent("    #{mod}", depth + 1)
              end
              code += ","
            end

            # TextField modifier
            textfield_modifiers = []
            # Size - default to fillMaxWidth for text areas
            if json_data['width'] == 'matchParent' || !json_data['width']
              textfield_modifiers << ".fillMaxWidth()"
            else
              textfield_modifiers.concat(Helpers::ModifierBuilder.build_size(json_data))
            end

            # Height for multi-line
            if json_data['flexible']
              # flexible: height adjusts to content within min/max bounds
              min_h = json_data['minHeight'] || json_data['height'] || 24
              if json_data['maxHeight']
                textfield_modifiers << ".heightIn(min = #{min_h}.dp, max = #{json_data['maxHeight']}.dp)"
              else
                textfield_modifiers << ".heightIn(min = #{min_h}.dp)"
              end
            elsif json_data['height']
              if json_data['height'] == 'matchParent'
                textfield_modifiers << ".fillMaxHeight()"
              elsif json_data['height'] == 'wrapContent'
                textfield_modifiers << ".wrapContentHeight()"
              else
                textfield_modifiers << ".height(#{json_data['height']}.dp)"
              end
            else
              # Default height for text area
              textfield_modifiers << ".height(120.dp)"
            end

            textfield_modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
            textfield_modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
            textfield_modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))

            if textfield_modifiers.any?
              code += "\n" + indent("textFieldModifier = Modifier", depth + 1)
              textfield_modifiers.each do |mod|
                code += "\n" + indent("    #{mod}", depth + 1)
              end
              code += ","
            end
          else
            # Regular modifiers for CustomTextField
            modifiers = []
            modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))

            # Size - default to fillMaxWidth for text areas
            if json_data['width'] == 'matchParent' || !json_data['width']
              modifiers << ".fillMaxWidth()"
            else
              modifiers.concat(Helpers::ModifierBuilder.build_size(json_data))
            end

            # Height for multi-line
            if json_data['flexible']
              min_h = json_data['minHeight'] || json_data['height'] || 24
              if json_data['maxHeight']
                modifiers << ".heightIn(min = #{min_h}.dp, max = #{json_data['maxHeight']}.dp)"
              else
                modifiers << ".heightIn(min = #{min_h}.dp)"
              end
            elsif json_data['height']
              if json_data['height'] == 'matchParent'
                modifiers << ".fillMaxHeight()"
              elsif json_data['height'] == 'wrapContent'
                modifiers << ".wrapContentHeight()"
              else
                modifiers << ".height(#{json_data['height']}.dp)"
              end
            else
              # Default height for text area
              modifiers << ".height(120.dp)"
            end

            modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
            modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
            modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
            modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
            modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

            if modifiers.any?
              code += "\n" + indent("modifier = Modifier", depth + 1)
              modifiers.each do |mod|
                code += "\n" + indent("    #{mod}", depth + 1)
              end
              code += ","
            end
          end

          # Placeholder with optional line height styling
          if placeholder
            if json_data['hintLineHeightMultiple']
              # Complex placeholder with line height
              required_imports&.add(:text_style)
              base_size = json_data['hintFontSize'] || json_data['fontSize'] || 14
              line_height = base_size.to_f * json_data['hintLineHeightMultiple'].to_f
              code += "\n" + indent("placeholder = {", depth + 1)
              code += "\n" + indent("Text(", depth + 2)
              code += "\n" + indent("text = #{placeholder},", depth + 3)
              code += "\n" + indent("style = TextStyle(lineHeight = #{line_height}.sp)", depth + 3)
              code += "\n" + indent(")", depth + 2)
              code += "\n" + indent("},", depth + 1)
            else
              code += "\n" + indent("placeholder = { Text(#{placeholder}) },", depth + 1)
            end
          end

          # Container inset - internal padding
          if json_data['containerInset']
            inset = json_data['containerInset']
            if inset.is_a?(Array) && inset.length == 4
              code += "\n" + indent("contentPadding = PaddingValues(top = #{inset[0]}.dp, end = #{inset[1]}.dp, bottom = #{inset[2]}.dp, start = #{inset[3]}.dp),", depth + 1)
            elsif inset.is_a?(Array) && inset.length == 2
              code += "\n" + indent("contentPadding = PaddingValues(vertical = #{inset[0]}.dp, horizontal = #{inset[1]}.dp),", depth + 1)
            elsif inset.is_a?(Numeric)
              code += "\n" + indent("contentPadding = PaddingValues(#{inset}.dp),", depth + 1)
            end
          end

          # Shape with corner radius
          if json_data['cornerRadius']
            required_imports&.add(:shape)
            code += "\n" + indent("shape = RoundedCornerShape(#{json_data['cornerRadius']}.dp),", depth + 1)
          end

          # Background colors
          if json_data['background']
            bg_color = Helpers::ResourceResolver.process_color(json_data['background'], required_imports)
            code += "\n" + indent("backgroundColor = #{bg_color},", depth + 1)
          end

          if json_data['highlightBackground']
            highlight_color = Helpers::ResourceResolver.process_color(json_data['highlightBackground'], required_imports)
            code += "\n" + indent("highlightBackgroundColor = #{highlight_color},", depth + 1)
          end

          # Border color for outlined text fields
          if json_data['borderColor']
            border_color = Helpers::ResourceResolver.process_color(json_data['borderColor'], required_imports)
            code += "\n" + indent("borderColor = #{border_color},", depth + 1)
          end

          # Set isOutlined flag (TextView usually wants outlined style)
          code += "\n" + indent("isOutlined = true,", depth + 1)

          # Max lines for TextView
          if json_data['maxLines']
            code += "\n" + indent("maxLines = #{json_data['maxLines']},", depth + 1)
          else
            # Default to multiple lines
            code += "\n" + indent("maxLines = Int.MAX_VALUE,", depth + 1)
          end

          # Single line false for multi-line
          code += "\n" + indent("singleLine = false,", depth + 1)

          # Line break mode (overflow handling)
          if json_data['lineBreakMode']
            # Note: For multi-line TextField, overflow is less relevant
            # but we include it for completeness
            case json_data['lineBreakMode'].to_s.downcase
            when 'clip'
              code += "\n" + indent("// lineBreakMode: clip", depth + 1)
            when 'tail', 'truncatetail'
              code += "\n" + indent("// lineBreakMode: truncate tail", depth + 1)
            when 'head', 'truncatehead'
              code += "\n" + indent("// lineBreakMode: truncate head", depth + 1)
            when 'middle', 'truncatemiddle'
              code += "\n" + indent("// lineBreakMode: truncate middle", depth + 1)
            when 'wordwrap', 'word'
              code += "\n" + indent("// lineBreakMode: word wrap (default)", depth + 1)
            when 'charwrap', 'char'
              code += "\n" + indent("// lineBreakMode: character wrap", depth + 1)
            end
          end

          # Text styling — font attrs flow through Configuration.Font.resolve(FontSpec(...)).
          # fontColor stays inline as it's not part of the FontSpec contract.
          if tv_resolved_var || json_data['fontColor']
            required_imports&.add(:text_style)
            style_parts = []
            if tv_resolved_var
              style_parts.concat(Helpers::FontSpecHelper.style_arg_fragments(tv_resolved_var, required_imports))
            end
            if json_data['fontColor']
              font_color = Helpers::ResourceResolver.process_color(json_data['fontColor'], required_imports)
              style_parts << "color = #{font_color}"
            end
            if style_parts.any?
              code += "\n" + indent("textStyle = TextStyle(#{style_parts.join(', ')})", depth + 1)
            end
          end

          # Keyboard options
          keyboard_options = []

          # keyboardType
          if json_data['keyboardType'] || json_data['input']
            required_imports&.add(:keyboard_type)
            input_type = json_data['keyboardType'] || json_data['input']
            keyboard_type = case input_type.to_s.downcase
            when 'email'
              'KeyboardType.Email'
            when 'number'
              'KeyboardType.Number'
            when 'decimal'
              'KeyboardType.Decimal'
            when 'phone'
              'KeyboardType.Phone'
            when 'url'
              'KeyboardType.Uri'
            else
              'KeyboardType.Text'
            end
            keyboard_options << "keyboardType = #{keyboard_type}"
          end

          if json_data['returnKeyType']
            required_imports&.add(:ime_action)
            ime_action = case json_data['returnKeyType']
            when 'Done'
              'ImeAction.Done'
            when 'Next'
              'ImeAction.Next'
            when 'Default'
              'ImeAction.Default'
            else
              'ImeAction.Default'
            end
            keyboard_options << "imeAction = #{ime_action}"
          end

          if keyboard_options.any?
            required_imports&.add(:keyboard_type)
            code += ",\n" + indent("keyboardOptions = KeyboardOptions(#{keyboard_options.join(', ')})", depth + 1)
          end

          # scrollEnabled - controls vertical scroll within TextView
          if json_data.key?('scrollEnabled')
            # In Compose, scrolling is controlled via verticalScroll modifier
            # For TextField, we just note it - actual implementation may need custom handling
            if json_data['scrollEnabled'] == false
              code += ",\n" + indent("// scrollEnabled = false - scrolling disabled", depth + 1)
            end
          end

          # hideOnFocused - hide placeholder when focused
          # Note: Compose TextField hides placeholder by default when there's text
          # This is primarily for when you want different behavior
          if json_data.key?('hideOnFocused')
            code += ",\n" + indent("// hideOnFocused = #{json_data['hideOnFocused']}", depth + 1)
          end

          # Enabled state
          if json_data.key?('enabled')
            if json_data['enabled'].is_a?(String) && json_data['enabled'].start_with?('@{')
              variable = json_data['enabled'].match(/@\{([^}]+)\}/)[1]
              code += ",\n" + indent("enabled = data.#{variable}", depth + 1)
            else
              code += ",\n" + indent("enabled = #{json_data['enabled']}", depth + 1)
            end
          end

          # Remove trailing comma and close
          if code.end_with?(',')
            code = code[0..-2]
          end

          code += "\n" + indent(")", depth)
          code
        end

        private

        def self.process_data_binding(text)
          return quote(text) unless text.is_a?(String)

          if text.match(/@\{([^}]+)\}/)
            variable = $1
            if variable.include?(' ?? ')
              parts = variable.split(' ?? ')
              var_name = parts[0].strip
              "data.#{var_name}"
            else
              "data.#{variable}"
            end
          else
            quote(text)
          end
        end

        def self.extract_variable_name(text)
          if text && text.match(/@\{([^}]+)\}/)
            $1.split('.').last
          else
            'value'
          end
        end

        def self.quote(text)
          # Escape special characters properly
          escaped = text.gsub('\\', '\\\\\\\\')  # Escape backslashes first
                       .gsub('"', '\\"')           # Escape quotes
                       .gsub("\n", '\\n')           # Escape newlines
                       .gsub("\r", '\\r')           # Escape carriage returns
                       .gsub("\t", '\\t')           # Escape tabs
          "\"#{escaped}\""
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
