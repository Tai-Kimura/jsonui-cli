# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class SliderConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          base_style_attr = build_base_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr

          min_value = json['minimumValue'] || 0
          max_value = json['maximumValue'] || 100
          step_value = json['step']

          # Handle range array format: [min, max]
          if json['range'].is_a?(Array) && json['range'].length == 2
            min_value = json['range'][0]
            max_value = json['range'][1]
          end

          value_attr = build_value_attr
          on_change = build_on_change
          disabled_attr = build_disabled_attr
          step_attr = step_value ? " step={#{step_value}}" : ''

          # Accent color via style
          slider_style_attr = build_slider_style_attr

          jsx = <<~JSX.chomp
            #{indent_str(indent)}<input#{id_attr} type="range" className="#{class_name}" min={#{min_value}} max={#{max_value}}#{step_attr}#{value_attr}#{on_change}#{disabled_attr}#{slider_style_attr}#{base_style_attr}#{testid_attr}#{tag_attr} />
          JSX

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]

          classes << 'w-full'
          classes << 'cursor-pointer'

          # Disabled state
          if json['enabled'] == false
            classes << 'opacity-50 cursor-not-allowed'
          elsif has_binding?(json['enabled'])
            binding_expr = extract_binding_property(json['enabled'])
            classes << "${!#{binding_expr} ? 'opacity-50 cursor-not-allowed' : ''}"
          end

          classes.compact.reject(&:empty?).join(' ')
        end

        def build_value_attr
          value = json['value']

          if value && has_binding?(value)
            prop = extract_binding_property(value)
            " value={#{prop}}"
          elsif value
            " defaultValue={#{value}}"
          else
            ''
          end
        end

        def build_on_change
          # If custom handler is defined, use it (passing the event object)
          handler = json['onValueChange']
          if handler && has_binding?(handler)
            prop = extract_binding_property(handler)
            return " onChange={(e) => #{prop}?.(Number(e.target.value))}"
          end

          # Auto-generate onChange from value binding property
          # e.g., value: "@{sliderValue}" -> onChange={(e) => data.onSliderValueChange?.(Number(e.target.value))}
          value = json['value']
          if value && has_binding?(value)
            property_name = extract_raw_binding_property(value)
            handler_name = "on#{capitalize_first(property_name)}Change"
            return " onChange={(e) => data.#{handler_name}?.(Number(e.target.value))}"
          end

          ''
        end

        def capitalize_first(str)
          return str if str.nil? || str.empty?

          str[0].upcase + str[1..]
        end

        def build_disabled_attr
          enabled = json['enabled']
          return '' if enabled.nil?

          if has_binding?(enabled)
            " disabled={!#{extract_binding_property(enabled)}}"
          elsif enabled == false
            ' disabled'
          else
            ''
          end
        end

        def build_slider_style_attr
          style_parts = []

          tint_color = json['tintColor'] || json['minimumTrackTintColor']
          style_parts << "accentColor: '#{tint_color}'" if tint_color

          max_track_color = json['maximumTrackTintColor']
          style_parts << "backgroundColor: '#{max_track_color}'" if max_track_color

          return '' if style_parts.empty?

          " style={{ #{style_parts.join(', ')} }}"
        end

        def build_base_style_attr
          build_style_attr
        end
      end
    end
  end
end
