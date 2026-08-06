# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class ImageConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          style_attr = build_style_attr
          src = build_src
          id_attr = build_id_attr
          onclick_attr = build_onclick_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr

          # Build src attribute
          src_attr = if src.start_with?('`')
                       " src={#{src}}"
                     elsif src.include?('{')
                       " src={#{src.gsub(/[{}]/, '')}}"
                     else
                       " src=\"#{src}\""
                     end

          jsx = "#{indent_str(indent)}<img#{id_attr} className=\"#{class_name}\"#{style_attr}#{src_attr}#{build_alt_attr}#{loading_attr}#{onclick_attr}#{testid_attr}#{tag_attr} />"

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_src
          # Priority: srcName > src > url > defaultImage
          if attributes['srcName']
            if has_binding?(attributes['srcName'])
              binding_prop = extract_binding_property(attributes['srcName'])
              "`/images/${#{binding_prop}}`"
            else
              "/images/#{resolve_image_extension(attributes['srcName'])}"
            end
          elsif attributes['src']
            convert_src_value(attributes['src'], 'src')
          elsif attributes['url']
            convert_src_value(attributes['url'], 'url')
          elsif attributes['defaultImage']
            "/images/#{resolve_image_extension(attributes['defaultImage'])}"
          else
            '/images/placeholder.png'
          end
        end

        # Convert a src/url value WITHOUT the string-table resolution that
        # convert_binding applies: an image source that happens to match a
        # strings.json key would silently become UI text ("閉じる") the
        # moment someone registers the key — the img breaks with no warning
        # (rjui-image-src-bare-name-string-key-collision). Bindings resolve
        # as usual; bare names get a build warning steering to srcName.
        def convert_src_value(value, attr_name)
          return convert_binding(value) if has_binding?(value)
          return value unless value.is_a?(String)

          if bare_image_name?(value)
            if convert_string_key(value)
              Core::Logger.warn(
                "Image #{attr_name} '#{value}' collides with a strings.json key — " \
                "#{attr_name} is never resolved through the string table; " \
                "use srcName for named images (emitting the literal as-is)"
              )
            else
              Core::Logger.warn(
                "Image #{attr_name} '#{value}' is a bare name (no path/extension/scheme) — " \
                'named images should use srcName so the /images/ path and extension resolve'
              )
            end
          end

          convert_text_with_newlines(value)
        end

        # A "bare name" carries no path, extension, or scheme — it cannot
        # `loading` — the native lazy/eager fetch hint, passed through
        # unchanged when it is one of the two values the browser knows.
        def loading_attr
          loading = attributes['loading'].to_s.downcase
          return '' unless %w[lazy eager].include?(loading)

          " loading=\"#{loading}\""
        end

        # resolve as an <img> src and is almost certainly a srcName typo.
        def bare_image_name?(value)
          !value.empty? &&
            !value.include?('/') &&
            !value.include?('.') &&
            !value.start_with?('http', 'data:')
        end


        def build_class_name
          classes = [super]

          # Content mode (canonical enum: fit/fill/center/top/... plus the
          # iOS long forms — see attribute_definitions Image.contentMode).
          # Canonical semantics live in shared/core/attribute_semantics.json:
          # fill = stretch (scaleToFill synonym — AspectFill is the crop),
          # and the default is fit (image.defaultContentMode), both verified
          # by `jui conformance gate --cross-effect`.
          # A bound value has no spelling to match, so it fell straight
          # through to the `else` and every binding froze on object-contain.
          # It routes to the CSS pair instead (BaseConverter's shared table).
          unless apply_bound_content_mode(attributes['contentMode'])
            classes << content_mode_classes(attributes['contentMode'])
          end

          # CircleImage type
          if json['type'] == 'CircleImage'
            classes << 'rounded-full'
          end

          # Clickable cursor
          if attributes['canTap'] || attributes['onclick'] || attributes['onClick']
            classes << 'cursor-pointer'
          end

          finalize_classes(classes)
        end

        def build_style_attr
          super

          # Corner radius (for non-circle images). A bound one is already in
          # `borderRadius` from the base pass; re-writing it here would put
          # the characters `@{v}` back into the style.
          corner_radius = attributes['cornerRadius']
          if corner_radius && !has_binding?(corner_radius) && json['type'] != 'CircleImage'
            @dynamic_styles['borderRadius'] = "'#{corner_radius}px'"
          end

          # One renderer for every converter (BaseConverter#style_attr_for):
          # the SPREAD sentinel and the `React.CSSProperties` assertion a
          # custom-property key needs are handled in ONE place.
          style_attr_for(@dynamic_styles)
        end

        def build_onclick_attr
          return '' unless attributes['canTap'] || attributes['onclick'] || attributes['onClick']

          onclick = attributes['onclick'] || attributes['onClick']
          return '' unless onclick

          # The array face first: `end_with?` on an Array is a NoMethodError
          # (the exact crash kjui's get_event_handler_call had), so the whole
          # generation died on a declaration the SSoT allows.
          if onclick.is_a?(Array)
            expr = onclick_selector_expr(onclick)
            return expr ? " onClick={#{expr}}" : ''
          end

          if onclick.end_with?(':')
            # Selector format: "methodName:"
            method_name = onclick.chomp(':')
            " onClick={() => #{method_name}(this)}"
          elsif has_binding?(onclick)
            # Binding format: "@{functionName}"
            handler = extract_binding_property(onclick)
            " onClick={#{handler}}"
          else
            " onClick={#{onclick}}"
          end
        end
      end
    end
  end
end
