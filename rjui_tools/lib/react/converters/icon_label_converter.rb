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

          text = convert_text_binding(attributes['text'] || '')
          icon_position = (attributes['iconPosition'] || 'Left').downcase
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
          classes << 'cursor-pointer' if attributes['onClick'] || attributes['onclick']

          finalize_classes(classes)
        end

        def build_text_class_name
          classes = []

          # Font size
          classes << TailwindMapper.map_font_size(attributes['fontSize']) if attributes['fontSize']

          # Font weight
          classes << TailwindMapper.map_font_weight(attributes['fontWeight']) if attributes['fontWeight']

          # Font color
          if attributes['selected'] == true && attributes['selectedFontColor']
            # Statically selected: the selected colour IS the colour.
            classes << TailwindMapper.map_color(attributes['selectedFontColor'], 'text')
          elsif attributes['fontColor'] && !has_binding?(attributes['fontColor'])
            classes << TailwindMapper.map_color(attributes['fontColor'], 'text')
          end

          # Text decoration
          classes << 'underline' if attributes['underline']
          classes << 'line-through' if attributes['strikethrough']

          finalize_classes(classes)
        end

        def build_text_style
          style_parts = []

          # selectedFontColor with a bound selected state: the colour follows
          # the selection at runtime — same swap the icon does in get_icon_src.
          if attributes['selectedFontColor'] && attributes['selected'] &&
             has_binding?(attributes['selected'])
            selected_expr = extract_binding_property(attributes['selected'])
            base_color = attributes['fontColor'] && !has_binding?(attributes['fontColor']) ? attributes['fontColor'] : nil
            fallback = base_color ? "'#{base_color}'" : 'undefined'
            style_parts << "color: #{selected_expr} ? '#{attributes['selectedFontColor']}' : #{fallback}"
          elsif attributes['fontColor'] && has_binding?(attributes['fontColor'])
            binding_expr = convert_binding(attributes['fontColor']).gsub(/^\{|\}$/, '')
            style_parts << "color: #{binding_expr}"
          end

          # textShadow — same canonical object contract as Label.
          shadow = attributes['textShadow']
          if shadow.is_a?(Hash) && shadow['color'] && shadow['blur'] && shadow['offset'].is_a?(Array)
            css_color = shadow['color'].to_s.start_with?('#') ? shadow['color'] : "var(--color-#{shadow['color']})"
            style_parts << "textShadow: '#{shadow['offset'][0]}px #{shadow['offset'][1]}px #{shadow['blur']}px #{css_color}'"
          elsif shadow.is_a?(String) && !shadow.empty?
            style_parts << "textShadow: '#{shadow}'"
          end

          return '' if style_parts.empty?

          " style={{ #{style_parts.join(', ')} }}"
        end

        def get_icon_src
          # Support selected state with icon_on/icon_off
          if attributes['selected'] && has_binding?(attributes['selected'])
            binding_expr = extract_binding_property(attributes['selected'])
            icon_on = attributes['icon_on'] || attributes['iconOn'] || ''
            icon_off = attributes['icon_off'] || attributes['iconOff'] || ''
            "{#{binding_expr} ? '#{icon_on}' : '#{icon_off}'}"
          else
            attributes['icon_off'] || attributes['iconOff'] || attributes['icon_on'] || attributes['iconOn'] || attributes['icon'] || ''
          end
        end

        def build_icon_style
          classes = []

          # Icon size
          icon_size = attributes['iconSize']
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
          icon_position = (attributes['iconPosition'] || 'Left').downcase
          # 5 is the cross-platform canonical default (IconLabelView.swift and
          # both mobile dynamic converters) — 4 was an rjui-only deviation.
          margin = attributes['iconMargin'] || attributes['spacing'] || 5
          margin_class = case icon_position
                        when 'top' then "mb-[#{margin}px]"
                        when 'bottom' then "mt-[#{margin}px]"
                        when 'right' then "ml-[#{margin}px]"
                        else "mr-[#{margin}px]" # left is default
                        end
          classes << margin_class

          # Icon tint color (for SVG)
          tint_color = attributes['iconTintColor'] || attributes['tintColor']
          # Note: CSS filter or mix-blend-mode would be needed for actual color tinting

          finalize_classes(classes)
        end
      end
    end
  end
end
