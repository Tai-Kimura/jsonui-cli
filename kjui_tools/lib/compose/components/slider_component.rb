# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'
require_relative '../../core/normalization'

module KjuiTools
  module Compose
    module Components
      class SliderComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # Slider uses 'value' or 'bind' for binding
          value = if json_data['value']
            if json_data['value'].is_a?(String) && json_data['value'].match(/@\{([^}]+)\}/)
              variable = $1
              "data.#{variable}.toFloat()"
            else
              # Direct value
              "#{json_data['value']}f"
            end
          elsif json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
            variable = $1
            "data.#{variable}.toFloat()"
          else
            '0f'
          end
          
          # Canonical minimum/maximum with alias fallbacks (skipped on
          # L1-normalized layouts); 'min'/'max' are undeclared legacy
          # spellings, always honored last.
          min_value = Core::Normalization.attr_lookup(json_data, 'minimum', 'minimumValue', 'minValue') || json_data['min'] || 0
          max_value = Core::Normalization.attr_lookup(json_data, 'maximum', 'maximumValue', 'maxValue') || json_data['max'] || 100
          
          code = indent("Slider(", depth)
          code += "\n" + indent("value = #{value},", depth + 1)
          
          # onValueChange handler
          binding_variable = nil
          if json_data['value'] && json_data['value'].is_a?(String) && json_data['value'].match(/@\{([^}]+)\}/)
            binding_variable = $1
          elsif json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
            binding_variable = $1
          end
          
          view_id = json_data['id'] || 'slider'
          on_value_change = Core::Normalization.attr_lookup(json_data, 'onValueChange', 'onValueChanged')
          if on_value_change
            # onValueChange (camelCase) -> binding format only (@{functionName})
            if Helpers::ModifierBuilder.is_binding?(on_value_change)
              handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(on_value_change, view_id, 'it')
              if binding_variable
                # Both data binding and event handler
                code += "\n" + indent("onValueChange = { newValue -> viewModel.updateData(mapOf(\"#{binding_variable}\" to newValue.toDouble())); #{handler_call} },", depth + 1)
              else
                # Event handler only
                code += "\n" + indent("onValueChange = { #{handler_call} },", depth + 1)
              end
            else
              code += "\n" + indent("onValueChange = { // ERROR: #{on_value_change} - camelCase events require binding format @{functionName} },", depth + 1)
            end
          elsif binding_variable
            # Update the bound variable only
            code += "\n" + indent("onValueChange = { newValue -> viewModel.updateData(mapOf(\"#{binding_variable}\" to newValue.toDouble())) },", depth + 1)
          else
            code += "\n" + indent("onValueChange = { },", depth + 1)
          end
          
          # Value range
          code += "\n" + indent("valueRange = #{min_value}f..#{max_value}f,", depth + 1)
          
          # Steps
          if json_data['step'] && json_data['step'] > 0
            steps = ((max_value - min_value) / json_data['step'].to_f).to_i - 1
            code += "\n" + indent("steps = #{steps},", depth + 1) if steps > 0
          end
          
          # Build modifiers
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          code += Helpers::ModifierBuilder.format(modifiers, depth) if modifiers.any?
          
          # Slider colors
          if json_data['minimumTrackTintColor'] || json_data['maximumTrackTintColor'] || json_data['thumbTintColor']
            required_imports&.add(:slider_colors)
            colors_params = []
            
            if json_data['thumbTintColor']
              thumbcolor_resolved = Helpers::ResourceResolver.process_color(json_data['thumbTintColor'], required_imports)
              colors_params << "thumbColor = #{thumbcolor_resolved}"
            end
            
            if json_data['minimumTrackTintColor']
              activetrackcolor_resolved = Helpers::ResourceResolver.process_color(json_data['minimumTrackTintColor'], required_imports)
              colors_params << "activeTrackColor = #{activetrackcolor_resolved}"
            end
            
            if json_data['maximumTrackTintColor']
              inactivetrackcolor_resolved = Helpers::ResourceResolver.process_color(json_data['maximumTrackTintColor'], required_imports)
              colors_params << "inactiveTrackColor = #{inactivetrackcolor_resolved}"
            end
            
            if colors_params.any?
              code += ",\n" + indent("colors = SliderDefaults.colors(", depth + 1)
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