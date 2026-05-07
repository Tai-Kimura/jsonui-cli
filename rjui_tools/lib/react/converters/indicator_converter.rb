# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class IndicatorConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          style_attr = build_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr

          jsx = <<~JSX.chomp
            #{indent_str(indent)}<div#{id_attr} className="#{class_name}"#{style_attr}#{testid_attr}#{tag_attr}>
            #{indent_str(indent + 2)}<div className="#{build_spinner_class}" />
            #{indent_str(indent)}</div>
          JSX

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]

          classes << 'inline-flex items-center justify-center'

          classes.compact.reject(&:empty?).join(' ')
        end

        def build_spinner_class
          classes = []

          # Size from width/height or size string
          width = json['width']
          height = json['height']
          size = json['size'] || 'medium'

          if width && height
            classes << "w-[#{width}px]"
            classes << "h-[#{height}px]"
          else
            case size.to_s.downcase
            when 'small'
              classes << 'w-4 h-4'
            when 'large'
              classes << 'w-8 h-8'
            else # medium
              classes << 'w-6 h-6'
            end
          end

          # Spinner animation
          classes << 'animate-spin'
          classes << 'rounded-full'

          # Border width
          border_width = json['strokeWidth'] || json['borderWidth'] || 2
          classes << "border-#{border_width}"

          classes << 'border-transparent'

          # Color
          color = json['color'] || json['tintColor'] || '#3B82F6'
          if color.start_with?('#')
            classes << "border-t-[#{color}]"
            classes << "border-r-[#{color}]" if json['halfSpinner']
          else
            classes << "border-t-#{color}"
            classes << "border-r-#{color}" if json['halfSpinner']
          end

          classes.join(' ')
        end
      end
    end
  end
end
