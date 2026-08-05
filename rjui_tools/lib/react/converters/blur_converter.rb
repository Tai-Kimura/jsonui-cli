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
          # An explicit radius or intensity wins; otherwise the material's own
          # default (BaseConverter::EFFECT_STYLE_BLUR_PX — the same table the
          # common spelling reads, so Blur and a plain View cannot disagree).
          return attributes['blurRadius'] if attributes['blurRadius']
          return (attributes['intensity'] * 20).round if attributes['intensity']

          effect_style_blur_px(get_effect_style)
        end

        def get_background_color
          effect_style_background(get_effect_style)
        end

        def get_effect_style
          # `effectStyle` only. The `json['style']` fallback used to be here was
          # reading `common.style` — the STYLE FILE name — so a Blur inside a
          # styled screen matched its style-file reference against blur
          # appearances. sjui had the same misread and no `effectStyle` read at
          # all.
          effect_style_key
        end
      end
    end
  end
end
