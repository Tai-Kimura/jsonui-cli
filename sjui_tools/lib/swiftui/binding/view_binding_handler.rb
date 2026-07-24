# frozen_string_literal: true

require_relative 'binding_expression'

module SjuiTools
  module SwiftUI
    module Binding
      class ViewBindingHandler
        def initialize
          @binding_code = []
        end

        # Parse binding syntax @{expr} and return the Swift binding code.
        # Canonical expression grammar (shared/core/binding_semantics.json):
        # path with optional single '?? default', or '!path' negation.
        # @param read_only [Boolean] if true, use data. (read-only value
        #   context) instead of $data. (two-way Binding position; canonically
        #   a single flat identifier — defaults/negation are validator errors
        #   and are not emitted there)
        def parse_binding(value, read_only: false)
          return nil unless value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')

          inner = value[2..-2] # Remove @{ and }
          if read_only
            BindingExpression.swift_value_expr(inner, prefix: 'data')
          else
            BindingExpression.swift_two_way_expr(inner, prefix: '$data')
          end
        end

        # Check if a value is a binding expression
        def is_binding?(value)
          value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')
        end

        # Handle common bindings that apply to all views
        # All common bindings are read-only (use data. not $data.)
        def handle_common_binding(component, key, value)
          return nil unless is_binding?(value)

          binding = parse_binding(value, read_only: true)
          return nil unless binding

          case key
          when 'visibility'
            # Visibility is handled by VisibilityWrapper in child_renderer.rb, not here
            nil
          when 'background'
            color_expr = resolve_color_binding_expr(binding)
            ".background(#{color_expr})"
          when 'cornerRadius'
            ".cornerRadius(#{binding})"
          when 'opacity', 'alpha'
            ".opacity(#{binding})"
          when 'disabled'
            ".disabled(#{binding})"
          # Size constraints
          when 'width'
            ".frame(width: #{binding})"
          when 'height'
            ".frame(height: #{binding})"
          when 'minWidth'
            ".frame(minWidth: #{binding})"
          when 'maxWidth'
            ".frame(maxWidth: #{binding})"
          when 'minHeight'
            ".frame(minHeight: #{binding})"
          when 'maxHeight'
            ".frame(maxHeight: #{binding})"
          # Padding bindings
          when 'paddingTop'
            ".padding(.top, #{binding})"
          when 'paddingBottom'
            ".padding(.bottom, #{binding})"
          when 'paddingLeft', 'paddingStart'
            ".padding(.leading, #{binding})"
          when 'paddingRight', 'paddingEnd'
            ".padding(.trailing, #{binding})"
          # Margin bindings (SwiftUI uses padding for margins)
          when 'topMargin'
            ".padding(.top, #{binding})"
          when 'bottomMargin'
            ".padding(.bottom, #{binding})"
          when 'leftMargin', 'startMargin'
            ".padding(.leading, #{binding})"
          when 'rightMargin', 'endMargin'
            ".padding(.trailing, #{binding})"
          # Color attributes
          when 'tintColor'
            ".tint(#{binding})"
          when 'tapBackground', 'highlightBackground'
            ".background(#{binding})"
          # Border attributes
          when 'borderWidth'
            # Note: SwiftUI border requires overlay with stroke
            corner = component['cornerRadius'] || 0
            ".overlay(RoundedRectangle(cornerRadius: #{corner.to_i}).stroke(lineWidth: #{binding}))"
          when 'borderColor'
            # Note: SwiftUI border requires overlay with stroke
            corner = component['cornerRadius'] || 0
            border_width = component['borderWidth'] || 1
            color_expr = resolve_color_binding_expr(binding)
            ".overlay(RoundedRectangle(cornerRadius: #{corner.to_i}).stroke(#{color_expr}, lineWidth: #{border_width.to_i}))"
          when 'borderStyle'
            # Note: borderStyle (solid/dashed/dotted) requires StrokeStyle for dashed/dotted
            # Dynamic binding of borderStyle is complex in SwiftUI - recommend static usage
            nil
          when 'clipToBounds'
            ".clipped()"
          # User interaction
          when 'userInteractionEnabled', 'canTap'
            ".allowsHitTesting(#{binding})"
          else
            nil
          end
        end

        # Handle specific bindings for each view type (override in subclasses)
        def handle_specific_binding(component, key, value)
          nil
        end

        # Resolve a binding expression to a Color value
        # If the binding is a String property (color name), wraps with getColor(for:)
        # If it's already a Color property, returns as-is
        def resolve_color_binding_expr(binding)
          # Use getColor(for:) to handle both String color names and Color values
          "SwiftJsonUIConfiguration.shared.getColor(for: #{binding}) ?? Color.clear"
        end

        # Process all bindings for a component
        # @param skip_keys [Array<String>] keys to skip (already handled by converter)
        def process_bindings(component, skip_keys: [])
          modifiers = []

          component.each do |key, value|
            next if skip_keys.include?(key)

            # Try common bindings first
            modifier = handle_common_binding(component, key, value)
            modifiers << modifier if modifier

            # Try specific bindings
            modifier = handle_specific_binding(component, key, value)
            modifiers << modifier if modifier
          end

          modifiers
        end

        # Get the binding property value or the literal value
        def get_value(value, default = nil)
          if is_binding?(value)
            parse_binding(value)
          else
            value || default
          end
        end
      end
    end
  end
end