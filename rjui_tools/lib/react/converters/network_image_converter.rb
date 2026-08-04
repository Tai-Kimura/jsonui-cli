# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class NetworkImageConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          style_attr = build_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr

          src = build_src_attr
          content_mode = build_content_mode_attr
          placeholder_attr = build_placeholder_attr
          error_image = attributes['errorImage'] ? " errorImage=\"#{attributes['errorImage']}\"" : ''

          # Build event handlers
          on_load = build_event_handler('onLoad')
          on_error = build_event_handler('onError')
          onclick_attr = build_onclick_attr

          # Corner radius
          corner_radius_style = build_corner_radius_style

          jsx = <<~JSX.chomp
            #{indent_str(indent)}<NetworkImage#{id_attr} className="#{class_name}"#{src}#{content_mode}#{placeholder_attr}#{error_image}#{build_alt_attr}#{loading_attr}#{on_load}#{on_error}#{onclick_attr}#{corner_radius_style}#{style_attr}#{testid_attr}#{tag_attr} />
          JSX

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]

          # Content mode to object-fit. Keys cover the canonical
          # attribute_definitions enum (fit/fill/center/top/... /AspectFit)
          # plus the iOS/Android long forms. Canonical semantics:
          # shared/core/attribute_semantics.json — fill = stretch
          # (scaleToFill synonym), AspectFill is the crop.
          content_mode = attributes['contentMode'] || attributes['scaleType']
          if apply_bound_content_mode(content_mode)
            # A bound value matched no key and fell to the `||` fallback,
            # which built the dead class `object-@{v}`. object-fit /
            # object-position are owned by the inline style instead.
          elsif content_mode
            mode_map = {
              'fit' => 'object-contain',
              'fill' => 'object-fill',
              'center' => 'object-none object-center',
              'Center' => 'object-none object-center',
              'top' => 'object-none object-top',
              'bottom' => 'object-none object-bottom',
              'left' => 'object-none object-left',
              'right' => 'object-none object-right',
              'scaleAspectFill' => 'object-cover',
              'scaleAspectFit' => 'object-contain',
              'scaleToFill' => 'object-fill',
              'centerCrop' => 'object-cover',
              'fitCenter' => 'object-contain',
              'fitXY' => 'object-fill',
              'AspectFill' => 'object-cover',
              'AspectFit' => 'object-contain'
            }
            classes << (mode_map[content_mode] || "object-#{content_mode}")
          end

          # Circle image
          classes << 'rounded-full' if attributes['circle'] || attributes['circleImage']

          # Corner radius class (if using Tailwind standard values). A bound
          # radius is already an inline `borderRadius` from the base pass;
          # this arbitrary-value class would only restate it as dead text.
          corner_radius = attributes['cornerRadius']
          if corner_radius && !has_binding?(corner_radius) && !attributes['circle'] && !attributes['circleImage']
            classes << "rounded-[#{corner_radius}px]"
          end

          # Clickable
          classes << 'cursor-pointer' if attributes['canTap'] || attributes['onClick'] || attributes['onclick']

          finalize_classes(classes)
        end

        def build_src_attr
          src = attributes['src'] || attributes['url'] || attributes['imageUrl']
          return '' unless src

          if has_binding?(src)
            " src={#{convert_binding(src).gsub(/^\{|\}$/, '')}}"
          else
            " src=\"#{src}\""
          end
        end

        def build_content_mode_attr
          content_mode = attributes['contentMode'] || attributes['scaleType']
          return '' unless content_mode

          # Normalize the canonical enum (fit/fill/center/top/.../AspectFit)
          # and the iOS/Android long forms into the NetworkImageProps union
          # ('cover' | 'contain' | 'fill' | 'none' | 'scaleDown') — the
          # template contract must accept every value emitted here.
          # fill = stretch per shared/core/attribute_semantics.json.
          mode_map = {
            'fit' => 'contain',
            'fill' => 'fill',
            'center' => 'none',
            'Center' => 'none',
            'top' => 'none',
            'bottom' => 'none',
            'left' => 'none',
            'right' => 'none',
            'scaleAspectFill' => 'cover',
            'scaleAspectFit' => 'contain',
            'scaleToFill' => 'fill',
            'centerCrop' => 'cover',
            'fitCenter' => 'contain',
            'fitXY' => 'fill',
            'AspectFill' => 'cover',
            'AspectFit' => 'contain'
          }

          # A bound value cannot be normalised at codegen time, and quoting it
          # handed the component the four characters `@{v}` — outside the
          # NetworkImageProps union, so the prop was simply wrong. The
          # normalisation moves into the emitted expression.
          if (expr = bound_value_expr(content_mode))
            lookup = js_object_literal(mode_map.transform_keys(&:downcase))
            return " contentMode={(#{lookup})[String(#{expr}).toLowerCase()] ?? 'contain'}"
          end

          mapped_mode = mode_map[content_mode] || content_mode
          " contentMode=\"#{mapped_mode}\""
        end

        # Native lazy/eager fetch hint, forwarded to the underlying <img>.
        def loading_attr
          loading = attributes['loading'].to_s.downcase
          return '' unless %w[lazy eager].include?(loading)

          " loading=\"#{loading}\""
        end

        def build_placeholder_attr
          # `hint` is the canonical spelling; `placeholder` and `loadingImage`
          # are the loading-state chain. defaultImage is NOT part of it —
          # it is the no-src display and travels as its own prop (canonical
          # networkImage.noSrc = defaultImage, shared/core/
          # attribute_semantics.json); collapsing it into placeholder let a
          # declared placeholder hijack the no-src state.
          placeholder = attributes['hint'] || attributes['placeholder'] || attributes['loadingImage']
          attr = ''
          if placeholder
            attr +=
              if has_binding?(placeholder)
                " placeholder={#{convert_binding(placeholder).gsub(/^\{|\}$/, '')}}"
              else
                " placeholder=\"#{placeholder}\""
              end
          end
          default_image = attributes['defaultImage']
          if default_image && !has_binding?(default_image)
            attr += " defaultImage=\"#{default_image}\""
          end
          attr
        end

        def build_event_handler(event_name)
          handler = json[event_name]
          return '' unless handler

          if has_binding?(handler)
            " #{event_name}={#{extract_binding_property(handler)}}"
          else
            " #{event_name}={#{handler}}"
          end
        end

        def build_corner_radius_style
          corner_radius = attributes['cornerRadius']
          return '' unless corner_radius && !attributes['circle'] && !attributes['circleImage']

          # Already handled in className
          ''
        end
      end
    end
  end
end
