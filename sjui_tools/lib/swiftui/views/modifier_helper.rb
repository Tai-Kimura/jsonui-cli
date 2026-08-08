#!/usr/bin/env ruby

require_relative 'color_helper'

module SjuiTools
  module SwiftUI
    module Views
      module ModifierHelper
        include ColorHelper
        private

        def apply_gradient
          # The childless-Rectangle path may already have used the gradient as
          # the shape's own fill; a second copy behind it is dead paint.
          return if @gradient_consumed_as_fill

          @modifier_bag.register(:gradient, ".background(#{gradient_expression})")
        end

        # The `LinearGradient(...)` on its own, so the childless-View path can
        # `.fill()` a Rectangle with it instead of laying it behind an opaque
        # one. See `gradient_wins_over_background?`.
        def gradient_expression
          colors = @component['gradient'].map { |color| get_swiftui_color(color) }
          direction = @component['gradientDirection'] || 'Vertical'

          # RightToLeft / BottomToTop are REVERSED directions, not aliases —
          # the declared enum keeps them distinct (valueAliases folds only
          # LeftToRight/TopToBottom/Diagonal onto the base three). They fell
          # into the vertical default here, so both reversed fixtures drew the
          # same top→bottom picture (parity run 31202080745, distances 135/18
          # against the dynamic renders, which resolve them correctly).
          gradient_type = case direction
          when 'Horizontal'
            "startPoint: .leading, endPoint: .trailing"
          when 'RightToLeft'
            "startPoint: .trailing, endPoint: .leading"
          when 'BottomToTop'
            "startPoint: .bottom, endPoint: .top"
          when 'Oblique'
            "startPoint: .topLeading, endPoint: .bottomTrailing"
          else
            "startPoint: .top, endPoint: .bottom"
          end

          "LinearGradient(colors: [#{colors.join(', ')}], #{gradient_type})"
        end

        # `backgroundFill` (attribute_semantics.json, ruled 2026-08-07):
        # ONE fill per surface, and the more specific declaration wins —
        # `gradient` names a list of stops where `background` names one colour,
        # so `background` is the FALLBACK, not a layer underneath.
        #
        # ios honoured neither reading: it drew the colour and left the
        # declared gradient invisible on both emit paths, which is the defect
        # the ruling refuses to promote into canon.
        def gradient_wins_over_background?
          g = @component['gradient']
          g.is_a?(Array) && !g.empty?
        end

        def apply_safe_area_insets
          apply_safe_area_insets_to_bag
        end
      end
    end
  end
end
