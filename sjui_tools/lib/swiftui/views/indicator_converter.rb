#!/usr/bin/env ruby

require_relative 'base_view_converter'

module SjuiTools
  module SwiftUI
    module Views
      class IndicatorConverter < BaseViewConverter
        def convert
          # Check for animating property binding
          animating = @component['animating']

          if animating == false
            # Static false - don't show indicator
            add_line "EmptyView()"
          elsif animating.is_a?(String) && animating.match(/@\{([^}]+)\}/)
            # Animating is a binding
            variable = $1
            # Wrap in if condition based on binding
            add_line "if data.#{to_camel_case(variable)} {"
            indent do
              generate_progress_view
            end
            add_line "}"
          else
            # Static true, any truthy value, or no animating property - always show
            generate_progress_view
          end

          generated_code
        end

        private

        def generate_progress_view
          # ProgressView（インジケーター）
          add_line "ProgressView()"

          # style with scale effect for size
          indicator_style = @component['indicatorStyle'] || @component['style']
          if indicator_style
            style = indicator_style_to_swiftui(indicator_style)
            add_modifier_line ".progressViewStyle(#{style})"

            # Apply scale based on style
            scale = get_scale_for_style(indicator_style)
            if scale != 1.0
              add_modifier_line ".scaleEffect(#{scale})"
            end
          end

          # color/tint
          color = @component['color'] || @component['tintColor'] || @component['tint']
          if color
            swiftui_color = get_swiftui_color(color)
            add_modifier_line ".tint(#{swiftui_color})"
          end

          # 共通のモディファイアを適用
          apply_modifiers
        end

        def indicator_style_to_swiftui(style)
          case style.to_s.downcase
          when 'linear'
            'LinearProgressViewStyle()'
          else
            'CircularProgressViewStyle()'
          end
        end

        def get_scale_for_style(style)
          case style.to_s.downcase
          when 'large'
            1.5
          when 'small'
            0.8
          else
            1.0
          end
        end

        def to_camel_case(str)
          return str if str.nil? || str.empty?

          # Handle snake_case to camelCase
          parts = str.split('_')
          parts[0] + parts[1..-1].map(&:capitalize).join
        end
      end
    end
  end
end
