#!/usr/bin/env ruby

require_relative 'base_view_converter'

module SjuiTools
  module SwiftUI
    module Views
      class SliderConverter < BaseViewConverter
        def convert
          # Slider properties
          min_value = attr_with_alias('minimum', 'minimumValue', 'minValue') || 0
          max_value = attr_with_alias('maximum', 'maximumValue', 'maxValue') || 1
          value_prop = @component['value'] || min_value

          # range プロパティの処理（配列形式: [min, max]）
          if @component['range'].is_a?(Array) && @component['range'].length == 2
            min_value = @component['range'][0]
            max_value = @component['range'][1]
          end

          # The range is a `ClosedRange<Double>` in the emitted Swift, so a
          # bound bound has to be an expression: interpolating the
          # declaration produced `in: 0...@{max}`, which is not a program.
          # `Double` rather than CGFloat because `Slider(value:in:)` infers
          # the range from the Binding's Double.
          min_expr = bound_number(min_value, cast: 'Double') || min_value
          max_expr = bound_number(max_value, cast: 'Double') || max_value

          # Check if value is a binding
          if @component['value'] && @component['value'].to_s.start_with?('@{') && @component['value'].to_s.end_with?('}')
            # Use binding from data model (two-way position: parsed path only)
            property_name = SwiftUI::Binding::BindingExpression.parse(@component['value'][2..-2]).path
            binding_var = "$data.#{property_name}"
            add_line "Slider(value: #{binding_var}, in: #{min_expr}...#{max_expr})"
          else
            # Create @State variable name
            state_var = "sliderValue#{@component['id'] || ''}"
            state_var = state_var.gsub(/[^a-zA-Z0-9]/, '')
            
            # Add state variable to requirements
            add_state_variable(state_var, "Double", value_prop.to_s)
            
            # Slider
            add_line "Slider(value: $#{state_var}, in: #{min_expr}...#{max_expr})"
          end
          
          # Tint. `progressTintColor` is the specific spelling for the FILLED
          # portion and wins over the generic `tintColor`, the same precedence
          # the Progress converter takes for the same pair. Both were declared
          # `deprecated: swiftui` on the grounds that "SwiftUI Slider uses a
          # unified tint only"; the SSoT withdrew that on 2026-08-05 because
          # Progress — also SwiftUI — maps the identical pair to `.tint()` and
          # `.background()`. Unimplemented, not impossible.
          slider_tint = @component['progressTintColor'] || @component['tintColor']
          if slider_tint
            color = get_swiftui_color(slider_tint)
            add_modifier_line ".accentColor(#{color})"
          end

          # trackTintColor — the UNFILLED track (canonical:
          # attribute_semantics.json trackColors.sliderTrack, 2026-08-06).
          # `.background()` painted the view's whole frame, which the same
          # ruling names as the wrong reading. SwiftUI exposes nothing for
          # the unfilled track, so this goes through UISlider.appearance()
          # at appear time — the identical emit the dynamic SliderConverter
          # has carried all along (ios parity d 32 was the two sides
          # disagreeing, not either one missing the attribute).
          if @component['trackTintColor']
            color = get_swiftui_color(@component['trackTintColor'])
            add_modifier_line ".onAppear {"
            add_modifier_line "    UISlider.appearance().maximumTrackTintColor = UIColor(#{color})"
            add_modifier_line "}"
          end
          
          # Disabled state
          if @component['enabled'] == false
            add_modifier_line ".disabled(true)"
          end
          
          # Value change handler
          # onValueChange (camelCase) -> binding format only (@{functionName})
          # Also support legacy onValueChanged for backward compatibility
          handler = attr_with_alias('onValueChange', 'onValueChanged')
          if handler && is_binding?(handler)
            id = @component['id'] || 'slider'
            binding_prop = if @component['value'] && is_binding?(@component['value'])
                            extract_binding_property(@component['value'])
                          else
                            "sliderValue#{@component['id'] || ''}".gsub(/[^a-zA-Z0-9]/, '')
                          end
            handler_call = get_event_handler_invocation(handler, id, 'newValue')
            add_modifier_line ".onChange(of: data.#{binding_prop}) { _, newValue in"
            indent do
              add_line handler_call
            end
            add_line "}"
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