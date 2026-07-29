# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class BlurConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          style_attr = build_blur_style
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

          # Corner radius
          corner_radius = attributes['cornerRadius']
          classes << "rounded-[#{corner_radius}px]" if corner_radius

          # Overflow hidden for corner radius
          classes << 'overflow-hidden' if corner_radius

          # Cursor pointer for clickable items
          classes << 'cursor-pointer' if attributes['onClick'] || attributes['onclick']

          finalize_classes(classes)
        end

        def build_blur_style
          style_parts = []

          # Get backdrop filter blur
          blur_amount = get_blur_amount
          style_parts << "backdropFilter: 'blur(#{blur_amount}px)'"
          style_parts << "WebkitBackdropFilter: 'blur(#{blur_amount}px)'" # Safari support

          # Get background color based on effect style
          bg_color = attributes['backgroundColor'] || get_background_color
          style_parts << "backgroundColor: '#{bg_color}'" if bg_color

          existing_style = build_style_attr
          if existing_style.empty?
            " style={{ #{style_parts.join(', ')} }}"
          else
            existing_style.sub(/\}\}$/, ", #{style_parts.join(', ')} }}")
          end
        end

        def get_blur_amount
          # Use blurRadius if provided directly
          return attributes['blurRadius'] if attributes['blurRadius']

          # Use intensity if provided (0.0 to 1.0 mapped to 0 to 20px)
          if attributes['intensity']
            (attributes['intensity'] * 20).round
          else
            # Default blur based on effect style
            case get_effect_style
            when 'ultrathin', 'systemultrathinmaterial'
              4
            when 'thin', 'systemthinmaterial'
              8
            when 'regular', 'systemmaterial'
              12
            when 'thick', 'systemthickmaterial'
              16
            when 'chrome', 'systemchromematerial'
              20
            else
              10 # default
            end
          end
        end

        def get_background_color
          style = get_effect_style

          case style
          when 'light', 'extralight'
            'rgba(255, 255, 255, 0.7)'
          when 'dark'
            'rgba(0, 0, 0, 0.5)'
          when 'ultrathin', 'systemultrathinmaterial'
            'rgba(255, 255, 255, 0.3)'
          when 'thin', 'systemthinmaterial'
            'rgba(255, 255, 255, 0.5)'
          when 'regular', 'systemmaterial'
            'rgba(255, 255, 255, 0.7)'
          when 'thick', 'systemthickmaterial'
            'rgba(255, 255, 255, 0.85)'
          when 'chrome', 'systemchromematerial'
            'rgba(255, 255, 255, 0.9)'
          when 'prominent'
            'rgba(240, 240, 240, 0.8)'
          else
            'rgba(255, 255, 255, 0.6)'
          end
        end

        def get_effect_style
          # `effectStyle` only. The `json['style']` fallback used to be here was
          # reading `common.style` — the STYLE FILE name — so a Blur inside a
          # styled screen matched its style-file reference against blur
          # appearances. sjui had the same misread and no `effectStyle` read at
          # all.
          attributes['effectStyle'].to_s.downcase.gsub(/\s+/, '').then { |v| v.empty? ? 'regular' : v }
        end
      end
    end
  end
end
