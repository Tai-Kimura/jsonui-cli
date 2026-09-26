# frozen_string_literal: true

require_relative '../helpers/content_scale_helper'
require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'
require_relative '../helpers/image_accessibility_helper'
require_relative '../../core/string_literals'

module KjuiTools
  module Compose
    module Components
      class CircleImageComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # CircleImage can be local or network image
          is_network = json_data['url'] || (json_data['source'] && json_data['source'].start_with?('http'))
          
          if is_network
            required_imports&.add(:async_image)
            url = process_data_binding(json_data['url'] || json_data['source'] || json_data['src'] || '')
            
            code = indent("AsyncImage(", depth)
            code += "\n" + indent("model = #{url},", depth + 1)
          else
            # Local image
            image_name = json_data['source'] || json_data['src'] || 'placeholder'
            # Remove file extension and convert to resource name
            resource_name = image_name.gsub('.png', '').gsub('.jpg', '').gsub('-', '_').downcase
            
            # The names this emit uses are imported where it uses them: the
            # local branch added none, so a screen whose only image was a
            # local CircleImage did not compile — Image, painterResource and R
            # unresolved (measured: the 35 Image conformance layouts drawn as
            # CircleImage, compiled against Compose and KotlinJsonUI;
            # jsonui-cli 1.9.0).
            required_imports&.add(:image)
            required_imports&.add(:painter_resource)
            required_imports&.add(:r_class)
            code = indent("Image(", depth)
            code += "\n" + indent("painter = painterResource(id = R.drawable.#{Helpers::ResourceResolver.drawable_name(resource_name)}),", depth + 1)
          end
          
          # The alt, or null when decorative (ImageAccessibilityHelper); the
          # English "Profile Image" is kept only for an image that operates a
          # control and has no alt, which the build names.
          content_description = Helpers::ImageAccessibilityHelper.content_description(json_data, 'Profile Image', required_imports)
          code += "\n" + indent("contentDescription = #{content_description},", depth + 1)
          
          # contentMode, as on Image (CircleImage is an Image spelling —
          # type_synonyms.json render_as — and follows its contentMode, default
          # fit, attribute_semantics.json#image; 4f ruling, 2026-09-26). This
          # emitted ContentScale.Crop for every mode, so a CircleImage drew
          # cropped on Android and fit on iOS and web. No contentMode: nothing
          # is emitted and Compose's own default (Fit) draws, as for Image.
          if json_data['contentMode']
            required_imports&.add(:content_scale)
            if (scale = Helpers::ContentScaleHelper.scale_expression(json_data['contentMode']))
              code += "\n" + indent("contentScale = #{scale},", depth + 1)
            end
            if (alignment = Helpers::ContentScaleHelper.alignment_expression(json_data['contentMode']))
              required_imports&.add(:alignment)
              code += "\n" + indent("alignment = #{alignment},", depth + 1)
            end
          end
          
          # Build modifiers for circular shape
          modifiers = []

          # Add testTag and contentDescription for UI testing
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))

          # Margins are the outer spacing: before (outside) the size. They sat
          # after the size and the circle clip, where they padded the inside of
          # the 48dp circle instead of spacing it from its siblings
          # (kjui-dynamic-components-that-skip-the-common-modifiers, measured
          # as CG_ORDER CircleImage margins INSIDE on 24f7fad0).
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))

          # Size. The declared `width` / `height` (common) win and go through
          # the one size builder; they were dropped here, so a declared size
          # drew the 48dp default (kjui-dynamic-components-that-skip-the-
          # common-modifiers). With neither declared, the `size` shorthand or
          # the 48dp default stays as it was.
          if json_data['width'] || json_data['height'] || json_data['frame']
            modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports))
          else
            size = json_data['size'] || 48
            modifiers << ".size(#{size}.dp)"
          end

          # offset → alpha: the View slots after the size and before the
          # decoration, so the shadow, the circle, its border and background
          # move and fade with the image. They sat after the background
          # (kjui-dynamic-components-that-skip-the-common-modifiers, B2).
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))

          # Circular clip: CircleShape lives in foundation.shape (registered under
          # :circle_shape); :shape only brings RoundedCornerShape + clip helpers.
          required_imports&.add(:shape)
          required_imports&.add(:circle_shape)
          # Shadow before the clip, or the clip cuts it away; its outline is
          # the circle the image is clipped to.
          modifiers.concat(Helpers::ModifierBuilder.build_shadow(json_data, required_imports, shape: 'CircleShape'))
          modifiers << ".clip(CircleShape)"
          
          # Border for circle, through the one border builder with the circle
          # as its outline. The colour used to be written as Ruby text into
          # the Kotlin — `.border(2.dp, Helpers::ResourceResolver
          # .process_color('#FF0000', required_imports), CircleShape)` — which
          # does not compile (kjui-codegen-writes-ruby-expressions-into-kotlin).
          modifiers.concat(Helpers::ModifierBuilder.build_border(json_data, required_imports, shape: 'CircleShape'))
          
          # cornerRadius as declared, inside the circle clip above — the circle
          # stays outermost, so the result stays a circle (ruling on
          # kjui-dynamic-components-that-skip-the-common-modifiers). Border
          # first, as in build_background, so the clip does not cut it.
          modifiers.concat(Helpers::ModifierBuilder.build_corner_clip(json_data, required_imports))

          # Background (in case image doesn't load). The colour is resolved
          # here; it was the Ruby call itself, written as Kotlin text
          # (kjui-codegen-writes-ruby-expressions-into-kotlin).
          if json_data['background']
            required_imports&.add(:background)
            modifiers << ".background(#{Helpers::ResourceResolver.process_color(json_data['background'], required_imports)})"
          end
          
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
          modifiers.concat(Helpers::ModifierBuilder.build_alignment(json_data, required_imports, parent_type))

          code += Helpers::ModifierBuilder.format(modifiers, depth)
          
          # Error handling for network images
          if is_network && json_data['errorImage']
            required_imports&.add(:painter_resource)
            required_imports&.add(:r_class)
            code += ",\n" + indent("error = painterResource(R.drawable.#{Helpers::ResourceResolver.drawable_name(json_data['errorImage'])})", depth + 1)
          end
          
          code += "\n" + indent(")", depth)
          code
        end
        
        private
        
        def self.process_data_binding(text)
          return quote(text) unless text.is_a?(String)

          if (inner = Helpers::BindingExpression.extract_inner(text))
            # Value context (src): canonical parse; a `??` default becomes a
            # real Kotlin elvis on nullable properties (see BindingExpression).
            Helpers::BindingExpression.value_access(inner)
          else
            quote(text)
          end
        end
        
        # A Kotlin string literal — the one escaper (`$` included).
        def self.quote(text)
          JsonUIShared::StringLiterals.kotlin(text)
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