# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class IconLabelConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          style_attr = build_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr
          onclick_attr = build_onclick_attr

          text = convert_binding(json['text'] || '')
          icon_position = (json['iconPosition'] || 'Left').downcase
          icon_src = get_icon_src
          icon_style = build_icon_style

          # Determine flex direction based on icon position
          flex_direction = case icon_position
                          when 'top' then 'flex-col'
                          when 'bottom' then 'flex-col-reverse'
                          when 'right' then 'flex-row-reverse'
                          else 'flex-row' # left is default
                          end

          icon_element = if icon_src.include?('{')
            "<img className=\"#{icon_style}\" src={#{icon_src.gsub(/[{}]/, '')}} alt=\"\" />"
          else
            "<img className=\"#{icon_style}\" src=\"#{icon_src}\" alt=\"\" />"
          end

          text_style = build_text_style
          text_element = "<span className=\"#{build_text_class_name}\"#{text_style}>#{text}</span>"

          jsx = <<~JSX.chomp
            #{indent_str(indent)}<div#{id_attr} className="#{class_name} flex #{flex_direction} items-center"#{style_attr}#{onclick_attr}#{testid_attr}#{tag_attr}>
            #{indent_str(indent + 2)}#{icon_element}
            #{indent_str(indent + 2)}#{text_element}
            #{indent_str(indent)}</div>
          JSX

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]

          # Cursor pointer for clickable items
          classes << 'cursor-pointer' if json['onClick'] || json['onclick']

          classes.compact.reject(&:empty?).join(' ')
        end

        def build_text_class_name
          classes = []

          # Font size
          classes << TailwindMapper.map_font_size(json['fontSize']) if json['fontSize']

          # Font weight
          classes << TailwindMapper.map_font_weight(json['fontWeight']) if json['fontWeight']

          # Font color
          if json['fontColor'] && !has_binding?(json['fontColor'])
            classes << TailwindMapper.map_color(json['fontColor'], 'text')
          end

          # Text decoration
          classes << 'underline' if json['underline']
          classes << 'line-through' if json['strikethrough']

          classes.compact.reject(&:empty?).join(' ')
        end

        def build_text_style
          style_parts = []

          # Dynamic font color
          if json['fontColor'] && has_binding?(json['fontColor'])
            binding_expr = convert_binding(json['fontColor']).gsub(/^\{|\}$/, '')
            style_parts << "color: #{binding_expr}"
          end

          return '' if style_parts.empty?

          " style={{ #{style_parts.join(', ')} }}"
        end

        def get_icon_src
          # Support selected state with icon_on/icon_off
          if json['selected'] && has_binding?(json['selected'])
            binding_expr = extract_binding_property(json['selected'])
            icon_on = json['icon_on'] || json['iconOn'] || ''
            icon_off = json['icon_off'] || json['iconOff'] || ''
            "{#{binding_expr} ? '#{icon_on}' : '#{icon_off}'}"
          else
            json['icon_off'] || json['iconOff'] || json['icon_on'] || json['iconOn'] || json['icon'] || ''
          end
        end

        def build_icon_style
          classes = []

          # Icon size
          icon_size = json['iconSize']
          if icon_size.is_a?(Array) && icon_size.length >= 2
            width = icon_size[0]
            height = icon_size[1]
            classes << "w-[#{width}px]" if width
            classes << "h-[#{height}px]" if height
          elsif icon_size.is_a?(Numeric)
            classes << "w-[#{icon_size}px]"
            classes << "h-[#{icon_size}px]"
          end

          # Icon margin
          icon_position = (json['iconPosition'] || 'Left').downcase
          margin = json['iconMargin'] || json['spacing'] || 4
          margin_class = case icon_position
                        when 'top' then "mb-[#{margin}px]"
                        when 'bottom' then "mt-[#{margin}px]"
                        when 'right' then "ml-[#{margin}px]"
                        else "mr-[#{margin}px]" # left is default
                        end
          classes << margin_class

          # Icon tint color (for SVG)
          tint_color = json['iconTintColor'] || json['tintColor']
          # Note: CSS filter or mix-blend-mode would be needed for actual color tinting

          classes.compact.reject(&:empty?).join(' ')
        end
      end
    end
  end
end
