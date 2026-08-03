# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'

module KjuiTools
  module Compose
    module Components
      class NetworkImageComponent
        # `headers` — HTTP headers for the image request. A plain String model has
        # nowhere to put them, so the URL becomes a built ImageRequest instead.
        #
        # Coil 3 moved these off the request builder: `addHeader` was Coil 2, and
        # the current API is `httpHeaders(NetworkHeaders)` from coil3.network.
        # (The attribute's own description still named the old one; corrected.)
        def self.image_model(json_data, url, required_imports)
          headers = json_data['headers']
          return url unless headers.is_a?(Hash) && headers.any?

          required_imports&.add(:image_request)
          required_imports&.add(:network_headers)
          required_imports&.add(:local_context)
          pairs = headers.map { |key, value| ".add(#{quote(key.to_s)}, #{quote(value.to_s)})" }
          "ImageRequest.Builder(LocalContext.current).data(#{url})" \
            ".httpHeaders(NetworkHeaders.Builder()#{pairs.join}.build()).build()"
        end

        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          required_imports&.add(:async_image)

          # NetworkImage uses 'source' or 'url' for image URL
          url = process_data_binding(json_data['source'] || json_data['url'] || json_data['src'] || '')
          # Support 'hint' (primary), 'placeholder' and the legacy
          # 'loadingImage' spelling — all name the in-flight image.
          placeholder = json_data['hint'] || json_data['placeholder'] || json_data['loadingImage']
          content_description = json_data['contentDescription'] || 'Image'

          code = indent("AsyncImage(", depth)
          code += "\n" + indent("model = #{image_model(json_data, url, required_imports)},", depth + 1)
          code += "\n" + indent("contentDescription = \"#{content_description}\",", depth + 1)

          # Content scale (case-insensitive check)
          if json_data['contentMode']
            required_imports&.add(:content_scale)
            mode = json_data['contentMode'].to_s.downcase
            scale = case mode
            when 'aspectfit'
              'ContentScale.Fit'
            when 'aspectfill'
              'ContentScale.Crop'
            when 'fill', 'scaletofill'
              'ContentScale.FillBounds'
            when 'center', 'top', 'bottom', 'left', 'right'
              # Positional modes draw unscaled and aligned (UIKit contentMode
              # positions — mirrors the dynamic component).
              'ContentScale.None'
            else
              'ContentScale.Fit'
            end
            code += "\n" + indent("contentScale = #{scale},", depth + 1)
            alignment = {
              'top' => 'Alignment.TopCenter', 'bottom' => 'Alignment.BottomCenter',
              'left' => 'Alignment.CenterStart', 'right' => 'Alignment.CenterEnd'
            }[mode]
            if alignment
              required_imports&.add(:alignment)
              code += "\n" + indent("alignment = #{alignment},", depth + 1)
            end
          end

          # Placeholder
          if placeholder
            required_imports&.add(:painter_resource)
            required_imports&.add(:r_class)
            code += "\n" + indent("placeholder = painterResource(R.drawable.#{Helpers::ResourceResolver.drawable_name(placeholder)}),", depth + 1)
          end

          # Build modifiers
          # Compose Modifier order (top to bottom = outer to inner):
          # 1. margins (outer spacing)
          # 2. size
          # 3. clip/background
          # 4. padding (inner spacing)
          modifiers = []

          # Add testTag and contentDescription for UI testing
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))

          # Margins first (outer spacing, before size)
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))

          # Size
          if json_data['size']
            modifiers << ".size(#{json_data['size']}.dp)"
          else
            modifiers.concat(Helpers::ModifierBuilder.build_size(json_data))
          end

          # clip/background (after size, before padding)
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))

          # Padding (inner spacing)
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))

          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
          modifiers.concat(Helpers::ModifierBuilder.build_alignment(json_data, required_imports, parent_type))

          code += Helpers::ModifierBuilder.format(modifiers, depth)

          # Error/fallback per the canonical no-src chain
          # (networkImage.noSrc = defaultImage, shared/core/
          # attribute_semantics.json): with no src the view shows
          # defaultImage; on error it shows errorImage, falling back to
          # defaultImage. defaultImage was previously never read here —
          # a Collection control declaring only defaultImage rendered blank.
          default_image = json_data['defaultImage']
          error_image = json_data['errorImage'] || default_image || placeholder
          fallback_image = default_image || json_data['errorImage'] || placeholder
          if error_image || fallback_image
            required_imports&.add(:painter_resource)
            required_imports&.add(:r_class)
            error_name = error_image.gsub('.png', '').gsub('.jpg', '')
            fallback_name = fallback_image.gsub('.png', '').gsub('.jpg', '')
            code += ",\n" + indent("error = painterResource(R.drawable.#{Helpers::ResourceResolver.drawable_name(error_name)}),", depth + 1)
            code += "\n" + indent("fallback = painterResource(R.drawable.#{Helpers::ResourceResolver.drawable_name(fallback_name)})", depth + 1)
          end

          code += "\n" + indent(")", depth)
          code
        end

        private

        def self.process_data_binding(text)
          return quote(text) unless text.is_a?(String)

          if (inner = Helpers::BindingExpression.extract_inner(text))
            # Value context (src): canonical parse; a `??` default becomes a
            # real Kotlin elvis on nullable properties. With no default, the
            # plain (possibly null) access is emitted — AsyncImage's null
            # model is the attribute-default behavior.
            Helpers::BindingExpression.value_access(inner)
          else
            quote(text)
          end
        end

        # A Kotlin string literal: a backslash, a quote and a `$` all need
        # escaping — an unescaped `$` opens a string template. Block form on
        # purpose: gsub's replacement string treats backslashes specially, which
        # is how the first cut of this silently dropped the `$` case.
        def self.quote(text)
          escaped = text.to_s.gsub(/[\\"$]/) { |char| "\\#{char}" }
          "\"#{escaped}\""
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
