# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'

module KjuiTools
  module Compose
    module Components
      class GradientviewComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil, is_root: false)
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

          # Add gradient background.
          # The DECLARED color source is `gradient` (array) — read it first;
          # 'colors'/'items' are undeclared legacy spellings. This path used
          # to read only the legacy names, so every declared gradient fell to
          # the black/white default (ios/web read the declaration; the kotlin
          # pair was the outlier — parity family kjui-codegen-gradientview).
          # A legacy object wrapper { colors:, items: } is tolerated.
          colors = json_data['gradient'] || json_data['colors'] || json_data['items']
          colors = colors['colors'] || colors['items'] if colors.is_a?(Hash)
          colors = ['#000000', '#FFFFFF'] unless colors.is_a?(Array) && !colors.empty?

          # Direction: the DECLARED attr is `gradientDirection`
          # (enum Vertical/Horizontal/Oblique — matched case-insensitively
          # like sjui/rjui); 'orientation' and startPoint/endPoint stay as
          # legacy fallbacks.
          gradient_type = case json_data['gradientDirection'].to_s.downcase
          when 'horizontal'
            'horizontalGradient'
          when 'oblique'
            'linearGradient'
          when 'vertical'
            'verticalGradient'
          else
            if json_data['orientation']
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
          end
          
          # Build color list - process colors at generation time, not runtime
          resolved_colors = colors.map { |color|
            Helpers::ResourceResolver.process_color(color, required_imports)
          }

          # Add gradient modifier. `locations` (0.0-1.0 stops, one per
          # colour) selects the colorStops overload; without it the colours
          # spread evenly, which is the listOf form.
          required_imports&.add(:gradient)
          locations = json_data['locations']
          if locations.is_a?(Array) && locations.length == resolved_colors.length
            stops = locations.zip(resolved_colors).map { |loc, color| "#{loc}f to #{color}" }.join(", ")
            modifiers << ".background(Brush.#{gradient_type}(#{stops}))"
          else
            modifiers << ".background(Brush.#{gradient_type}(listOf(#{resolved_colors.join(', ')})))"
          end
          
          # Add corner radius if specified
          if json_data['cornerRadius']
            required_imports&.add(:shape)
            modifiers << ".clip(RoundedCornerShape(#{json_data['cornerRadius']}.dp))"
          end
          
          modifiers.concat(Helpers::ModifierBuilder.build_alignment(json_data, required_imports, parent_type))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          if modifiers.any? || is_root
            code += Helpers::ModifierBuilder.format(modifiers, depth, is_root: is_root)
          end
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