# frozen_string_literal: true

require_relative '../view_binding_handler'

module SjuiTools
  module SwiftUI
    module Binding
      class ButtonBindingHandler < ViewBindingHandler
        def handle_specific_binding(component, key, value)
          case key
          when 'text'
            # Button text is handled in the Button label
            nil
          when 'enabled'
            if is_binding?(value)
              binding = parse_binding(value, read_only: true)
              ".disabled(!#{binding})"
            end
          when 'fontColor'
            if is_binding?(value)
              binding = parse_binding(value, read_only: true)
              color_expr = resolve_color_binding_expr(binding)
              ".foregroundColor(#{color_expr})"
            end
          else
            nil
          end
        end

        # Get the button text (with binding support)
        def get_button_text(component)
          text_value = component['text']
          if is_binding?(text_value)
            parse_binding(text_value, read_only: true)
          else
            "\"#{text_value || ''}\""
          end
        end

        # Get the action name for the button
        def get_action(component)
          onClick = component['onClick']
          if onClick
            # Extract function name from binding format @{functionName}
            method_name = onClick.gsub(/^@\{|\}$/, '')
            "data.#{method_name}?()"
          else
            "{}"
          end
        end
      end
    end
  end
end