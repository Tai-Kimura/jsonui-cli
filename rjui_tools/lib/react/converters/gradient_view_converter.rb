# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class GradientViewConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          style_attr = build_gradient_style
          children = convert_children(indent)
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr
          event_attrs = build_event_attrs

          jsx = if children.empty?
            "#{indent_str(indent)}<div#{id_attr} className=\"#{class_name}\"#{style_attr}#{event_attrs}#{testid_attr}#{tag_attr} />"
          else
            <<~JSX.chomp
              #{indent_str(indent)}<div#{id_attr} className="#{class_name}"#{style_attr}#{event_attrs}#{testid_attr}#{tag_attr}>
              #{children}
              #{indent_str(indent)}</div>
            JSX
          end

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_gradient_style
          gradient_css = build_gradient_css
          return build_style_attr unless gradient_css

          existing_style = build_style_attr
          if existing_style.empty?
            " style={{ background: '#{gradient_css}' }}"
          else
            existing_style.sub(/\}\}$/, ", background: '#{gradient_css}' }}")
          end
        end

        def build_gradient_css
          colors = json['gradient'] || json['colors']
          return nil unless colors.is_a?(Array) && colors.length >= 2

          direction = get_gradient_direction
          locations = json['locations']

          color_stops = if locations.is_a?(Array) && locations.length == colors.length
            colors.each_with_index.map do |color, i|
              "#{color} #{(locations[i] * 100).to_i}%"
            end.join(', ')
          else
            colors.join(', ')
          end

          gradient_type = json['gradientType']&.downcase

          if gradient_type == 'radial'
            "radial-gradient(circle, #{color_stops})"
          else
            "linear-gradient(#{direction}, #{color_stops})"
          end
        end

        def get_gradient_direction
          # Check for startPoint/endPoint first
          if json['startPoint'] && json['endPoint']
            start_x, start_y = json['startPoint']
            end_x, end_y = json['endPoint']

            # Calculate angle from points
            angle = Math.atan2(end_y - start_y, end_x - start_x) * (180 / Math::PI) + 90
            return "#{angle.round}deg"
          end

          # Check for angle directly
          return "#{json['angle']}deg" if json['angle']

          # Fall back to gradientDirection
          direction = (json['gradientDirection'] || json['direction'] || 'Vertical').downcase
          case direction
          when 'horizontal', 'lefttoright'
            'to right'
          when 'righttoleft'
            'to left'
          when 'toptobottom'
            'to bottom'
          when 'bottomtotop'
            'to top'
          when 'oblique', 'diagonal'
            '45deg'
          else # vertical
            'to bottom'
          end
        end

        def build_class_name
          classes = [super]

          # Default flex column for View with children
          if json['child'].is_a?(Array) && !json['orientation']
            classes.unshift('flex flex-col')
          end

          # Corner radius
          corner_radius = json['cornerRadius']
          classes << "rounded-[#{corner_radius}px]" if corner_radius

          # Overflow hidden for corner radius
          classes << 'overflow-hidden' if corner_radius

          # Cursor pointer for clickable items
          classes << 'cursor-pointer' if json['onClick'] || json['onclick']

          classes.compact.reject(&:empty?).join(' ')
        end

        def build_event_attrs
          attrs = []
          attrs << build_onclick_attr
          attrs.compact.join('')
        end
      end
    end
  end
end
