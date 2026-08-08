# frozen_string_literal: true

require_relative '../helpers/content_scale_helper'
require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'
# The renderingMode -> ColorFilter mapping lives on the Image converter and is
# called from here. The full suite happened to load it first, so the missing
# require only showed up running this file alone.
require_relative 'image_component'

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

          # NetworkImage uses 'source' or 'url' for image URL. An absent
          # source must be a NULL model, not "": Coil routes an empty string
          # through the request/error path (errorImage), while null selects
          # the fallback (defaultImage) — the canonical no-src state
          # (networkImage.noSrc; the dynamic component nulls empty URLs too).
          raw_source = json_data['source'] || json_data['url'] || json_data['src']
          url = raw_source.nil? ? 'null' : process_data_binding(raw_source)
          # Support 'hint' (primary), 'placeholder' and the legacy
          # 'loadingImage' spelling — all name the in-flight image.
          placeholder = json_data['hint'] || json_data['placeholder'] || json_data['loadingImage']
          content_description = json_data['contentDescription'] || 'Image'

          code = indent("AsyncImage(", depth)
          code += "\n" + indent("model = #{image_model(json_data, url, required_imports)},", depth + 1)
          code += "\n" + indent("contentDescription = \"#{content_description}\",", depth + 1)

          # Content scale (case-insensitive check). Shared vocabulary AND
          # shared default — see ContentScaleHelper. The two local quirks this
          # caller used to keep are gone: `attribute_semantics.json#image` puts
          # the default at `fit` and the positional table at all five modes.
          if json_data['contentMode']
            required_imports&.add(:content_scale)
            scale = Helpers::ContentScaleHelper.scale_expression(json_data['contentMode'])
            code += "\n" + indent("contentScale = #{scale},", depth + 1)
            alignment = Helpers::ContentScaleHelper.alignment_expression(json_data['contentMode'])
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

          # renderingMode — declared for swift and kotlin, and only Image read
          # it. `AsyncImage` takes the same `colorFilter` an `Image` does, so
          # the mapping from mode + tint to a filter stays in the Image
          # converter rather than growing a second copy: a private duplicate of
          # a shared helper is what made Label.fontFamily inert on android
          # while TextView and TextField worked (KotlinJsonUI f3bdd90).
          #
          # The spellings are read HERE and handed over explicitly, rather than
          # passing the whole node. Two reasons, both found by the coverage
          # scan refusing to see the first version: a declared attribute that
          # only a sibling component reads is invisible to a per-component
          # source scan and reads as unimplemented, and passing the node whole
          # also carried Image's `iconColor` read — a spelling declared on
          # neither Image nor common — onto NetworkImage.
          rendering = {
            'renderingMode' => json_data['renderingMode'],
            'tintColor' => json_data['tintColor']
          }
          if (filter = ImageComponent.rendering_color_filter(rendering, required_imports))
            code += "\n" + indent("colorFilter = #{filter},", depth + 1)
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
            modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports))
          end

          # clip/background (after size, before padding)
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))

          # Padding (inner spacing)
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))

          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
          modifiers.concat(Helpers::ModifierBuilder.build_alignment(json_data, required_imports, parent_type))

          code += Helpers::ModifierBuilder.format(modifiers, depth)

          # Error/fallback per the canonical state chain
          # (shared/core/attribute_semantics.json#networkImage): with no src
          # the view shows defaultImage; while loading it shows the first of
          # hint/placeholder/loadingImage; on error it shows errorImage,
          # falling back to defaultImage.
          #
          # Each Coil slot takes ONLY the images the ruling puts in its own
          # state. `fallback` is the NO-SRC slot, and it used to end in
          # `|| errorImage || placeholder`; `error` used to end in
          # `|| placeholder`. Those tails made a state image appear in a state
          # it does not belong to — every NetworkImage conformance fixture is
          # no-src (not one of the 19 declares source/url/src), so the whole
          # family rendered through `fallback`, and errorImage__static /
          # loadingImage__static / placeholder__static went visibly active
          # while hint__static — the only one declaring defaultImage — stayed
          # inert. Same rule as `semantics.border`: an image that was never
          # declared for this state does not get summoned into it, and a
          # no-src view with no defaultImage correctly shows nothing (plan 49
          # #19, C's verdict, ratified 2026-08-05).
          default_image = json_data['defaultImage']
          error_image = json_data['errorImage'] || default_image
          fallback_image = default_image
          state_args = []
          state_args << "error = painterResource(R.drawable.#{drawable_for(error_image)})" if error_image
          state_args << "fallback = painterResource(R.drawable.#{drawable_for(fallback_image)})" if fallback_image
          unless state_args.empty?
            required_imports&.add(:painter_resource)
            required_imports&.add(:r_class)
            code += ",\n" + state_args.map { |arg| indent(arg, depth + 1) }.join(",\n")
          end

          code += "\n" + indent(")", depth)
          code
        end

        private

        # Drawable identifier for a state image, with the file extension the
        # layout may carry stripped first.
        def self.drawable_for(name)
          Helpers::ResourceResolver.drawable_name(name.gsub('.png', '').gsub('.jpg', ''))
        end

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
