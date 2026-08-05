# frozen_string_literal: true

require_relative '../helpers/content_scale_helper'
require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'

module KjuiTools
  module Compose
    module Components
      class ImageComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # Image source priority: srcName > src > defaultImage >
          # errorImage > loadingImage > 'placeholder'. A STATIC Image has no
          # in-flight state, so `loadingImage` can only mean fallback imagery
          # here (the sjui converter makes the same call) — and for the same
          # reason `errorImage` belongs in the chain too. It was the only link
          # missing on this platform; sjui has it (image_converter.rb:42).
          # Plan 49 lane C, handed over from D.
          raw_src = json_data['srcName'] || json_data['src'] || json_data['defaultImage'] ||
                    json_data['errorImage'] || json_data['loadingImage'] || 'placeholder'

          # Add required imports
          required_imports&.add(:image)

          code = indent("Image(", depth)

          # Check if src is a binding expression
          if Helpers::ModifierBuilder.is_binding?(raw_src)
            # @{termsCheckboxIcon} -> data.termsCheckboxIcon (String = drawable resource name)
            # Use runtime resource lookup to convert String -> Painter via painterResource
            property_name = Helpers::ModifierBuilder.extract_binding_property(raw_src)
            camel_case_name = to_camel_case(property_name)
            required_imports&.add(:painter_resource)
            required_imports&.add(:r_class)
            required_imports&.add(:local_context)
            code += "\n" + indent("painter = LocalContext.current.let { ctx ->", depth + 1)
            code += "\n" + indent("val resId = ctx.resources.getIdentifier(data.#{camel_case_name}, \"drawable\", ctx.packageName)", depth + 2)
            code += "\n" + indent("if (resId != 0) painterResource(id = resId) else painterResource(id = R.drawable.#{Helpers::ResourceResolver.drawable_name(json_data['defaultImage'] || json_data['loadingImage'] || 'placeholder')})", depth + 2)
            code += "\n" + indent("},", depth + 1)
          else
            # Static resource name needs painterResource
            required_imports&.add(:painter_resource)
            required_imports&.add(:r_class)
            code += "\n" + indent("painter = painterResource(id = R.drawable.#{Helpers::ResourceResolver.drawable_name(raw_src)}),", depth + 1)
          end
          
          # Content description for accessibility
          # Use 'id' (testId) as contentDescription if available, for UIAutomator compatibility
          content_desc = json_data['contentDescription'] || json_data['id'] || ''
          code += "\n" + indent("contentDescription = #{quote(content_desc)},", depth + 1)
          
          # Build modifiers
          modifiers = []

          # Add testTag and contentDescription for UI testing
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))

          # Margins (outer spacing) - must be applied BEFORE size in Compose
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))

          # Size handling
          w = json_data['width']
          h = json_data['height']
          if w && h
            if w == 'matchParent' && h == 'matchParent'
              modifiers << ".fillMaxSize()"
            elsif w == 'matchParent'
              modifiers << ".fillMaxWidth()"
              modifiers << ".height(#{h}.dp)" unless h == 'wrapContent'
            elsif h == 'matchParent'
              modifiers << ".width(#{w}.dp)" unless w == 'wrapContent'
              modifiers << ".fillMaxHeight()"
            elsif w.is_a?(Numeric) && h.is_a?(Numeric)
              modifiers << ".size(#{w}.dp, #{h}.dp)"
            else
              modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, nil, required_imports))
            end
          elsif json_data['size']
            modifiers << ".size(#{json_data['size']}.dp)"
          else
            modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, nil, required_imports))
          end

          # Padding (inner spacing) - applied after size
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
          modifiers.concat(Helpers::ModifierBuilder.build_alignment(json_data, required_imports, parent_type))

          code += Helpers::ModifierBuilder.format(modifiers, depth)
          
          # Content mode (case-insensitive). Vocabulary AND default live in
          # ContentScaleHelper so Image and NetworkImage cannot drift apart
          # again, and so a `@{...}` mode resolves at runtime instead of
          # freezing (plan 49 lane C: Image.contentMode). This caller used to
          # emit NOTHING for a mode outside the table; the declared default is
          # `fit` (attribute_semantics.json#image), which is also Compose's own
          # default for Image — so naming it changes no picture.
          if json_data['contentMode']
            required_imports&.add(:content_scale)
            if (scale = Helpers::ContentScaleHelper.scale_expression(json_data['contentMode']))
              code += ",\n" + indent("contentScale = #{scale}", depth + 1)
            end
            if (alignment = Helpers::ContentScaleHelper.alignment_expression(json_data['contentMode']))
              required_imports&.add(:alignment)
              code += ",\n" + indent("alignment = #{alignment}", depth + 1)
            end
          end
          
          # renderingMode — `template` means "take the tint, ignore the asset's own
          # colours", which is a ColorFilter here and `.renderingMode(.template)`
          # on iOS. `original` says the opposite, so it suppresses a tint that
          # would otherwise apply. Emitted after contentScale, which is where the
          # Image( ... ) argument list ends.
          if (filter = rendering_color_filter(json_data, required_imports))
            code += ",\n" + indent("colorFilter = #{filter}", depth + 1)
          end

          code += "\n" + indent(")", depth)
          code
        end

        def self.rendering_color_filter(json_data, required_imports)
          mode = json_data['renderingMode'].to_s.downcase
          tint = json_data['tintColor'] || json_data['iconColor']

          case mode
          when 'template'
            required_imports&.add(:color_filter)
            color = if tint
                      Helpers::ResourceResolver.process_color(tint, required_imports)
                    else
                      # Compose's stand-in for "the current foreground colour",
                      # which is what a template image takes on iOS.
                      required_imports&.add(:local_content_color)
                      'LocalContentColor.current'
                    end
            "ColorFilter.tint(#{color})"
          when 'original'
            nil
          else
            # No renderingMode: a tint still applies if one was asked for.
            return nil unless tint

            required_imports&.add(:color_filter)
            "ColorFilter.tint(#{Helpers::ResourceResolver.process_color(tint, required_imports)})"
          end
        end
        
        private

        def self.to_camel_case(snake_case_string)
          return snake_case_string unless snake_case_string.include?('_')
          parts = snake_case_string.split('_')
          parts[0] + parts[1..-1].map(&:capitalize).join
        end

        def self.quote(text)
          "\"#{text.gsub('"', '\\"')}\""
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