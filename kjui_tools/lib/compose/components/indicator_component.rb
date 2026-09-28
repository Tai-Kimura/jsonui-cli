# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'

module KjuiTools
  module Compose
    module Components
      class IndicatorComponent
        # The spinner's size for each indicatorStyle that has one of its own;
        # `medium` is CircularProgressIndicator's default and `linear` a bar.
        STYLE_SIZES = { 'small' => 16, 'large' => 48 }.freeze

        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # indicatorStyle (declared for Compose): small / medium / large are
          # the spinner's size, linear a bar. The legacy spellings — `style`,
          # which is the style-file key, and an undeclared `size` — are no
          # longer read here: the layout normalizer folds them into
          # indicatorStyle and width / height, with a warning
          # (kjui-dynamic-components-that-skip-the-common-modifiers, C).
          style = json_data['indicatorStyle'] || 'medium'
          is_animating = json_data['animating']
          
          # Check if animating is controlled by data binding
          show_condition = if is_animating && is_animating.is_a?(String) && is_animating.match(/@\{([^}]+)\}/)
            variable = $1
            "data.#{variable}"
          elsif is_animating == false
            'false'
          else
            'true'
          end
          
          # Wrap in if condition if controlled by animating attribute
          if is_animating != nil
            code = indent("if (#{show_condition}) {", depth)
            actual_depth = depth + 1
          else
            code = ""
            actual_depth = depth
          end
          
          # Determine indicator type based on style
          if style == 'linear'
            code += "\n" if is_animating != nil
            code += indent("LinearProgressIndicator(", actual_depth)
          else
            code += "\n" if is_animating != nil
            code += indent("CircularProgressIndicator(", actual_depth)
          end
          
          # Build modifiers
          modifiers = []

          # Add testTag and contentDescription for UI testing
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))

          # Size, in the size slot after the margins. A declared length
          # (a number or a bound number) wins over the style's size and goes
          # through the one size builder; so do matchParent and a weight,
          # which were not ruled and keep their old picture. A wrapContent
          # axis is the content's size, and the style sets the content's
          # size, so it is NOT a declaration here: with the style's size of
          # its own, a wrapContent axis draws the style's size, and an
          # Indicator that declares only wrapContent draws `.size(style)`
          # (kjui-indicator-style-loses-to-a-declared-wrapcontent). The
          # style's size sat before the margins, so they padded the inside of
          # the 48dp spinner.
          style_size = STYLE_SIZES[style]
          size_json, wrap_width, wrap_height = style_size ? strip_wrap_axes(json_data) : [json_data, false, false]
          declared_size = size_json['width'] || size_json['height'] || size_json['frame']
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          if declared_size
            modifiers.concat(Helpers::ModifierBuilder.build_size(size_json, parent_type, required_imports))
            modifiers << ".width(#{Helpers::BoundValue.dp(style_size)})" if wrap_width
            modifiers << ".height(#{Helpers::BoundValue.dp(style_size)})" if wrap_height
          elsif style_size
            modifiers << ".size(#{Helpers::BoundValue.dp(style_size)})"
          end
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          # shadow → background (border + clip + background): the View slots.
          modifiers.concat(Helpers::ModifierBuilder.build_shadow(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_alignment(json_data, required_imports, parent_type))
          
          # Add weight modifier if in Row or Column
          if parent_type == 'Row' || parent_type == 'Column'
            modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
          end
          
          has_modifiers = modifiers.any?
          code += Helpers::ModifierBuilder.format(modifiers, actual_depth) if has_modifiers

          # Color
          if json_data['color']
            color_resolved = Helpers::ResourceResolver.process_color(json_data['color'], required_imports)
            if has_modifiers
              code += ",\n" + indent("color = #{color_resolved}", actual_depth + 1)
            else
              code += "\n" + indent("color = #{color_resolved}", actual_depth + 1)
              has_modifiers = true
            end
          end

          # Track color for linear progress. The separator follows what came
          # before: with neither modifiers nor a color the first argument is
          # this one, and the `,` it always led with opened the call with
          # `(,` — not Kotlin.
          if style == 'linear' && json_data['trackColor']
            trackcolor_resolved = Helpers::ResourceResolver.process_color(json_data['trackColor'], required_imports)
            code += (has_modifiers ? ",\n" : "\n") + indent("trackColor = #{trackcolor_resolved}", actual_depth + 1)
            has_modifiers = true
          end

          # Stroke width for circular progress
          if style != 'linear' && json_data['strokeWidth']
            code += (has_modifiers ? ",\n" : "\n") + indent("strokeWidth = #{Helpers::BoundValue.dp(json_data['strokeWidth'])}", actual_depth + 1)
            has_modifiers = true
          end
          
          code += "\n" + indent(")", actual_depth)
          
          # Close if condition
          if is_animating != nil
            code += "\n" + indent("}", depth)
          end
          
          code
        end
        
        private

        WRAP_SPELLINGS = %w[wrapContent wrap_content].freeze

        # The declaration without its wrapContent axes (top level or inside a
        # `frame` object), and which axes were wrapContent. A frame left with
        # neither axis is dropped, so it declares nothing.
        def self.strip_wrap_axes(json_data)
          size_json = json_data.dup
          wrap_width = false
          wrap_height = false
          if size_json['frame'].is_a?(Hash)
            frame = size_json['frame'].dup
            wrap_width = WRAP_SPELLINGS.include?(frame['width'])
            wrap_height = WRAP_SPELLINGS.include?(frame['height'])
            frame.delete('width') if wrap_width
            frame.delete('height') if wrap_height
            if frame['width'] || frame['height']
              size_json['frame'] = frame
            else
              size_json.delete('frame')
            end
          else
            wrap_width = WRAP_SPELLINGS.include?(size_json['width'])
            wrap_height = WRAP_SPELLINGS.include?(size_json['height'])
            size_json.delete('width') if wrap_width
            size_json.delete('height') if wrap_height
          end
          [size_json, wrap_width, wrap_height]
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