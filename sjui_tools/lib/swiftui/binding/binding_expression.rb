# frozen_string_literal: true

module SjuiTools
  module SwiftUI
    module Binding
      # Canonical parser + Swift emitters for '@{...}' binding expressions.
      #
      # Grammar (shared/core/binding_semantics.json):
      #   inner := path [ '??' default ] | '!' path
      #   path  := identifier segments joined by '.', optional bracket index
      #   default := "str" | 'str' | true | false | number | null
      #
      # Exactly one '??' is canonical; runtimes split on the FIRST '??' only.
      # 'null' (and any unparseable literal — fails closed) is treated as
      # "no default" (unresolved falls through to the context behavior).
      module BindingExpression
        Parsed = Struct.new(:path, :negated, :default_kind, :default_value, keyword_init: true)

        module_function

        def binding?(value)
          value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')
        end

        # Parse the inner of an '@{...}' expression (without the delimiters).
        def parse(inner)
          s = inner.to_s.strip
          negated = false
          if s.start_with?('!')
            negated = true
            s = s[1..].to_s.strip
          end
          idx = s.index('??')
          if idx
            path = s[0...idx].strip
            raw_default = s[(idx + 2)..].to_s.strip
            kind, value = parse_default_literal(raw_default)
          else
            path = s
            kind = :none
            value = nil
          end
          Parsed.new(path: path, negated: negated, default_kind: kind, default_value: value)
        end

        # Classify a default literal. Single- OR double-quoted strings are
        # canonical; single quotes are normalized away here (Swift emits ").
        def parse_default_literal(raw)
          return [:none, nil] if raw.nil? || raw.empty?

          if (m = raw.match(/\A"(.*)"\z/m)) || (m = raw.match(/\A'(.*)'\z/m))
            [:string, m[1]]
          elsif raw == 'true' || raw == 'false'
            [:bool, raw]
          elsif raw == 'null'
            [:null, nil]
          elsif raw.match?(/\A-?\d+(\.\d+)?\z/)
            [:number, raw]
          else
            # Unparseable default fails closed to unresolved (canonical arity
            # rule: the remainder after the first '??' that doesn't parse as a
            # literal yields no default).
            [:null, nil]
          end
        end

        # Swift literal for the parsed default, or nil when none/null.
        def swift_default_literal(parsed)
          case parsed.default_kind
          when :string
            escaped = parsed.default_value.gsub('\\', '\\\\\\\\').gsub('"', '\\"')
            "\"#{escaped}\""
          when :bool, :number
            parsed.default_value
          end
        end

        # True when the generated data property is non-optional (has a
        # data-section defaultValue). Canonical fallback precedence merges the
        # data-section defaultValue BEFORE any inline '??' is reached, so for
        # a non-optional property the inline default is dead code.
        # Reads the same thread-local store as Views::ColorHelper
        # .data_definitions (set during build) without requiring it, to keep
        # this module dependency-free.
        def non_optional?(path)
          definitions = Thread.current[:sjui_data_definitions] || {}
          definition = definitions[path]
          !!(definition && !definition['defaultValue'].nil?)
        end

        # Read-only Swift value expression for a whole-value binding.
        # Boolean negation emits '!' (wrapping optionals so it always
        # compiles); inline defaults emit '?? <literal>' only for optional
        # properties (dead code otherwise, see non_optional?).
        def swift_value_expr(inner, prefix: 'data')
          parsed = parse(inner)
          base = "#{prefix}.#{parsed.path}"

          if parsed.negated
            return "!#{base}" if non_optional?(parsed.path)
            fallback = swift_default_literal(parsed) || 'false'
            return "!(#{base} ?? #{fallback})"
          end

          default = swift_default_literal(parsed)
          if default && !non_optional?(parsed.path)
            "#{base} ?? #{default}"
          else
            base
          end
        end

        # Swift expression for a boolean value context (hidden, bool
        # conditions). Optional properties are unwrapped with the inline
        # default (or false) so the emitted condition always compiles.
        def swift_bool_expr(inner, prefix: 'data')
          parsed = parse(inner)
          base = "#{prefix}.#{parsed.path}"
          if non_optional?(parsed.path)
            parsed.negated ? "!#{base}" : base
          else
            fallback = swift_default_literal(parsed) || 'false'
            parsed.negated ? "!(#{base} ?? #{fallback})" : "(#{base} ?? #{fallback})"
          end
        end

        # Swift expression for one '@{...}' occurrence in a text context
        # (string interpolation position). Optional properties keep the
        # historical '?? ""' fallback (canonical: unresolved text renders as
        # the empty string). Returns nil for negation — not valid in text
        # contexts; canonical runtimes treat the token as unresolved.
        def swift_text_expr(inner, prefix: 'data')
          parsed = parse(inner)
          return nil if parsed.negated

          base = "#{prefix}.#{parsed.path}"
          return base if non_optional?(parsed.path)

          default = swift_default_literal(parsed) || '""'
          "#{base} ?? #{default}"
        end

        # Swift expression for a two-way Binding<T> position. Canonically the
        # inner must be a single flat identifier; defaults/negation are
        # validator errors (binding-two-way-complex) — the path alone is
        # emitted so the generated Swift stays valid either way.
        def swift_two_way_expr(inner, prefix: '$data')
          parsed = parse(inner)
          "#{prefix}.#{parsed.path}"
        end

        # Swift expression for the VisibilityWrapper parameter (String-typed
        # visibility enum: visible/invisible/gone). Value may be a literal
        # string, a String-property binding, or (non-canonical, validator
        # error) a negated bool binding — bridged to a visible/gone ternary so
        # the emitted Swift still compiles.
        def swift_visibility_param(value, prefix: 'data')
          return "\"#{value}\"" unless binding?(value)

          inner = value[2..-2]
          parsed = parse(inner)
          base = "#{prefix}.#{parsed.path}"

          if parsed.negated
            bool_expr = non_optional?(parsed.path) ? "!#{base}" : "!(#{base} ?? false)"
            return "#{bool_expr} ? \"visible\" : \"gone\""
          end

          default = swift_default_literal(parsed)
          if default && !non_optional?(parsed.path)
            "#{base} ?? #{default}"
          else
            base
          end
        end
      end
    end
  end
end
