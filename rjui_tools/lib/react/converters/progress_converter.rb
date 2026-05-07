# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class ProgressConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          base_style_attr = build_base_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr

          value_attr = build_value_attr
          max_attr = " max={#{json['maximumValue'] || 100}}"

          jsx = <<~JSX.chomp
            #{indent_str(indent)}<progress#{id_attr} className="#{class_name}"#{value_attr}#{max_attr}#{base_style_attr}#{testid_attr}#{tag_attr} />
          JSX

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]

          classes << 'w-full'

          # Height
          height = json['progressHeight'] || json['barHeight']
          if height
            classes << "h-[#{height}px]"
          else
            classes << 'h-2'
          end

          classes << 'rounded-full'
          classes << 'appearance-none'

          # Custom progress bar styling
          classes << '[&::-webkit-progress-bar]:rounded-full'

          # Track color
          track_color = json['trackTintColor'] || json['trackColor']
          if track_color
            classes << "[&::-webkit-progress-bar]:bg-[#{track_color}]"
          else
            classes << '[&::-webkit-progress-bar]:bg-gray-200'
          end

          classes << '[&::-webkit-progress-value]:rounded-full'

          # Progress color
          tint_color = json['tintColor'] || json['progressTintColor']
          if tint_color
            classes << "[&::-webkit-progress-value]:bg-[#{tint_color}]"
            classes << "[&::-moz-progress-bar]:bg-[#{tint_color}]"
          else
            classes << '[&::-webkit-progress-value]:bg-blue-500'
            classes << '[&::-moz-progress-bar]:bg-blue-500'
          end

          classes.compact.reject(&:empty?).join(' ')
        end

        def build_value_attr
          value = json['value'] || json['progress'] || 0

          if has_binding?(value)
            prop = extract_binding_property(value)
            " value={#{prop}}"
          else
            " value={#{value}}"
          end
        end

        def build_base_style_attr
          build_style_attr
        end
      end
    end
  end
end
