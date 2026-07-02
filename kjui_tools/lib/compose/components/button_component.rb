# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'
require_relative '../helpers/font_spec_helper'
require_relative '../../core/normalization'

module KjuiTools
  module Compose
    module Components
      class ButtonComponent
        @counter ||= 0

        def self.next_resolved_var
          @counter += 1
          "resolved_button#{@counter}"
        end

        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # Button uses 'text' attribute per SwiftJsonUI spec
          text = Helpers::ResourceResolver.process_text(json_data['text'] || 'Button', required_imports)

          code = indent("Button(", depth)

          # Handle click events
          # onclick (lowercase) -> selector format (string only)
          # onClick (camelCase) -> binding format only (@{functionName})
          view_id = json_data['id'] || 'button'
          if json_data['onclick']
            # Lowercase onclick - legacy selector format
            handler_call = Helpers::ModifierBuilder.get_event_handler_call(json_data['onclick'], is_camel_case: false)
            code += "\n" + indent("onClick = { #{handler_call} }", depth + 1)
          elsif json_data['onClick']
            # camelCase onClick - binding format only (@{functionName})
            if Helpers::ModifierBuilder.is_binding?(json_data['onClick'])
              handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(json_data['onClick'], view_id, nil)
              code += "\n" + indent("onClick = { #{handler_call} }", depth + 1)
            else
              code += "\n" + indent("onClick = { // ERROR: #{json_data['onClick']} - camelCase events require binding format @{functionName} }", depth + 1)
            end
          else
            code += "\n" + indent("onClick = { }", depth + 1)
          end
          
          # Build modifiers (only margins, size, and weight, not padding)
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          # onLongPress: Button's own inner .clickable consumes the down event
          # in the Main pass, so the detector must watch the Initial pass
          # (see ModifierBuilder.build_long_pressable). combinedClickable on
          # this modifier would race the inner clickable the same way.
          modifiers.concat(Helpers::ModifierBuilder.build_long_pressable(json_data, required_imports))

          # Format modifiers only if there are modifiers
          if modifiers.any?
            code += ","
            code += Helpers::ModifierBuilder.format(modifiers, depth)
          end
          
          # Add shape with cornerRadius (always set to match dynamic defaults)
          required_imports&.add(:shape)
          required_imports&.add(:configuration)
          corner_radius = json_data['cornerRadius'] || 'Configuration.Button.defaultCornerRadius'
          code += ",\n" + indent("shape = RoundedCornerShape(#{corner_radius}.dp)", depth + 1)
          
          # Add contentPadding for internal padding
          # Support both 'padding' (number), 'paddings' (array), and individual padding attributes
          padding_data = json_data['paddings'] || json_data['padding']
          
          if padding_data || json_data['paddingTop'] || json_data['paddingBottom'] ||
             json_data['paddingLeft'] || json_data['paddingRight'] || json_data['paddingStart'] ||
             json_data['paddingEnd'] || json_data['paddingHorizontal'] || json_data['paddingVertical'] ||
             json_data['leftPadding'] || json_data['rightPadding']
            required_imports&.add(:button_padding)
            
            padding_values = []
            
            if padding_data
              # Handle paddings array or padding number
              if padding_data.is_a?(Array)
                case padding_data.length
                when 1
                  # One value: all sides
                  padding_values << "#{padding_data[0]}.dp"
                when 2
                  # Two values: [vertical, horizontal]
                  padding_values << "vertical = #{padding_data[0]}.dp"
                  padding_values << "horizontal = #{padding_data[1]}.dp"
                when 3
                  # Three values: [top, horizontal, bottom]
                  padding_values << "top = #{padding_data[0]}.dp"
                  padding_values << "horizontal = #{padding_data[1]}.dp"
                  padding_values << "bottom = #{padding_data[2]}.dp"
                when 4
                  # Four values: [top, right, bottom, left] (iOS UIEdgeInsets convention)
                  padding_values << "top = #{padding_data[0]}.dp"
                  padding_values << "end = #{padding_data[1]}.dp"
                  padding_values << "bottom = #{padding_data[2]}.dp"
                  padding_values << "start = #{padding_data[3]}.dp"
                end
              else
                # Single number: all sides
                padding_values << "#{padding_data}.dp"
              end
            else
              # Handle individual padding attributes
              top_padding = json_data['paddingTop'] || json_data['paddingVertical'] || 0
              bottom_padding = json_data['paddingBottom'] || json_data['paddingVertical'] || 0
              start_padding = json_data['paddingStart'] || json_data['paddingLeft'] || json_data['leftPadding'] || json_data['paddingHorizontal'] || 0
              end_padding = json_data['paddingEnd'] || json_data['paddingRight'] || json_data['rightPadding'] || json_data['paddingHorizontal'] || 0
              
              if top_padding == bottom_padding && start_padding == end_padding && top_padding == start_padding
                # All same, use single value
                padding_values << "#{top_padding}.dp" if top_padding > 0
              elsif top_padding == bottom_padding && start_padding == end_padding
                # Different horizontal and vertical
                padding_values << "horizontal = #{start_padding}.dp" if start_padding > 0
                padding_values << "vertical = #{top_padding}.dp" if top_padding > 0
              else
                # All different, need to specify each
                padding_values << "start = #{start_padding}.dp" if start_padding > 0
                padding_values << "top = #{top_padding}.dp" if top_padding > 0
                padding_values << "end = #{end_padding}.dp" if end_padding > 0
                padding_values << "bottom = #{bottom_padding}.dp" if bottom_padding > 0
              end
            end
            
            if padding_values.any?
              code += ",\n" + indent("contentPadding = PaddingValues(#{padding_values.join(', ')})", depth + 1)
            end
          else
            # No padding specified: use zero padding to avoid Material default (24dp horizontal)
            code += ",\n" + indent("contentPadding = PaddingValues(0.dp)", depth + 1)
          end
          
          # Button colors including normal, disabled, and pressed states
          # Always set to match dynamic defaults
          required_imports&.add(:button_colors)
          colors_code = "colors = ButtonDefaults.buttonColors("
          color_params = []

          if json_data['background']
            background_color = Helpers::ResourceResolver.process_color(json_data['background'], required_imports)
            color_params << "containerColor = #{background_color}"
          else
            color_params << "containerColor = Configuration.Button.defaultBackgroundColor"
          end

          if json_data['disabledBackground']
            disabled_bg_color = Helpers::ResourceResolver.process_color(json_data['disabledBackground'], required_imports)
            color_params << "disabledContainerColor = #{disabled_bg_color}"
          end

          if json_data['fontColor']
            font_color = Helpers::ResourceResolver.process_color(json_data['fontColor'], required_imports)
            color_params << "contentColor = #{font_color}"
          else
            color_params << "contentColor = Configuration.Button.defaultTextColor"
          end

          if json_data['disabledFontColor']
            disabled_font_color = Helpers::ResourceResolver.process_color(json_data['disabledFontColor'], required_imports)
            color_params << "disabledContentColor = #{disabled_font_color}"
          end

          # Note: highlightColor (pressed state) isn't directly supported in Material3 ButtonDefaults
          # We'd need a custom button implementation or InteractionSource for true pressed state
          # (canonical 'highlightColor'; 'hilightColor' is its typo alias,
          # skipped on L1-normalized layouts). Comment text keeps the
          # legacy spelling so L0/L1 output stays byte-identical.
          highlight_color_value = Core::Normalization.attr_lookup(json_data, 'highlightColor', 'hilightColor')
          if highlight_color_value
            color_params << "// hilightColor: #{highlight_color_value} - Use InteractionSource for pressed state"
          end

          colors_code += "\n" + color_params.map { |param| indent(param, depth + 2) }.join(",\n")
          colors_code += "\n" + indent(")", depth + 1)
          code += ",\n" + indent(colors_code, depth + 1)

          # Handle border
          if json_data['borderColor']
            required_imports&.add(:border_stroke)
            border_color = Helpers::ResourceResolver.process_color(json_data['borderColor'], required_imports)
            border_width = json_data['borderWidth'] || 1
            code += ",\n" + indent("border = BorderStroke(#{border_width}.dp, #{border_color})", depth + 1)
          end

          # Handle enabled attribute
          if json_data.key?('enabled')
            if json_data['enabled'].is_a?(String) && json_data['enabled'].start_with?('@{')
              # Data binding for enabled
              variable = json_data['enabled'].match(/@\{([^}]+)\}/)[1]
              code += ",\n" + indent("enabled = data.#{variable}", depth + 1)
            else
              code += ",\n" + indent("enabled = #{json_data['enabled']}", depth + 1)
            end
          end
          
          code += "\n" + indent(") {", depth)
          code += "\n" + indent("Text(#{text})", depth + 1)

          # Apply text attributes if specified (fontColor handled in ButtonDefaults.buttonColors).
          # All font attrs (fontFamily/font/fontWeight/fontSize) flow through the unified
          # Configuration.Font.resolve(FontSpec(...)) hook so the app's fontProvider sees
          # the full context.
          font_args = Helpers::FontSpecHelper.build_font_spec_args(json_data, required_imports)
          if font_args[:has_any]
            var_name = next_resolved_var
            resolve_block = Helpers::FontSpecHelper.emit_resolve_block(var_name, font_args, depth + 1, required_imports)
            text_arg_lines = Helpers::FontSpecHelper.text_arg_lines(var_name, depth + 1, required_imports)

            text_code = resolve_block + "\n" + indent("Text(", depth + 1) +
                        "\n" + indent("text = #{text},", depth + 2) +
                        "\n" + text_arg_lines +
                        "\n" + indent(")", depth + 1)
            code = code.sub(/Text\(#{Regexp.escape(text)}\)/, text_code.strip)
          end
          
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