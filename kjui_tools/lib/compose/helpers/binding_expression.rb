# frozen_string_literal: true

module KjuiTools
  module Compose
    module Helpers
      # Canonical `@{...}` binding-expression parser + Kotlin emit helpers for
      # the Compose static codegen.
      #
      # SSoT: shared/core/binding_semantics.json (renderer SSoT track 15).
      # Grammar:  inner := path [ '??' default ] | '!' path
      #   - exactly ONE `??` per expression (more is a validator error;
      #     the parser splits on the FIRST `??` and the remainder fails the
      #     default-literal parse => treated as "no default" — fails closed
      #     to the context's unresolved behavior, matching the runtime rule)
      #   - default literal: double- OR single-quoted string, true/false,
      #     number, or null (null == "no default": unresolved falls through)
      #   - negation `!path` is only meaningful in boolean value contexts
      #     (validator enforces the context; emit helpers only produce a
      #     Kotlin `!` where the caller says the context is negatable)
      #
      # This class replaced four duplicated "split on ' ?? ' and silently
      # strip the default" implementations (compose_builder,
      # resource_resolver, textfield_component, textview_component) which
      # additionally disagreed about the `?: ""` fallback. The ONE canonical
      # rule now lives here:
      #
      #   * Nullability follows the generated data class: a data-section
      #     property WITHOUT a defaultValue is emitted by DataModelUpdater as
      #     `var x: T? = null` (nullable); WITH a defaultValue it is non-null.
      #   * Non-null access => plain `data.path`. The data-section
      #     defaultValue is merged before any `??` is reached (canonical
      #     fallbackPrecedence step 1), so an inline default there is dead —
      #     and `?:` on a non-null receiver is a Kotlin warning.
      #   * Nullable access in TEXT (string-interpolation) context always
      #     gets an explicit fallback: the authored `??` default when
      #     present, else `?: ""` (canonical unresolved-text => empty string;
      #     also prevents Kotlin printing the literal "null").
      #   * Nullable access in VALUE contexts gets `?: <default>` only when a
      #     `??` default was authored; with no default the plain (nullable)
      #     access is emitted and the component's own default applies
      #     (canonical unresolved-value => attribute default).
      #   * TWO-WAY contexts take the flat path only — `??`/`!`/dots are
      #     grammar violations there (binding-two-way-complex) and the
      #     validator reports them; emit stays the resolved path.
      class BindingExpression
        BINDING_RE = /@\{([^}]+)\}/.freeze
        WHOLE_BINDING_RE = /\A@\{[^}]+\}\z/.freeze
        FLAT_IDENTIFIER_RE = /\A[a-zA-Z_][a-zA-Z0-9_]*\z/.freeze
        # A path the emitters may put after `data.`: identifier segments,
        # dots, and array indices. Anything else — a space, an operator, an
        # empty inner — is not a path, and interpolating it produces code
        # that does not parse. Measured 2026-09-04: `@{ bad name }` emitted
        # `"${data.bad name ?: \"\"}"`, which is a Kotlin syntax error, from a
        # build that exited 0.
        PATH_RE = /\A[a-zA-Z_][a-zA-Z0-9_]*(?:\[[0-9]+\])?(?:\.[a-zA-Z_][a-zA-Z0-9_]*(?:\[[0-9]+\])?)*\z/.freeze

        Parsed = Struct.new(:path, :negated, :default, :has_default, keyword_init: true)

        class << self
          def whole_binding?(value)
            value.is_a?(String) && value.match?(WHOLE_BINDING_RE)
          end

          # First `@{...}` inner expression of a string, or nil.
          def extract_inner(value)
            return nil unless value.is_a?(String)
            m = value.match(BINDING_RE)
            m && m[1]
          end

          # Parse a canonical inner expression (the text between @{ and }).
          def parse(inner)
            s = inner.to_s.strip
            negated = s.start_with?('!')
            s = s[1..].to_s.strip if negated

            path = s
            default = nil
            has_default = false
            if s.include?('??')
              lhs, rhs = s.split('??', 2)
              path = lhs.strip
              lit, valid = parse_default_literal(rhs.strip)
              if valid
                default = lit
                has_default = true
              end
            end
            Parsed.new(path: path, negated: negated, default: default, has_default: has_default)
          end

          # => [value, valid?]. `null` and anything unparseable (including a
          # second `??`) count as "no default".
          def parse_default_literal(raw)
            return [nil, false] if raw.nil? || raw.empty? || raw.include?('??')

            case raw
            when /\A"(.*)"\z/m then [Regexp.last_match(1), true]
            when /\A'(.*)'\z/m then [Regexp.last_match(1), true]
            when 'true' then [true, true]
            when 'false' then [false, true]
            when 'null' then [nil, false]
            when /\A-?\d+\z/ then [raw.to_i, true]
            when /\A-?\d+\.\d+\z/ then [raw.to_f, true]
            else [nil, false]
            end
          end

          # Mirrors DataModelUpdater: no data-section defaultValue => the
          # generated property is nullable (`var x: T? = null`). Dot-paths /
          # bracket paths have no matching data definition and therefore
          # count as nullable, matching the pre-existing process_text rule.
          def property_nullable?(path)
            !ResourceResolver.has_default_value?(path)
          end

          # C1 text (string interpolation). Returns the full quoted Kotlin
          # string literal, e.g. "\"${data.name ?: \"Guest\"}\"".
          # True when the parsed path can be emitted as Kotlin. False means
          # the author wrote something that is not a property path.
          def emittable_path?(path)
            path.to_s.match?(PATH_RE)
          end

          def interpolated_access(inner)
            p = parse(inner)
            # Not a path: emit the author's own text as a literal instead of
            # invalid Kotlin. The build still reports the finding; what it
            # must not do is write a file that cannot be parsed.
            return quote("@{#{inner}}") unless emittable_path?(p.path)

            base = "data.#{p.path}"
            if !property_nullable?(p.path)
              "\"${#{base}}\""
            elsif p.has_default
              "\"${#{base} ?: #{kotlin_literal(p.default)}}\""
            else
              "\"${#{base} ?: \"\"}\""
            end
          end

          # C2 value (typed whole-value binding). Returns a bare Kotlin
          # expression. Pass negatable: true for boolean value contexts so
          # `@{!flag}` emits a real Kotlin negation (`!data.flag`).
          def value_access(inner, negatable: false)
            p = parse(inner)
            # Same rule as the text context, one step weaker: there is no
            # literal that fits every value position, so emit the safest
            # compilable thing for the shape asked for. Either way the
            # generated file parses.
            unless emittable_path?(p.path)
              return negatable ? 'false' : quote("@{#{inner}}")
            end

            base = "data.#{p.path}"
            expr =
              if p.has_default && property_nullable?(p.path)
                "(#{base} ?: #{kotlin_literal(p.default)})"
              else
                base
              end

            if p.negated && negatable
              # `!` needs a non-null Boolean receiver; coerce a bare nullable
              # access so the emitted Kotlin always compiles.
              expr = "(#{base} ?: false)" if expr == base && property_nullable?(p.path)
              "!#{expr}"
            else
              # Negation outside a boolean value context is a validator error
              # (binding-negation-context); emit the un-negated access so the
              # generated code still compiles (fails soft, matching the
              # runtime's fall-through-to-unresolved rule as closely as a
              # static emit can).
              expr
            end
          end

          # C5 two-way. Grammar restricts these to a single flat identifier;
          # violations are validator errors (binding-two-way-complex). Emit
          # tolerantly returns the parsed path (default/negation stripped).
          def two_way_path(inner)
            parse(inner).path
          end

          # C3 params-leaf and other path-only contexts (defaults/negation
          # are validator errors there; emit keeps the resolved path).
          alias_method :path_only, :two_way_path

          def kotlin_literal(value)
            case value
            when String then quote(value)
            when true, false, Integer, Float then value.to_s
            else quote(value.to_s)
            end
          end

          def quote(text)
            escaped = text.to_s.gsub('\\', '\\\\\\\\')
                          .gsub('"', '\\"')
                          .gsub("\n", '\\n')
                          .gsub("\r", '\\r')
                          .gsub("\t", '\\t')
            "\"#{escaped}\""
          end
        end
      end
    end
  end
end
