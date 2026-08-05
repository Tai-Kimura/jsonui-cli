#!/usr/bin/env ruby

require_relative 'base_view_converter'

module SjuiTools
  module SwiftUI
    module Views
      class ProgressConverter < BaseViewConverter
        def convert
          id = @component['id'] || 'progress'
          # Undeclared progress renders an EMPTY bar (0); a nonzero default made
          # the control half-full and progress:0.5 fixtures measured inert
          # (see shared/core/attribute_semantics.json → progressValue).
          progress = @component['progress'] || 0
          
          # Get progress value (binding or static)
          progress_value = if @component['progress'] && is_binding?(@component['progress'])
                            "data.#{extract_binding_property(@component['progress'])}"
                          else
                            # Create @State variable name
                            state_var = "#{id}Value"
                            # Add state variable to requirements
                            add_state_variable(state_var, "Double", progress.to_s)
                            state_var
                          end
          
          # ProgressView
          add_line "ProgressView(value: #{progress_value})"

          # indicatorStyle — the declared vocabulary is `medium` / `large`
          # ("ActivityIndicator size style"), not linear/circular. Reading it
          # as the shape mapped BOTH declared values to
          # `CircularProgressViewStyle()`, so the attribute emitted one
          # constant whatever you wrote (`jui conformance codegen-effect` C2).
          #
          # `style` keeps the shape reading: it is the separate spelling that
          # carries linear/circular and is not the same attribute.
          #
          # `.scaleEffect`, not `.controlSize`. `controlSize` is the API a
          # size vocabulary reads like it wants, and the 3PF round-3 measure
          # says it does nothing to a determinate `ProgressView(value:)` on
          # ios: BOTH declared values went inert against their control the
          # moment this converter started emitting it. The Indicator
          # converter has used `scaleEffect` for the same vocabulary all
          # along and its `large` fixture measures ACTIVE, so the mechanism
          # that works on this platform is already in the tree.
          #
          # `medium` is scale 1.0 and emits nothing — the same
          # `value-is-default` shape Indicator's medium has. That is honest
          # rather than fixed: the representative value is what would need to
          # change for the fixture to discriminate (lane D's
          # PREFERRED_PRIMARY_CASE).
          scale = indicator_size_scale(@component['indicatorStyle'])
          add_modifier_line ".scaleEffect(#{scale})" if scale != 1.0

          style = @component['style']
          if style
            swift_style = style.to_s.downcase == 'linear' ? 'LinearProgressViewStyle()' : 'CircularProgressViewStyle()'
            add_modifier_line ".progressViewStyle(#{swift_style})"
          end

          # progressTintColor — `color` and `tintColor` are the Indicator/UIKit
          # spellings of the same accent; the specific name wins.
          progress_tint = @component['progressTintColor'] || @component['color'] || @component['tintColor']
          if progress_tint
            color = get_swiftui_color(progress_tint)
            add_modifier_line ".tint(#{color})"
          end
          
          # trackTintColor（SwiftUIでは背景として実装）
          if @component['trackTintColor']
            color = get_swiftui_color(@component['trackTintColor'])
            add_modifier_line ".background(#{color})"
          end

          # hidesWhenStopped — the UIActivityIndicatorView property SJUIViewCreator
          # sets. On a determinate ProgressView "stopped" is progress == 0, so
          # this hides the bar until there is progress to show. Read by nobody
          # before, which meant a Progress declared with it stayed visible at 0.
          if @component['hidesWhenStopped'] == true
            add_modifier_line ".opacity(#{progress_value} > 0 ? 1 : 0)"
          end
          
          # 共通のモディファイアを適用
          apply_modifiers
          
          generated_code
        end
        
        private
        
        def add_state_variable(name, type, default_value)
          @state_variables ||= []
          @state_variables << "@State private var #{name}: #{type} = #{default_value}"
        end
      end
    end
  end
end