#!/usr/bin/env ruby

require_relative 'color_helper'

module SjuiTools
  module SwiftUI
    module Views
      module ModifierHelper
        include ColorHelper
        private

        def apply_gradient
          colors = @component['gradient'].map { |color| get_swiftui_color(color) }
          direction = @component['gradientDirection'] || 'Vertical'

          gradient_type = case direction
          when 'Horizontal'
            "startPoint: .leading, endPoint: .trailing"
          when 'Oblique'
            "startPoint: .topLeading, endPoint: .bottomTrailing"
          else
            "startPoint: .top, endPoint: .bottom"
          end

          @modifier_bag.register(:gradient, ".background(LinearGradient(colors: [#{colors.join(', ')}], #{gradient_type}))")
        end

        def apply_safe_area_insets
          apply_safe_area_insets_to_bag
        end
      end
    end
  end
end
