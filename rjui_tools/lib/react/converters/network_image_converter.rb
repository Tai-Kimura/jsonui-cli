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
          if has_binding?(content_mode)
            # A bound value matched no key and fell to the `||` fallback,
            # which built the dead class `object-@{v}`.
            #
            # Unlike Image, this does NOT route to an inline style: the
            # NetworkImage component takes `contentMode` as a PROP and derives
            # its own object-fit class from it, and NetworkImageProps has no
            # `style` at all — writing one is TS2322 on the element. The prop
            # emitted by build_content_mode_attr already carries the binding.
          elsif content_mode
            classes << content_mode_classes(content_mode)
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

          # The NetworkImageProps union ('cover' | 'contain' | 'fill' | 'none'
          # | 'scaleDown' | 'fit') is the same vocabulary object-fit takes, so
          # this reads BaseConverter's one table rather than keeping a third
          # copy. The copy it replaced was case-sensitive and had a
          # pass-the-value-through fallback, so a lowercase `aspectfill` — a
          # spelling ImageConverter accepted — reached the component as
          # `aspectfill`, outside the union.
          #
          # A bound value cannot be normalised at codegen time, and quoting it
          # handed the component the four characters `@{v}`. The normalisation
          # moves into the emitted expression, asserted through the component's
          # own prop type rather than by restating the union.
          if (expr = bound_value_expr(content_mode))
            lookup = js_object_literal(CONTENT_MODE_OBJECT_FIT)
            cast = "React.ComponentProps<typeof NetworkImage>['contentMode']"
            return " contentMode={((#{lookup})[String(#{expr}).toLowerCase()] ?? " \
                   "'#{CONTENT_MODE_DEFAULT_FIT}') as #{cast}}"
          end

          " contentMode=\"#{content_mode_prop(content_mode)}\""
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
