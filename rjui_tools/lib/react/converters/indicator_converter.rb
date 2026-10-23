# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class IndicatorConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          # before the style: a bound colour puts its custom property there
          spinner_class = build_spinner_class
          style_attr = build_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr

          jsx = <<~JSX.chomp
            #{indent_str(indent)}<div#{id_attr}#{class_name_attr(class_name)}#{style_attr}#{testid_attr}#{tag_attr}>
            #{indent_str(indent + 2)}<div className="#{spinner_class}" />
            #{indent_str(indent)}</div>
          JSX

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]

          classes << 'inline-flex items-center justify-center'

          finalize_classes(classes)
        end

        def build_spinner_class
          classes = []

          # The spinner's size: a declared length on both axes, else the
          # medium spinner. wrapContent / matchParent are not lengths (they
          # were written as `w-[wrapContentpx]`, a class Tailwind does not
          # have). A legacy `size` never arrives here: the layout normalizer
          # folds it into width / height on every platform.
          width = attributes['width']
          height = attributes['height']

          if length?(width) && length?(height)
            classes << "w-[#{width}px]"
            classes << "h-[#{height}px]"
          else
            classes << 'w-6 h-6'
          end

          # Spinner animation
          classes << 'animate-spin'
          classes << 'rounded-full'

          # Border width
          border_width = attributes['strokeWidth'] || attributes['borderWidth'] || 2
          classes << "border-#{border_width}"

          classes << 'border-transparent'

          # Color
          color = attributes['color'] || attributes['tintColor'] || '#3B82F6'
          if has_binding?(color)
            # A bound colour rides a custom property on the outer element,
            # inherited by the spinner; as a class name it was `border-t-@{…}`.
            @dynamic_styles['--jui-indicator-color'] = color_style_expr(color)
            classes << 'border-t-[color:var(--jui-indicator-color)]'
            classes << 'border-r-[color:var(--jui-indicator-color)]' if attributes['halfSpinner']
          elsif color.start_with?('#')
            classes << "border-t-[#{color}]"
            classes << "border-r-[#{color}]" if attributes['halfSpinner']
          else
            classes << "border-t-#{color}"
            classes << "border-r-#{color}" if attributes['halfSpinner']
          end

          classes.join(' ')
        end

        def length?(value)
          value.is_a?(Numeric) || value.to_s.match?(/\A\d+(\.\d+)?\z/)
        end
      end
    end
  end
end
