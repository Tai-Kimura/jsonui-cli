# frozen_string_literal: true

require_relative 'binding_expression'
# BindingExpression#property_nullable? calls ResourceResolver but does not
# require it (the cycle resource_resolver -> binding_expression means it
# cannot). Pulling it in here keeps every BoundValue caller safe regardless of
# which helper it loaded first.
require_relative 'resource_resolver'

module KjuiTools
  module Compose
    module Helpers
      # Canonical typed Kotlin emitters for attribute values that MAY be a
      # `@{...}` binding.
      #
      # Why this exists (plan 49 lane C). The Compose codegen read attribute
      # values with plain Ruby operators:
      #
      #   ".padding(top = #{json_data['paddingTop']}.dp)"   # => `@{v}.dp`  — not a program
      #   if json_data['alignTop']                          # => `"@{v}"` is truthy — frozen ON
      #   json_data['weight'].to_f > 0                      # => `"@{v}".to_f == 0.0` — branch lost
      #   json_data['font'].downcase == 'bold'              # => never matches — frozen to Normal
      #
      # 41 confirmed 51 defects of that shape on android alone. The tool was
      # already there — `BindingExpression` parses the canonical grammar and
      # knows the nullability rule — it just was not on these paths. Rather
      # than teach every component the vocabulary again (40: "duplicated
      # vocabulary always drifts"), every value context now goes through ONE
      # of the emitters below.
      #
      # Two rules the emitters keep:
      #
      #   1. **Static declarations emit exactly what they emitted before.**
      #      A numeric/boolean literal never reaches BindingExpression; the
      #      binding branch is additive. Regressions pin this.
      #   2. **Emitters take VALUES, never attribute names.** `jui conformance
      #      coverage` (jui_cli/conformance/coverage.py) scans sources for the
      #      literal `json_data['x']`, so the literal has to stay at the call
      #      site. `BoundValue.dp(json_data['paddingTop'])` is visible to the
      #      scanner; `BoundValue.dp(json_data, 'paddingTop')` would not be.
      #
      # Nullability: a data-section property WITHOUT a `defaultValue` is
      # generated as `var x: T? = null`, so every emit that would dereference
      # it coalesces. `.dp` / `.sp` use the `x?.dp ?: N.dp` shape rather than
      # `(x ?: N).dp` on purpose — the data class may declare Int or Double
      # and `Double? ?: Int` widens to `Comparable & Number`, on which `.dp`
      # does not resolve. `Int.dp` / `Float.dp` / `Double.dp` all yield `Dp`,
      # so the chosen shape compiles for every declared numeric type.
      module BoundValue
        module_function

        # True when the value carries a `@{...}` expression anywhere.
        def bound?(value)
          value.is_a?(String) && !BindingExpression.extract_inner(value).nil?
        end

        # Dp expression, or nil when the value is absent.
        #
        # `fallback:` is the value used when a nullable property resolves to
        # null and the author wrote no `?? default`. **It must not collide with
        # a value the attribute already gives a meaning to.** `0` is right for
        # a padding (no padding) and wrong for a `maxWidth` (a 0dp cap
        # annihilates the view), so bounded-maximum callers pass
        # `null_expr: 'Dp.Infinity'` and text sizes pass
        # `TextUnit.Unspecified`. Plan 49 lane C, from B's lane: a fallback
        # that happens to be the attribute's own "unset" sentinel turns every
        # unresolved binding into a silent, wrong declaration.
        def dp(value, fallback: 0, null_expr: nil)
          unit_value(value, 'dp', fallback, null_expr)
        end

        # Sp (text unit) expression, or nil when the value is absent.
        def sp(value, fallback: 0, null_expr: nil)
          unit_value(value, 'sp', fallback, null_expr)
        end

        def unit_value(value, unit, fallback, null_expr = nil)
          return nil if value.nil? || value == ''
          return "#{value}.#{unit}" unless bound?(value)

          inner = BindingExpression.extract_inner(value)
          p = BindingExpression.parse(inner)
          base = "data.#{p.path}"
          return "#{base}.#{unit}" unless BindingExpression.property_nullable?(p.path)

          unresolved =
            if p.has_default && p.default.is_a?(Numeric)
              "#{p.default}.#{unit}"
            else
              null_expr || "#{fallback}.#{unit}"
            end
          "(#{base}?.#{unit} ?: #{unresolved})"
        end

        # Kotlin `Float` expression, or nil when the value is absent.
        def float(value, fallback: 0)
          return nil if value.nil? || value == ''
          # Raw spelling, not `to_f`: `1` must stay `1f`, not become `1.0f`.
          # Static output has to be byte-identical to the pre-guard emit.
          return "#{value}f" unless bound?(value)

          inner = BindingExpression.extract_inner(value)
          p = BindingExpression.parse(inner)
          base = "data.#{p.path}"
          return "#{base}.toFloat()" unless BindingExpression.property_nullable?(p.path)

          default = p.has_default && p.default.is_a?(Numeric) ? p.default : fallback
          "(#{base}?.toFloat() ?: #{default.to_f}f)"
        end

        # Kotlin `Int` expression, or nil when the value is absent.
        def int(value, fallback: 0)
          return nil if value.nil? || value == ''
          return value.to_i.to_s unless bound?(value)

          inner = BindingExpression.extract_inner(value)
          p = BindingExpression.parse(inner)
          base = "data.#{p.path}"
          return base unless BindingExpression.property_nullable?(p.path)

          default = p.has_default && p.default.is_a?(Numeric) ? p.default.to_i : fallback.to_i
          "(#{base} ?: #{default})"
        end

        # A boolean|binding attribute, resolved into one of three states:
        #
        #   :on     — statically true (emit the modifier unconditionally)
        #   :off    — absent or statically false (emit nothing)
        #   String  — a Kotlin Boolean expression to decide at runtime
        #
        # Everything that used to be spelled `if json_data['alignTop']` is a
        # `case bool(...)` now; a `@{...}` no longer freezes the flag ON.
        def bool(value)
          return :off if value.nil? || value == false || value == 'false'
          return :on if value == true || value == 'true'

          unless bound?(value)
            # Non-binding, non-boolean scalar. Ruby truthiness is what every
            # caller used before; keep it so static output is unchanged.
            return :on
          end

          inner = BindingExpression.extract_inner(value)
          p = BindingExpression.parse(inner)
          # `value_access` already coalesces a NEGATED nullable access (`!`
          # needs a non-null receiver); a plain nullable read still hands back
          # a `Boolean?`, which no `if`/`when` guard accepts.
          if !p.negated && BindingExpression.property_nullable?(p.path)
            default = p.has_default && (p.default == true || p.default == false) ? p.default : false
            "(data.#{p.path} ?: #{default})"
          else
            BindingExpression.value_access(inner, negatable: true)
          end
        end

        # Conjunction of #bool states, staying in the same three-valued
        # domain. A single static `:off` collapses the whole conjunction, so
        # an all-static tree never grows a runtime branch.
        def all_of(*states)
          return :off if states.any? { |s| s == :off }

          dynamic = states.reject { |s| s == :on }
          return :on if dynamic.empty?
          return dynamic.first if dynamic.length == 1

          "(#{dynamic.join(' && ')})"
        end

        # A quoted Kotlin String expression for a text-position value. A
        # binding becomes a real interpolation instead of the characters
        # `@{...}` reaching the screen.
        def text(value)
          str = value.to_s
          return BindingExpression.quote(str) unless bound?(value)
          return BindingExpression.interpolated_access(str[2..-2]) if BindingExpression.whole_binding?(str)

          # Mixed literal + binding. Escape the literal runs, splice the
          # `${…}` accesses between them (`interpolated_access` hands back a
          # full quoted literal, so drop its own quotes).
          out = +''
          cursor = 0
          str.scan(BindingExpression::BINDING_RE) do
            m = Regexp.last_match
            out << escaped_run(str[cursor...m.begin(0)])
            out << BindingExpression.interpolated_access(m[1])[1..-2]
            cursor = m.end(0)
          end
          out << escaped_run(str[cursor..])
          "\"#{out}\""
        end

        # The escaping half of BindingExpression.quote, without the quotes.
        def escaped_run(segment)
          return '' if segment.nil? || segment.empty?
          BindingExpression.quote(segment)[1..-2]
        end

        # A vocabulary attribute (`contentMode`, `textAlign`, `fontWeight`, …).
        #
        #   mapping  — { json spelling => Kotlin constant }
        #   default  — Kotlin constant used for an unknown / unresolved value
        #
        # Static input picks from the map exactly as the old `case`/`==`
        # chains did. A binding emits the whole map as a Kotlin `when` so the
        # declared value is honoured at runtime instead of collapsing to the
        # default (which is what a `==` against `"@{v}"` always did).
        # Returns nil when the value is absent, or when a static value is
        # outside the vocabulary and no default was supplied.
        # `lowercase:` mirrors a static path that folded case before looking the
        # value up (the font-weight table does). Without it the runtime `when`
        # would be case-sensitive where the static emit was not.
        # `bound_default:` is the `else` arm for the runtime `when`, for the
        # common case where an unknown STATIC value should emit nothing (the
        # attribute falls back to the component default) but a `when` used as
        # an expression still needs an exhaustive else to compile. Without any
        # usable else the bound case returns nil rather than shipping a
        # non-compiling `when` — the binding is dropped, which is the canonical
        # unresolved-value behaviour and strictly better than a build failure.
        def enum(value, mapping, default: nil, bound_default: nil, lowercase: false)
          return nil if value.nil? || value == ''

          unless bound?(value)
            key = value.to_s
            key = key.downcase if lowercase
            return mapping[key] || default
          end

          else_arm = bound_default || default
          return nil unless else_arm

          inner = BindingExpression.extract_inner(value)
          p = BindingExpression.parse(inner)
          access = "data.#{p.path}"
          # `toString()` first: the property may not be a String. `fontWeight`
          # declares `["string", "number", "binding"]`, so `data.x.lowercase()`
          # does not resolve when the layout bound it to an Int — a type error
          # that no amount of `@{...}` analysis can see, because the spelling
          # carries no type.
          access = "#{access}?.toString()?.lowercase()" if lowercase
          subject = if BindingExpression.property_nullable?(p.path) || lowercase
                      fallback = p.has_default && p.default.is_a?(String) ? p.default : ''
                      "#{access} ?: #{BindingExpression.quote(fallback)}"
                    else
                      access
                    end

          branches = mapping.map { |k, v| "#{BindingExpression.quote(k)} -> #{v}" }
          branches << "else -> #{else_arm}"
          "when (#{subject}) { #{branches.join('; ')} }"
        end

        # Wrap a Modifier fragment in a runtime condition. `state` is a value
        # returned by #bool.
        #
        #   :on     -> the fragment itself
        #   :off    -> nil
        #   String  -> `.then(if (<expr>) Modifier<fragment> else Modifier)`
        #
        # `Modifier.then(other)` keeps Scope-receiver extensions (`.align`,
        # `.weight`) resolving, because the expression is evaluated at the
        # call site — inside the RowScope/ColumnScope/BoxScope content lambda.
        def conditional_modifier(state, fragment)
          case state
          when :on then fragment
          when :off then nil
          else ".then(if (#{state}) Modifier#{fragment} else Modifier)"
          end
        end

        # Fold a priority-ordered [condition, result] list.
        #
        # `conditions` are #bool states. When every one of them is static the
        # list is resolved in Ruby and the winning result is returned as-is —
        # byte-identical to the old if/elsif chain. As soon as one is a
        # runtime expression the whole chain becomes a Kotlin `when`, which
        # preserves the SAME priority order.
        #
        # Returns nil when nothing matches (and no `else_result` was given).
        def priority_when(pairs, else_result: nil)
          return else_result if pairs.empty?

          if pairs.all? { |state, _| state == :on || state == :off }
            hit = pairs.find { |state, _| state == :on }
            return hit ? hit[1] : else_result
          end

          branches = []
          pairs.each do |state, result|
            next if state == :off
            if state == :on
              # A statically-true guard ends the chain: nothing after it can
              # be reached, exactly as in the if/elsif form.
              branches << "else -> #{result}"
              return "when { #{branches.join('; ')} }"
            end
            branches << "#{state} -> #{result}"
          end
          branches << "else -> #{else_result || 'null'}"
          "when { #{branches.join('; ')} }"
        end

        # `priority_when` over Modifier fragments: the else arm is a bare
        # `Modifier`, and the result is spliced into a chain with `.then(...)`.
        def priority_modifier(pairs)
          return nil if pairs.empty?

          if pairs.all? { |state, _| state == :on || state == :off }
            hit = pairs.find { |state, _| state == :on }
            return hit ? hit[1] : nil
          end

          branches = []
          pairs.each do |state, fragment|
            next if state == :off
            if state == :on
              branches << "else -> Modifier#{fragment}"
              return ".then(when { #{branches.join('; ')} })"
            end
            branches << "#{state} -> Modifier#{fragment}"
          end
          return nil if branches.empty?

          branches << 'else -> Modifier'
          ".then(when { #{branches.join('; ')} })"
        end
      end
    end
  end
end
