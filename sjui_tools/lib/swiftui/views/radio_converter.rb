#!/usr/bin/env ruby

require_relative 'base_view_converter'
require_relative '../helpers/font_helper'

module SjuiTools
  module SwiftUI
    module Views
      class RadioConverter < BaseViewConverter
        include SjuiTools::SwiftUI::Helpers::FontHelper
        def convert
          id = @component['id'] || 'radio'
          items = @component['items'] || []
          text = @component['text'] || ""
          
          # Check if this is a radio group with items
          if items.any?
            # Get selection binding
            if @component['selectedValue'] && is_binding?(@component['selectedValue'])
              selection_binding = "data.#{extract_binding_property(@component['selectedValue'])}"
            else
              state_var = "selected#{id.split('_').map(&:capitalize).join}"
              add_state_variable(state_var, "String", '""')
              selection_binding = state_var
            end
            
            # Create radio group with ForEach
            add_line "VStack(alignment: .leading, spacing: 8) {"
            indent do
              if text && !text.empty?
                # Escape double quotes in text for Swift string literal
                escaped_text = text.gsub('"', '\\"')
                add_line "Text(\"#{escaped_text}\")"
                # Apply font modifiers using helper
                apply_font_modifiers(@component, self)
              end
              
              items.each_with_index do |item, index|
                add_line "HStack {"
                indent do
                  add_radio_icon_lines("#{selection_binding} == \"#{item}\"")
                  add_modifier_line ".onTapGesture {"
                  indent do
                    add_line "#{selection_binding} = \"#{item}\""
                    # onValueChange handler - called when radio selection changes
                    # onValueChange (camelCase) -> binding format only (@{functionName})
                    if @component['onValueChange'] && is_binding?(@component['onValueChange'])
                      handler_call = get_event_handler_invocation(@component['onValueChange'], id, index.to_s)
                      add_line handler_call
                    end
                  end
                  add_line "}"
                  # Escape double quotes in item text for Swift string literal
                  escaped_item = item.gsub('"', '\\"')
                  add_line "Text(\"#{escaped_item}\")"
                end
                add_line "}"
              end
            end
            add_line "}"
          else
            # Single radio button (old implementation)
            group = @component['group'] || 'defaultGroup'
            
            # Create @State variable name for selection (グループごとに管理)
            state_var = "selected#{group.split('_').map(&:capitalize).join}"
            
            # Add state variable to requirements
            add_state_variable(state_var, "String", '""')
            
            # カスタムRadioButton実装
            add_line "HStack {"
            indent do
              add_radio_icon_lines("data.#{state_var} == \"#{id}\"")
              add_modifier_line ".onTapGesture {"
              indent do
                add_line "data.#{state_var} = \"#{id}\""
                # onClick handler - called when radio is clicked
                # onClick (camelCase) -> binding format only (@{functionName})
                if @component['onClick'] && is_binding?(@component['onClick'])
                  handler_call = get_event_handler_invocation(@component['onClick'], id, nil)
                  add_line handler_call
                end
              end
              add_line "}"
              
              if text && !text.empty?
                # Escape double quotes in text for Swift string literal
                escaped_text = text.gsub('"', '\\"')
                add_line "Text(\"#{escaped_text}\")"
                
                # Apply font modifiers using helper
                apply_font_modifiers(@component, self)
                
                if @component['fontColor']
                  color = get_swiftui_color(@component['fontColor'])
                  add_modifier_line ".foregroundColor(#{color})"
                end
              end
            end
            add_line "}"
          end
          
          # Disabled state
          if @component['enabled'] == false
            add_modifier_line ".disabled(true)"
            add_modifier_line ".opacity(0.6)"
          end
          
          # 共通のモディファイアを適用
          apply_modifiers
          
          generated_code
        end
        
        private

        # The radio glyph.
        #
        # `icon` / `selectedIcon` name asset images; without them the SF Symbol
        # pair is used, as before. `iconColor` replaces the hard-coded blue, and
        # reaches a custom asset only through template rendering — a tint applied
        # to an original-mode asset does nothing. `iconSize` needs .resizable()
        # to have any effect, because an SF Symbol otherwise scales with the
        # font rather than the frame.
        def add_radio_icon_lines(selected_expr)
          icon = @component['icon']
          selected_icon = @component['selectedIcon']
          size = @component['iconSize']
          icon_color = @component['iconColor'] ? get_swiftui_color(@component['iconColor']) : nil

          if icon || selected_icon
            on_name = selected_icon || icon
            off_name = icon || selected_icon
            add_line "Image(#{selected_expr} ? \"#{on_name}\" : \"#{off_name}\")"
            add_modifier_line ".renderingMode(.template)" if icon_color
            add_modifier_line ".resizable()"
            add_modifier_line ".aspectRatio(contentMode: .fit)"
          else
            add_line "Image(systemName: #{selected_expr} ? \"largecircle.fill.circle\" : \"circle\")"
            if size
              add_modifier_line ".resizable()"
              add_modifier_line ".aspectRatio(contentMode: .fit)"
            end
          end
          add_modifier_line ".frame(width: #{size}, height: #{size})" if size
          add_modifier_line ".foregroundColor(#{icon_color || '.blue'})"
        end
        
        def add_state_variable(name, type, default_value)
          @state_variables ||= []
          @state_variables << "@State private var #{name}: #{type} = #{default_value}"
        end
      end
    end
  end
end