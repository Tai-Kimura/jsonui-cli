# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'

module KjuiTools
  module Compose
    module Components
      class GradientviewComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # GradientView maps to a Box with gradient background
          code = indent("Box(", depth)
          
          # Build modifiers
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))

          # Add gradient background
          # Support both 'colors' and 'items' for color list
          colors = json_data['colors'] || json_data['items'] || ['#000000', '#FFFFFF']
          
          # Determine gradient direction from orientation or start/end points
          gradient_type = if json_data['orientation']
            case json_data['orientation']
            when 'horizontal'
              'horizontalGradient'
            when 'vertical'
              'verticalGradient'
            when 'diagonal'
              'linearGradient'
            else
              'verticalGradient'
            end
          else
            start_point = json_data['startPoint'] || 'top'
            end_point = json_data['endPoint'] || 'bottom'
            case [start_point, end_point]
            when ['top', 'bottom'], ['bottom', 'top']
              'verticalGradient'
            when ['left', 'right'], ['leading', 'trailing'], ['right', 'left'], ['trailing', 'leading']
              'horizontalGradient'
            else
              'linearGradient'
            end
          end
          
          # Build color list - process colors at generation time, not runtime
          color_list = colors.map { |color| 
            Helpers::ResourceResolver.process_color(color, required_imports)
          }.join(", ")
          
          # Add gradient modifier
          required_imports&.add(:gradient)
          modifiers << ".background(Brush.#{gradient_type}(listOf(#{color_list})))"
          
          # Add corner radius if specified
          if json_data['cornerRadius']
            required_imports&.add(:shape)
            modifiers << ".clip(RoundedCornerShape(#{json_data['cornerRadius']}.dp))"
          end
          
          modifiers.concat(Helpers::ModifierBuilder.build_alignment(json_data, required_imports, parent_type))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          code += Helpers::ModifierBuilder.format(modifiers, depth) if modifiers.any?
          code += "\n" + indent(") {", depth)
          
          # Process children
          children = json_data['child'] || []
          children = [children] unless children.is_a?(Array)
          
          # Return structure for parent to process children
          { code: code, children: children, closing: "\n" + indent("}", depth), json_data: json_data }
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