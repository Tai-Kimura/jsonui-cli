# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'

module KjuiTools
  module Compose
    module Components
      class ToggleComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # Toggle in iOS maps to Switch in Android
          code = indent("Switch(", depth)
          
          # Checked state
          checked_value = if json_data['data']
            "@{#{json_data['data']}}"
          elsif json_data['isOn']
            json_data['isOn'].to_s
          else
            'false'
          end
          
          # Process data binding
          if checked_value.start_with?('@{')
            variable = checked_value[2..-2]
            code += "\n" + indent("checked = data.#{variable},", depth + 1)
            code += "\n" + indent("onCheckedChange = { newValue -> data.#{variable} = newValue },", depth + 1)
          else
            code += "\n" + indent("checked = #{checked_value},", depth + 1)
            
            # Handle onclick (lowercase) -> selector format only
            # onClick (camelCase) -> binding format only
            if json_data['onclick']
              handler_call = Helpers::ModifierBuilder.get_event_handler_call(json_data['onclick'], is_camel_case: false)
              code += "\n" + indent("onCheckedChange = { #{handler_call} },", depth + 1)
            elsif json_data['onClick']
              handler_call = Helpers::ModifierBuilder.get_event_handler_call(json_data['onClick'], is_camel_case: true)
              code += "\n" + indent("onCheckedChange = { #{handler_call} },", depth + 1)
            else
              code += "\n" + indent("onCheckedChange = { },", depth + 1)
            end
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
          
          code += Helpers::ModifierBuilder.format(modifiers, depth)
          
          # Colors if specified
          if json_data['tintColor'] || json_data['backgroundColor']
            required_imports&.add(:switch_colors)
            code += ",\n" + indent("colors = SwitchDefaults.colors(", depth + 1)
            
            if json_data['tintColor']
              checkedthumbcolor_resolved = Helpers::ResourceResolver.process_color(json_data['tintColor'], required_imports)
              code += "\n" + indent("checkedThumbColor = #{checkedthumbcolor_resolved},", depth + 2)
              checkedtrackcolor_resolved = Helpers::ResourceResolver.process_color(json_data['tintColor'], required_imports)
              code += "\n" + indent("checkedTrackColor = #{checkedtrackcolor_resolved}.copy(alpha = 0.5f)", depth + 2)
            end
            
            if json_data['backgroundColor']
              code += ",\n" if json_data['tintColor']
              uncheckedtrackcolor_resolved = Helpers::ResourceResolver.process_color(json_data['backgroundColor'], required_imports)
              code += "\n" + indent("uncheckedTrackColor = #{uncheckedtrackcolor_resolved}", depth + 2)
            end
            
            code += "\n" + indent(")", depth + 1)
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