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
          # Padding and margin are NOT handled here.
          #
          # `SpacingHelper#apply_padding` / `#apply_margins` read every
          # spelling of both — `paddingTop` and its `topPadding` alias, the
          # `padding` / `paddings` shorthand, the RTL pair — and since plan 49
          # they emit the bound form through the canonical numeric emitter.
          # This branch read four of the eight padding spellings and none of
          # the shorthands, which is why `topPadding` and friends froze to
          # `.padding(.top, 0)` while `paddingTop` did not. Adding the missing
          # spellings here would have been the second copy of a vocabulary
          # (plan 40); deleting the branch leaves one.
          #
          # It was also actively destructive: `process_bindings` registers its
          # result with `ModifierBag#register`, which REPLACES a multi-value
          # key, so one bound padding edge dropped every static padding on the
          # same view. And it emitted `data.x` bare into a CGFloat slot, which
          # does not compile for an optional property.
          #
          # Every converter that runs this handler also runs SpacingHelper —
          # the one exception is ViewConverter's `skip_padding:` under
          # relative positioning, where the container's `parentPadding`
          # already owns the inset and a modifier here would double it.

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
            # This branch only ever runs for a BINDING (the guard at the top
            # of the method returns for anything else), and it emitted an
            # unconditional `.clipped()` — every bound clipToBounds clipped,
            # whatever the property said. `.clipped()` has no conditional
            # form and SwiftJsonUI's `View.if` helper is internal to the
            # module, so generated app code cannot express "clip when true"
            # with today's public API.
            #
            # Emitting nothing is the same answer the dynamic runtime gives
            # (DynamicModifierHelper: `guard component.clipToBounds == true`,
            # and a `@{...}` decodes to nil there), so the two paths agree
            # rather than disagreeing in opposite directions. Reported to the
            # SwiftJsonUI lane: a public `func clipToBounds(_ enabled: Bool)`
            # closes it on both sides at once.
            nil
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