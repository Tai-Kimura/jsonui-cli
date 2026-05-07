# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'

module KjuiTools
  module Compose
    module Components
      class ProgressComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # Progress can have a value (determinate) or be indeterminate
          has_value = json_data['value'] || json_data['bind']
          
          if has_value
            # Determinate progress (LinearProgressIndicator)
            value = if json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
              variable = $1
              "data.#{variable}.toFloat()"
            elsif json_data['value'] && json_data['value'].match(/@\{([^}]+)\}/)
              variable = $1
              "data.#{variable}.toFloat()"
            elsif json_data['value']
              "#{json_data['value']}f"
            else
              '0f'
            end
            
            code = indent("LinearProgressIndicator(", depth)
            code += "\n" + indent("progress = { #{value} },", depth + 1)
          else
            # Indeterminate progress
            style = json_data['style'] || 'linear'
            
            if style == 'circular' || style == 'large'
              code = indent("CircularProgressIndicator(", depth)
            else
              code = indent("LinearProgressIndicator(", depth)
            end
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
          
          # Progress colors
          if json_data['progressTintColor'] || json_data['trackTintColor']
            colors_params = []
            
            if json_data['progressTintColor']
              color_resolved = Helpers::ResourceResolver.process_color(json_data['progressTintColor'], required_imports)
              colors_params << "color = #{color_resolved}"
            end
            
            if json_data['trackTintColor']
              trackcolor_resolved = Helpers::ResourceResolver.process_color(json_data['trackTintColor'], required_imports)
              colors_params << "trackColor = #{trackcolor_resolved}"
            end
            
            if colors_params.any?
              code += ",\n" + colors_params.map { |param| indent(param, depth + 1) }.join(",\n")
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