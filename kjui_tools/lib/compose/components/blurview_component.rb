# frozen_string_literal: true

require_relative '../helpers/effect_style_helper'
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
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, nil, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))

          # Add corner radius if specified (before background/blur — the
          # dynamic chain clips first)
          if json_data['cornerRadius']
            required_imports&.add(:shape)
            modifiers << ".clip(RoundedCornerShape(#{json_data['cornerRadius']}.dp))"
          end

          # `effectStyle` (enum Light / Dark / ExtraLight) is expressed the
          # same way as the dynamic path: a translucent scrim under a real
          # `.blur(...)` — Compose has no material-blur equivalent of
          # UIVisualEffectView. The scrim is only the fallback when no
          # explicit background is declared, and `blurRadius` (default 10)
          # is a plain radius, NOT derived from the style — mirrors
          # DynamicBlurViewComponent (effectStyleColor + resolveFloat).
          effect_style = json_data['effectStyle'].to_s.downcase
          blur_radius = json_data['blurRadius'] || 10

          bg_source = json_data['background'] || json_data['backgroundColor']
          bg_expr = if bg_source
                      Helpers::ResourceResolver.process_color(bg_source, required_imports)
                    else
                      # Same table the common path uses (EffectStyleHelper):
                      # the component that owns the concept and the `common`
                      # spelling must not answer differently. The UIKit trio
                      # keeps the alphas this component already emitted, so
                      # sharing the table changes no Blur output.
                      Helpers::EffectStyleHelper.scrim(json_data['effectStyle'])
                    end
          if bg_expr
            opacity = json_data['opacity'] || json_data['alpha']
            bg_expr = "(#{bg_expr}).copy(alpha = #{opacity.to_f}f)" if opacity
            modifiers << ".background(#{bg_expr})"
          end

          # Real blur modifier (Compose 1.3+), after the scrim like the
          # dynamic chain
          required_imports&.add(:blur)
          modifiers << ".blur(#{blur_radius}.dp)"
          
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