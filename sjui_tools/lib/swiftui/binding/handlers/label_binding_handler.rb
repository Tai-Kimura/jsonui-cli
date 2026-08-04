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
              # `.system(size:)` takes a CGFloat, and `parse_binding` hands
              # back the read-only VALUE expression — an Optional for any
              # property without a data-section default, which does not
              # compile. `swift_number_expr` fixes the optionality and not the
              # TYPE: a `fontSize` declared `Int` still is not a CGFloat.
              # `bound_number` does both.
              ".font(.system(size: #{bound_number(value)}))"
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
        # Canonical '@{path ?? default}' is parsed via BindingExpression;
        # string defaults become double-quoted Swift literals, number/bool
        # defaults stay bare, null/no default keeps the '?? ""' text fallback
        # for optional properties.
        def get_text_content(component)
          text_value = component['text']
          if is_binding?(text_value)
            # Full binding: @{propertyName [?? default]}
            expr = BindingExpression.swift_text_expr(text_value[2..-2], prefix: 'data')
            if expr
              "\"\\(#{expr})\""
            else
              # Negation is not valid in text contexts — canonical runtimes
              # treat the token as unresolved (empty string)
              "\"\""
            end
          elsif text_value && text_value.include?('@{')
            # Text with interpolation: "Some text @{property} more text".
            # Literal segments are escaped individually so quotes emitted as
            # part of Swift default literals stay unescaped inside \(...)
            parts = text_value.split(/(@\{[^}]+\})/)
            interpolated = parts.map do |part|
              if (m = part.match(/\A@\{([^}]+)\}\z/))
                expr = BindingExpression.swift_text_expr(m[1], prefix: 'data')
                expr ? "\\(#{expr})" : ''
              else
                part.gsub('"', '\\"').gsub("\n", "\\n")
              end
            end.join
            "\"#{interpolated}\""
          else
            "\"#{(text_value || '').gsub('"', '\\"').gsub("\n", "\\n")}\""
          end
        end
      end
    end
  end
end