# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'

module KjuiTools
  module Compose
    module Components
      class BlurviewComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil, is_root: false)
          # BlurView in Compose requires a special modifier or library
          # For now, we'll create a semi-transparent overlay as a fallback
          code = indent("Box(", depth)
          
          # Build modifiers
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))

          # Add blur effect.
          #
          # `effectStyle` is the declared attribute (enum Light / Dark /
          # ExtraLight) and was not read at all here. Compose has no
          # material-blur equivalent of UIVisualEffectView, so the appearance is
          # expressed as radius + overlay: ExtraLight is the softest blur over a
          # bright scrim, Dark the strongest over a dark one. `blurRadius` stays
          # supported as an explicit override, and it now WINS over the style —
          # it is the more specific instruction.
          effect_style = json_data['effectStyle'].to_s.downcase
          blur_radius = json_data['blurRadius'] || case effect_style
                                                   when 'extralight' then 6
                                                   when 'dark' then 14
                                                   else 10
                                                   end

          # Try to use real blur modifier (available in Compose 1.3+)
          required_imports&.add(:blur)
          modifiers << ".blur(#{blur_radius}.dp)"
          
          # Background color
          if json_data['backgroundColor']
            bg_color = json_data['backgroundColor']
            opacity = json_data['opacity'] || 0.8
            modifiers << ".background(Helpers::ResourceResolver.process_color('#{bg_color}', required_imports).copy(alpha = #{opacity}f))"
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