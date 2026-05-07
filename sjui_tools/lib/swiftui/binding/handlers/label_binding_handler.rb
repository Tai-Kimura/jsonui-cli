# frozen_string_literal: true

require_relative '../view_binding_handler'
require_relative '../../views/color_helper'

module SjuiTools
  module SwiftUI
    module Binding
      class LabelBindingHandler < ViewBindingHandler
        def handle_specific_binding(component, key, value)
          case key
          when 'text'
            # Text content is handled in the Text initialization
            # Return nil as it's not a modifier
            nil
          when 'fontColor'
            if is_binding?(value)
              binding = parse_binding(value, read_only: true)
              color_expr = resolve_color_binding_expr(binding)
              ".foregroundColor(#{color_expr})"
            end
          when 'fontSize'
            if is_binding?(value)
              binding = parse_binding(value, read_only: true)
              ".font(.system(size: #{binding}))"
            end
          when 'font'
            if is_binding?(value)
              binding = parse_binding(value, read_only: true)
              # Handle font weight binding
              ".fontWeight(#{binding} == \"bold\" ? .bold : .regular)"
            end
          else
            nil
          end
        end

        # Get the text content (with binding support)
        def get_text_content(component)
          text_value = component['text']
          if is_binding?(text_value)
            # Full binding: @{propertyName}
            # For Text views, we need the actual value, not a binding
            # So we remove the $ prefix that parse_binding adds
            binding = parse_binding(text_value, read_only: true)
            if binding
              property_path = binding
              # Extract property name from path (e.g., "data.propertyName" -> "propertyName")
              property_name = property_path.sub(/^data\./, '')

              # Check if property has defaultValue (non-optional)
              if Views::ColorHelper.has_default_value?(property_name)
                # Non-optional - use directly
                "\"\\(#{property_path})\""
              else
                # Optional - add ?? "" fallback
                "\"\\(#{property_path} ?? \"\")\""
              end
            else
              "\"\""
            end
          elsif text_value && text_value.include?('@{')
            # Text with interpolation: "Some text @{property} more text"
            # Extract all binding expressions
            interpolated = text_value.gsub(/@\{([^}]+)\}/) do |match|
              property_name = $1
              # Check if property has defaultValue (non-optional)
              if Views::ColorHelper.has_default_value?(property_name)
                # Non-optional - use directly
                "\\(data.#{property_name})"
              else
                # Optional - add ?? "" fallback
                "\\(data.#{property_name} ?? \"\")"
              end
            end
            "\"#{interpolated.gsub('"', '\\"').gsub("\n", "\\n")}\""
          else
            "\"#{(text_value || '').gsub('"', '\\"').gsub("\n", "\\n")}\""
          end
        end
      end
    end
  end
end