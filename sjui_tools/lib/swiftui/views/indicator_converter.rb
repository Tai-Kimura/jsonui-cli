#!/usr/bin/env ruby

require_relative 'base_view_converter'

module SjuiTools
  module SwiftUI
    module Views
      class IndicatorConverter < BaseViewConverter
        def convert
          # Check for animating property binding
          animating = @component['animating']

          # hidesWhenStopped — UIActivityIndicatorView's own property, which
          # SJUIViewCreator sets. Default TRUE, matching UIKit: a stopped
          # indicator disappears. `false` keeps the (stopped) indicator in the
          # layout, so it has to render rather than collapse to EmptyView — the
          # difference is whether the surrounding layout reflows, which is the
          # whole reason the attribute exists.
          hides_when_stopped = @component['hidesWhenStopped']
          hides_when_stopped = true if hides_when_stopped.nil?

          if animating == false
            if hides_when_stopped
              # Static false - don't show indicator
              add_line "EmptyView()"
            else
              # Keeps its space: a stopped indicator that still occupies layout.
              generate_progress_view
              @modifier_bag.append(:component_specific, ".opacity(0)")
            end
          elsif animating.is_a?(String) && animating.match(/@\{([^}]+)\}/)
            # Animating is a binding
            variable = $1
            if hides_when_stopped
              # Wrap the binding condition in Group: an `if` is a statement,
              # not a view, so the modifier chain the base converter appends
              # (accessibilityIdentifier, frame, ...) cannot attach to it —
              # same idiom as the secure-field branch (textfield_converter).
              add_line "Group {"
              indent do
                add_line "if data.#{to_camel_case(variable)} {"
                indent do
                  generate_progress_view
                end
                add_line "}"
              end
              add_line "}"
            else
              prop = to_camel_case(variable)
              generate_progress_view
              @modifier_bag.append(
                :component_specific,
                ".opacity(data.#{prop} ? 1 : 0)"
              )
            end
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

        # Delegates to the shared table: Progress reads the same declared
        # vocabulary, and two copies of one vocabulary drift (plan 40).
        def get_scale_for_style(style)
          indicator_size_scale(style)
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
