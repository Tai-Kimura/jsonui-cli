# frozen_string_literal: true

require_relative '../binding/binding_expression'

module SjuiTools
  module SwiftUI
    module Views
      # Rendering one margin as Swift, shared by the two helpers that do
      # arithmetic on margins: PositioningHelper takes the DIFFERENCE of
      # two opposing margins as a ZStack child's .offset, SpacingHelper
      # keeps what the pair SHARES as padding (semantics.margins). Both
      # end up in the same converter class, so this lives in one module
      # rather than twice — a second copy is how the two drift.
      #
      # Margins are declared `["number", "binding"]`. Only the numeric
      # spelling has a value at generation time; a binding becomes an
      # expression, because `.offset` and `.padding` take expressions and
      # the generator's own convenience is not a reason to reject a
      # declaration the SSoT allows.
      module MarginExpressionHelper
        private

        # A margin that is already a number here — the numeric spelling
        # and the numeric-string spelling both are. nil for a binding or
        # anything unparseable.
        def margin_number(value)
          return value if value.is_a?(Numeric)
          return value.to_i if value.is_a?(String) && value.match?(/\A-?\d+\z/)

          nil
        end

        # One margin as a Swift operand. CGFloat() rather than the bare
        # property because a bound margin may be declared Int or Double
        # and this lands in CGFloat arithmetic — and because the call
        # brackets the '?? default' an optional property unwraps to.
        # Parsing goes through the canonical binding emitter so a margin
        # sees the same path, default and optionality rules as every other
        # bound value. An undeclared or unparseable margin is 0, matching
        # the library's marginValueToCGFloat.
        def margin_operand(value)
          number = margin_number(value)
          return number.to_s if number
          return '0' unless Binding::BindingExpression.binding?(value)

          "CGFloat(#{Binding::BindingExpression.swift_number_expr(value[2..-2])})"
        end
      end
    end
  end
end
