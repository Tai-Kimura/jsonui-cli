# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class CircleViewConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          style_attr = build_circle_style
          children = convert_children(indent)
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr
          onclick_attr = build_onclick_attr

          jsx = if children.empty?
            "#{indent_str(indent)}<div#{id_attr} className=\"#{class_name}\"#{style_attr}#{onclick_attr}#{testid_attr}#{tag_attr} />"
          else
            <<~JSX.chomp
              #{indent_str(indent)}<div#{id_attr} className="#{class_name}"#{style_attr}#{onclick_attr}#{testid_attr}#{tag_attr}>
              #{children}
              #{indent_str(indent)}</div>
            JSX
          end

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]

          # Make it circular
          classes << 'rounded-full'

          # Overflow hidden to clip children
          classes << 'overflow-hidden'

          # Flex for centering content
          classes << 'flex items-center justify-center' if json['child'] || json['children']

          # Cursor pointer for clickable items
          classes << 'cursor-pointer' if json['onClick'] || json['onclick']

          classes.compact.reject(&:empty?).join(' ')
        end

        def build_circle_style
          style_parts = []

          # Fill color (takes precedence over background for circle)
          fill_color = json['fillColor'] || json['background'] || json['backgroundColor']
          if fill_color
            if has_binding?(fill_color)
              binding_expr = convert_binding(fill_color).gsub(/^\{|\}$/, '')
              style_parts << "backgroundColor: #{binding_expr}"
            else
              style_parts << "backgroundColor: '#{fill_color}'"
            end
          end

          # Border/Stroke
          stroke_color = json['strokeColor'] || json['borderColor']
          stroke_width = json['strokeWidth'] || json['borderWidth']
          stroke_style = json['borderStyle'] || 'solid'

          if stroke_color || stroke_width
            stroke_width ||= 1
            stroke_color ||= '#000000'
            style_parts << "border: '#{stroke_width}px #{stroke_style} #{stroke_color}'"
          end

          # Shadow
          shadow = json['shadow']
          if shadow.is_a?(Hash)
            shadow_color = shadow['color'] || 'rgba(0,0,0,0.25)'
            shadow_x = shadow['x'] || shadow['offsetX'] || 0
            shadow_y = shadow['y'] || shadow['offsetY'] || 2
            shadow_blur = shadow['blur'] || shadow['radius'] || 4
            style_parts << "boxShadow: '#{shadow_x}px #{shadow_y}px #{shadow_blur}px #{shadow_color}'"
          end

          return build_style_attr if style_parts.empty?

          existing_style = build_style_attr
          if existing_style.empty?
            " style={{ #{style_parts.join(', ')} }}"
          else
            existing_style.sub(/\}\}$/, ", #{style_parts.join(', ')} }}")
          end
        end
      end
    end
  end
end
