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
          alt = json['alt'] || json['accessibilityLabel'] || ''
          content_mode = build_content_mode_attr
          placeholder_attr = build_placeholder_attr
          error_image = json['errorImage'] ? " errorImage=\"#{json['errorImage']}\"" : ''

          # Build event handlers
          on_load = build_event_handler('onLoad')
          on_error = build_event_handler('onError')
          onclick_attr = build_onclick_attr

          # Corner radius
          corner_radius_style = build_corner_radius_style

          jsx = <<~JSX.chomp
            #{indent_str(indent)}<NetworkImage#{id_attr} className="#{class_name}"#{src}#{content_mode}#{placeholder_attr}#{error_image} alt="#{alt}"#{on_load}#{on_error}#{onclick_attr}#{corner_radius_style}#{style_attr}#{testid_attr}#{tag_attr} />
          JSX

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]

          # Content mode to object-fit
          content_mode = json['contentMode'] || json['scaleType']
          if content_mode
            mode_map = {
              'scaleAspectFill' => 'object-cover',
              'scaleAspectFit' => 'object-contain',
              'scaleToFill' => 'object-fill',
              'center' => 'object-none',
              'centerCrop' => 'object-cover',
              'fitCenter' => 'object-contain',
              'fitXY' => 'object-fill',
              'AspectFill' => 'object-cover',
              'AspectFit' => 'object-contain'
            }
            classes << (mode_map[content_mode] || "object-#{content_mode}")
          end

          # Circle image
          classes << 'rounded-full' if json['circle'] || json['circleImage']

          # Corner radius class (if using Tailwind standard values)
          corner_radius = json['cornerRadius']
          if corner_radius && !json['circle'] && !json['circleImage']
            classes << "rounded-[#{corner_radius}px]"
          end

          # Clickable
          classes << 'cursor-pointer' if json['canTap'] || json['onClick'] || json['onclick']

          classes.compact.reject(&:empty?).join(' ')
        end

        def build_src_attr
          src = json['src'] || json['url'] || json['imageUrl']
          return '' unless src

          if has_binding?(src)
            " src={#{convert_binding(src).gsub(/^\{|\}$/, '')}}"
          else
            " src=\"#{src}\""
          end
        end

        def build_content_mode_attr
          content_mode = json['contentMode'] || json['scaleType']
          return '' unless content_mode

          mode_map = {
            'scaleAspectFill' => 'cover',
            'scaleAspectFit' => 'contain',
            'scaleToFill' => 'fill',
            'center' => 'none',
            'centerCrop' => 'cover',
            'fitCenter' => 'contain',
            'fitXY' => 'fill',
            'AspectFill' => 'cover',
            'AspectFit' => 'contain'
          }

          mapped_mode = mode_map[content_mode] || content_mode
          " contentMode=\"#{mapped_mode}\""
        end

        def build_placeholder_attr
          placeholder = json['placeholder'] || json['defaultImage']
          return '' unless placeholder

          if has_binding?(placeholder)
            " placeholder={#{convert_binding(placeholder).gsub(/^\{|\}$/, '')}}"
          else
            " placeholder=\"#{placeholder}\""
          end
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
          corner_radius = json['cornerRadius']
          return '' unless corner_radius && !json['circle'] && !json['circleImage']

          # Already handled in className
          ''
        end
      end
    end
  end
end
