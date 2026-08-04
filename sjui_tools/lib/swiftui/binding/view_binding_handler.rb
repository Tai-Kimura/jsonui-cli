# frozen_string_literal: true

require_relative 'binding_expression'
require_relative '../views/color_helper'
require_relative '../views/value_expression_helper'

module SjuiTools
  module SwiftUI
    module Binding
      class ViewBindingHandler
        # A colour slot takes a `Color`, and a bound colour is usually a
        # String property naming one. `ColorHelper#get_swiftui_color` is the
        # canonical emitter for that — it knows to wrap a String property in
        # `getColor(for:)` and to pass a `Color`-typed property straight
        # through, which is a distinction this class had no way to make.
        include SjuiTools::SwiftUI::Views::ColorHelper
        # …and the same for the numeric slots. `parse_binding` answers "what
        # does this expression read", which is not the same question as "what
        # does this SLOT need": a `cornerRadius` declared `Int` in the data
        # section is a perfectly good read and still not a CGFloat.
        include SjuiTools::SwiftUI::Views::ValueExpressionHelper

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
            ".background(#{get_swiftui_color(value)})"
          # Numeric slots. These handed the property over bare, so a
          # `cornerRadius` declared `Int` — the ordinary way to declare one —
          # emitted `.cornerRadius(data.r)` and the build died on
          # `cannot convert value of type 'Int'`. `bound_number` casts as well
          # as unwrapping; the canonical expression emitters answer
          # optionality alone, which is only half of what a CGFloat slot
          # needs. Found by diffing declared data types against use sites
          # across the whole generated tree (plan 49; the ios host build only
          # ever showed the first of them).
          when 'cornerRadius'
            ".cornerRadius(#{bound_number(value)})"
          when 'opacity', 'alpha'
            ".opacity(#{bound_number(value, cast: 'Double')})"
          when 'disabled'
            ".disabled(#{BindingExpression.swift_bool_expr(value[2..-2])})"
          # Size constraints
          when 'width'
            ".frame(width: #{bound_number(value)})"
          when 'height'
            ".frame(height: #{bound_number(value)})"
          when 'minWidth'
            ".frame(minWidth: #{bound_number(value)})"
          when 'maxWidth'
            ".frame(maxWidth: #{bound_number(value)})"
          when 'minHeight'
            ".frame(minHeight: #{bound_number(value)})"
          when 'maxHeight'
            ".frame(maxHeight: #{bound_number(value)})"
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

          # Color attributes.
          #
          # These pasted the bound PROPERTY into a `Color` slot, so a layout
          # writing `tintColor: "@{brand}"` against a String property emitted
          # `.tint(data.brand)` — no `@{` left in the output, and the build
          # dies on `cannot convert value of type 'String' to expected
          # argument type 'Color'`. `jui conformance codegen-effect` cannot
          # see it: the binding DID reach the output and the check asks
          # whether it survived, not whether it typechecks. It took compiling
          # the conformance host to find (plan 49, ios host stopped on
          # `common/tintColor__binding`). The same shape as the padding and
          # border branches above — a value context this class was not
          # emitting for.
          when 'tintColor'
            ".tint(#{get_swiftui_color(value)})"
          when 'tapBackground', 'highlightBackground'
            ".background(#{get_swiftui_color(value)})"
          # Border attributes are NOT handled here, for the reasons padding
          # is not (above): `BaseViewConverter#border_overlay` owns the whole
          # rule — what summons a border, what colour it falls back to, and
          # which stroke style it takes — and it reads the bound spelling
          # through the canonical emitters.
          #
          # Both branches here were wrong in the same two ways. `borderWidth`
          # emitted a stroke with NO colour, so a bound width drew in the
          # foreground colour rather than the declared one. `borderColor`
          # read the width with `.to_i`, which is 0 for a binding, so a bound
          # pair drew a zero-width border. And `:border` is a multi-value bag
          # key, so `register` replaced whatever the converter had already
          # put there.
          when 'clipToBounds'
            # This branch only ever runs for a BINDING (the guard at the top
            # of the method returns for anything else), and it emitted an
            # unconditional `.clipped()` — every bound clipToBounds clipped,
            # whatever the property said. `.clipped()` has no conditional form
            # of its own, so this had nowhere to put the condition.
            #
            # SwiftJsonUI grew `View.clipToBounds(_ enabled: Bool)` for it.
            # The flag is a PARAMETER rather than a call-site branch on
            # purpose: a branch here would freeze at whatever the generator
            # saw, while an argument is resolved at render time and tracks the
            # property.
            ".clipToBounds(#{BindingExpression.swift_bool_expr(value[2..-2])})"
          # User interaction
          when 'userInteractionEnabled', 'canTap'
            ".allowsHitTesting(#{BindingExpression.swift_bool_expr(value[2..-2])})"
          else
            nil
          end
        end

        # Handle specific bindings for each view type (override in subclasses)
        def handle_specific_binding(component, key, value)
          nil
        end

        # Resolve an ALREADY-PARSED binding expression to a Color.
        #
        # Kept for the two subclass handlers that call it with a parsed
        # expression rather than the raw value. It assumes the property is a
        # String naming a colour; `get_swiftui_color` is the fuller answer
        # (it reads the data section and passes a `Color`-typed property
        # through untouched) and is what the cases above use.
        def resolve_color_binding_expr(binding)
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