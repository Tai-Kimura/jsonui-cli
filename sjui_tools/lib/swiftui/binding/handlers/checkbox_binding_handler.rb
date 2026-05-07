# frozen_string_literal: true

require_relative '../view_binding_handler'

module SjuiTools
  module SwiftUI
    module Binding
      # CheckboxBindingHandler handles binding logic for "CheckBox" and "Check" components.
      # Manages isOn/checked state bindings and enabled state.
      class CheckboxBindingHandler < ViewBindingHandler
        def handle_specific_binding(component, key, value)
          case key
          when 'isOn', 'checked'
            # Checkbox state is handled in the CheckBoxView initialization
            nil
          when 'enabled'
            if is_binding?(value)
              binding = parse_binding(value, read_only: true)
              ".disabled(!#{binding})"
            end
          else
            nil
          end
        end

        # Get the checkbox state binding
        def get_state_binding(component)
          # Check for 'isOn' property
          if component['isOn'] && is_binding?(component['isOn'])
            return parse_binding(component['isOn'])
          end

          # Check for 'checked' property
          if component['checked'] && is_binding?(component['checked'])
            return parse_binding(component['checked'])
          end

          # Check for 'bind' property
          if component['bind'] && is_binding?(component['bind'])
            return parse_binding(component['bind'])
          end

          # Return a constant binding if not a binding expression
          state_value = component['isOn'] || component['checked'] || false
          ".constant(#{state_value})"
        end

        # Get the checkbox label
        def get_label(component)
          label = component['label'] || component['text'] || ''
          if is_binding?(label)
            parse_binding(label, read_only: true)
          else
            "\"#{label}\""
          end
        end
      end
    end
  end
end
