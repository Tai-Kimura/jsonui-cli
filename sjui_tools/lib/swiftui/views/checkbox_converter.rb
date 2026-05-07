#!/usr/bin/env ruby

require_relative 'base_view_converter'
require_relative '../helpers/font_helper'

module SjuiTools
  module SwiftUI
    module Views
      # CheckboxConverter handles "CheckBox" and "Check" component types.
      # Generates CheckBoxView component for SwiftUI static mode.
      class CheckboxConverter < BaseViewConverter
        include SjuiTools::SwiftUI::Helpers::FontHelper

        def convert
          id = @component['id'] || 'checkbox'
          text = @component['text'] || @component['label'] || ""

          # Get icon names
          icon = @component['icon'] || @component['src']
          selected_icon = @component['selectedIcon'] || @component['onSrc']

          # Get state binding
          state_binding = get_state_binding(id)

          # Build CheckBoxView initialization
          add_line "CheckBoxView("
          indent do
            add_line "isOn: #{state_binding},"

            # Label
            if !text.empty?
              if is_binding?(text)
                add_line "label: data.#{extract_binding_property(text)},"
              else
                escaped_text = text.gsub('"', '\\"')
                add_line "label: \"#{escaped_text}\","
              end
            end

            # Custom icons
            if icon
              add_line "icon: \"#{icon}\","
            end
            if selected_icon
              add_line "selectedIcon: \"#{selected_icon}\","
            end

            # Icon size
            if @component['iconSize']
              add_line "iconSize: #{@component['iconSize']},"
            end

            # Spacing
            if @component['spacing']
              add_line "spacing: #{@component['spacing']},"
            end

            # Font properties
            if @component['fontSize']
              add_line "fontSize: #{@component['fontSize']},"
            end

            if @component['fontStyle']
              weight = get_font_weight(@component['fontStyle'])
              add_line "fontWeight: .#{weight}," if weight
            end

            # Font color
            if @component['fontColor']
              color = get_swiftui_color(@component['fontColor'])
              add_line "fontColor: #{color},"
            end

            # Checked/unchecked colors (support checkedColor, checkColor, tintColor, onTintColor)
            checked_color_value = @component['checkedColor'] || @component['checkColor'] || @component['tintColor'] || @component['onTintColor']
            if checked_color_value
              color = get_swiftui_color(checked_color_value)
              add_line "checkedColor: #{color},"
            end

            if @component['uncheckedColor']
              color = get_swiftui_color(@component['uncheckedColor'])
              add_line "uncheckedColor: #{color},"
            end

            # Enabled state
            if @component.key?('enabled')
              if is_binding?(@component['enabled'])
                enabled_binding = extract_binding_property(@component['enabled'])
                add_line "isEnabled: data.#{enabled_binding},"
              elsif @component['enabled'] == false
                add_line "isEnabled: false,"
              end
            end

            # onValueChange callback (supports type-based invocation)
            # onValueChange (camelCase) -> binding format only (@{functionName})
            # Also support legacy onValueChanged and onClick for backward compatibility
            handler_attr = @component['onValueChange'] || @component['onClick'] || @component['action'] || @component['onValueChanged']
            if handler_attr && is_binding?(handler_attr)
              handler_call = get_event_handler_invocation(handler_attr, id, 'newValue')
              add_line "onValueChanged: { newValue in #{handler_call} }"
            end
          end
          add_line ")"

          # Apply common modifiers
          apply_modifiers

          generated_code
        end

        private

        def get_state_binding(id)
          # Check for isOn binding
          if @component['isOn'] && is_binding?(@component['isOn'])
            return "$data.#{extract_binding_property(@component['isOn'])}"
          end

          # Check for checked binding
          if @component['checked'] && is_binding?(@component['checked'])
            return "$data.#{extract_binding_property(@component['checked'])}"
          end

          # Check for bind attribute
          if @component['bind'] && is_binding?(@component['bind'])
            return "$data.#{extract_binding_property(@component['bind'])}"
          end

          # Create local state variable
          state_var = "#{id}IsOn"
          initial_value = @component['isOn'] || @component['checked'] || false
          add_state_variable(state_var, "Bool", initial_value.to_s)
          "$#{state_var}"
        end

        def add_state_variable(name, type, default_value)
          @state_variables ||= []
          @state_variables << "@State private var #{name}: #{type} = #{default_value}"
        end
      end
    end
  end
end
