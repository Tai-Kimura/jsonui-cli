# frozen_string_literal: true

require_relative '../binding/binding_expression'

module SjuiTools
  module SwiftUI
    module Views
      # One declared attribute value, rendered as the Swift operand its
      # position needs.
      #
      # Every method here answers the same question in a different value
      # context: "the layout wrote `@{...}` here — what Swift goes in this
      # slot?". They all return nil for a value that is NOT a binding, so a
      # call site reads
      #
      #     add_line "fontSize: #{bound_number(@component['fontSize']) || @component['fontSize']},"
      #
      # and the static branch is textually the code it always was. That is
      # deliberate and is the property plan 49 has to hold: a declaration made
      # of numbers must emit the same bytes it emitted before, to the bit.
      #
      # This generalises what plan 43 built for margins
      # (`MarginExpressionHelper#margin_operand`, which now delegates here).
      # 43's finding was that the canonical parser already existed and the
      # dimension helpers were bypassing it; the same shape was then found in
      # kjui (`process_dimension`) and rjui. So there is no new parsing here —
      # every method below ends in one of `BindingExpression`'s canonical
      # value-context emitters, and no method in this file contains a regular
      # expression.
      #
      # The context matters because Swift's types do not forgive:
      #
      #   - a NUMBER slot cannot take an Optional (`CGFloat(data.x)` does not
      #     compile) and cannot take the raw text (`fontSize: @{v}` is not a
      #     program at all — 12 of plan 49's ios findings are exactly that);
      #   - a STRING slot compiles whatever you put in it, which is why the
      #     leak class exists: `Text("@{v}")` builds, runs, and shows the user
      #     the characters `@{v}`;
      #   - a BOOL slot is where Ruby's truthiness does the damage — `"@{x}"`
      #     is truthy, so `if @component['clipToBounds']` clipped every bound
      #     declaration unconditionally;
      #   - an ENUM slot has no runtime spelling at all unless the generator
      #     puts the vocabulary INTO the emitted Swift, which is what
      #     `bound_enum` does.
      module ValueExpressionHelper
        private

        def bound_value?(value)
          Binding::BindingExpression.binding?(value)
        end

        # The inner of `@{...}`. Callers must have checked `bound_value?`.
        def binding_inner(value)
          value[2..-2]
        end

        # A number slot: `CGFloat(data.size ?? 0)`.
        #
        # The cast is not cosmetic. A bound number may be declared Int or
        # Double in the data section and lands in a CGFloat/Double parameter;
        # the call also brackets the `?? default` an optional property unwraps
        # to, which `??`'s low precedence would otherwise leave dangling in
        # `0...data.max ?? 1`. Pass `cast: nil` only where the slot is
        # already a call and the parentheses are someone else's.
        def bound_number(value, cast: 'CGFloat')
          return nil unless bound_value?(value)

          # A dimension may be declared `["number", "string", "binding"]` —
          # `weight`, `fontWeight` and friends — and when the data section
          # takes the `string` half the property really is a String at run
          # time. `CGFloat(data.w)` does not compile then, and neither does
          # the `?? 0` the numeric emitter would append. Parse it instead.
          #
          # This is the same union-with-no-arbiter that split `fontWeight`
          # between the Data generator and the View generator; the data
          # section is the arbiter in both.
          expr = if string_property?(value)
                   text = Binding::BindingExpression.swift_text_expr(binding_inner(value))
                   "Double(#{text}) ?? 0"
                 else
                   Binding::BindingExpression.swift_number_expr(binding_inner(value))
                 end
          cast ? "#{cast}(#{expr})" : "(#{expr})"
        end

        # Whether the data section declares this bound property a String.
        # Reads the same thread-local store `BindingExpression.non_optional?`
        # and `ColorHelper` do.
        def string_property?(value)
          path = Binding::BindingExpression.parse(binding_inner(value)).path
          definition = (Thread.current[:sjui_data_definitions] || {})[path]
          !!(definition && definition['class'].to_s == 'String')
        end

        # A String slot: `data.title ?? ""`, bracketed.
        #
        # Canonically an unresolved text renders as the empty string, which is
        # what `swift_text_expr` emits. Negation has no meaning in a text
        # context and the canonical emitter returns nil for it; so does this,
        # which leaves the call site on its static branch rather than emitting
        # something that does not typecheck.
        def bound_string(value)
          return nil unless bound_value?(value)

          expr = Binding::BindingExpression.swift_text_expr(binding_inner(value))
          expr.nil? ? nil : "(#{expr})"
        end

        # A Bool slot: `(data.flag ?? false)`, already bracketed by the
        # canonical emitter for the optional case.
        def bound_bool(value)
          return nil unless bound_value?(value)

          expr = Binding::BindingExpression.swift_bool_expr(binding_inner(value))
          expr.start_with?('(') ? expr : "(#{expr})"
        end

        # A declared `weight` as `[does it apply?, the Swift operand]`.
        #
        # Weight is the one number here that also decides STRUCTURE — whether
        # the parent becomes a WeightedHStack, whether the child gets
        # matchParent on the main axis — and every one of those tests was
        # `value.to_f > 0`, which is 0 for a `@{...}`. So a bound weight did
        # not merely emit the wrong number: the container never became a
        # weighted stack at all and the child was laid out as if the
        # declaration were absent. The structural decision has to be made from
        # the PRESENCE of the declaration, the number only from its value.
        def weight_expression(value)
          bound = bound_number(value)
          return [true, bound] if bound
          return [false, 0.0] if value.nil?

          number = value.to_f
          [number > 0, number]
        end

        # An enum slot, resolved at RUN time by a dictionary the generator
        # writes into the Swift.
        #
        # *map* is the same `{ json spelling => swift literal }` table the
        # static path switches on, so the vocabulary keeps exactly one home —
        # copying it into the library is how the two spellings drift apart
        # (plan 40). Keys are compared lowercased on both sides, matching the
        # `.downcase` every static mapper here already does.
        #
        #   ["left": TextAlignment.leading, "center": .center][(data.a ?? "").lowercased()] ?? .leading
        #
        # *type* names the enum on the FIRST dictionary value so Swift can
        # infer the literal's type; the rest stay leading-dot. *default* is
        # the same fallback the static mapper uses for an unknown spelling;
        # pass `default: nil` to leave the lookup Optional, which is what a
        # slot that is itself Optional wants (and what lets a caller ask
        # "did this name a member of the vocabulary at all?").
        # Returns nil when the map is empty — a caller with nothing to map
        # has nothing to emit.
        def bound_enum(value, map, default:, type:)
          return nil unless bound_value?(value)
          return nil if map.nil? || map.empty?

          expr = Binding::BindingExpression.swift_text_expr(binding_inner(value))
          return nil if expr.nil?

          pairs = map.each_with_index.map do |(key, swift), index|
            literal = index.zero? ? "#{type}#{swift}" : swift
            "#{key.to_s.downcase.inspect}: #{literal}"
          end
          lookup = "[#{pairs.join(', ')}][(#{expr}).lowercased()]"
          default.nil? ? "(#{lookup})" : "(#{lookup} ?? #{default})"
        end
      end
    end
  end
end
