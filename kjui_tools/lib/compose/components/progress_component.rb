# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'
require_relative '../helpers/inherited_tint'

module KjuiTools
  module Compose
    module Components
      class ProgressComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # Progress can have a value (determinate) or be indeterminate.
          # `progress` is the canonical determinate value (0..1, declared in
          # attribute_definitions); `value` is the undeclared legacy spelling
          # (see shared/core/attribute_semantics.json → progressValue).
          # A lone `bind` arrives as `progress` (JsonUIShared::BindFold at the
          # dispatch); it was read here before `progress`, so a `bind` beside
          # a bound `progress` drew the other value.
          literal = json_data['progress'] || json_data['value']
          has_value = literal

          if has_value
            # Determinate progress (LinearProgressIndicator)
            value = if literal && literal.to_s.match(/@\{([^}]+)\}/)
              variable = $1
              "data.#{variable}.toFloat()"
            elsif literal
              "#{literal}f"
            else
              '0f'
            end
            
            code = indent("LinearProgressIndicator(", depth)
            code += "\n" + indent("progress = { #{value} },", depth + 1)
          else
            # Indeterminate progress — a bar, as the determinate one is.
            # `style` is the style file's name (common.style), not a shape:
            # Progress declares none, and a style named `circular` / `large`
            # drew a spinner here while every other path drew a bar.
            code = indent("LinearProgressIndicator(", depth)
          end
          
          # Build modifiers
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_shadow(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          code += Helpers::ModifierBuilder.format(modifiers, depth) if modifiers.any?
          
          # Progress colors. `tintColor` is the cross-platform (UIKit)
          # spelling of the indicator colour — progressTintColor wins when
          # both are present.
          # Without one of its own, the tint a container handed down
          # (InheritedTint) — so the colour is always emitted.
          progress_tint = json_data['progressTintColor'] || json_data['tintColor']
          begin
            colors_params = []

            color_resolved = if progress_tint
                               Helpers::ResourceResolver.process_color(progress_tint, required_imports)
                             else
                               Helpers::InheritedTint.accent(required_imports)
                             end
            colors_params << "color = #{color_resolved}"
            
            if json_data['trackTintColor']
              trackcolor_resolved = Helpers::ResourceResolver.process_color(json_data['trackTintColor'], required_imports)
              colors_params << "trackColor = #{trackcolor_resolved}"
            end
            
            if colors_params.any?
              # After `(` (no argument yet) or a trailing `,` (the progress
              # argument, with no modifier after it) no separator is added:
              # the colour is always emitted now, and `(,` / `,,` do not parse.
              separator = code.rstrip.end_with?('(', ',') ? "\n" : ",\n"
              code += separator + colors_params.map { |param| indent(param, depth + 1) }.join(",\n")
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