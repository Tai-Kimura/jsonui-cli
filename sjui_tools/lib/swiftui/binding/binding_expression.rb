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

        # A path the emitters may put after `data.`: identifier segments,
        # dots, and array indices. Anything else — a space, an operator, an
        # empty inner — is not a path, and interpolating it produces code
        # that does not compile. Measured 2026-09-04: `@{ bad name }` emitted
        # "\(data.bad name ?? \"\")", which `swiftc -parse` rejects, from a
        # build that exited 0 and reported only "undefined variable".
        PATH_RE = /\A[a-zA-Z_][a-zA-Z0-9_]*(?:\[[0-9]+\])?(?:\.[a-zA-Z_][a-zA-Z0-9_]*(?:\[[0-9]+\])?)*\z/.freeze

        # True when the parsed path can be emitted as Swift.
        def emittable_path?(path)
          path.to_s.match?(PATH_RE)
        end

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

        # A Swift string literal carrying the author's own text.
        def swift_literal_for(text)
          escaped = text.to_s.gsub('\\', '\\\\').gsub('"', '\\"')
          "\"#{escaped}\""
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

        def data_definitions
          Thread.current[:sjui_data_definitions] || {}
        end

        # Declared classes whose Swift type is an UNTYPED JSON container
        # ([String: Any] / [Any]).
        #
        # A second copy of Core::TypeConverter::JSON_CONTAINER_CLASSES, which
        # decides the spelling these paths are read through. Deliberate: that
        # module requires config_manager and project_finder, and this one is
        # kept free of anything that touches the filesystem. The two lists are
        # asserted equal in spec/swiftui/binding/container_path_binding_spec.rb
        # so adding a class on one side fails rather than drifts.
        JSON_CONTAINER_CLASSES = %w[Object object Hash hash Array array].freeze

        def path_root(path)
          path.to_s[/\A[a-zA-Z_][a-zA-Z0-9_]*/]
        end

        # True when the path reads THROUGH an untyped JSON container rather
        # than naming one declared property.
        #
        # `data.profile.name` is not Swift when `profile` is `[String: Any]`:
        # a dictionary has no member `name`, and `items[0].title` has no
        # member `title` on `Any`. The declared CLASS of the root decides —
        # a project model type keeps plain member access, which is what it
        # has always had and what still compiles.
        #
        # The whole path is checked against the store first: a property may
        # legitimately be *named* with dots (the canonical FLAT-key rule,
        # DynamicBindingResolver.lookupRaw), and that one is a declared
        # property, not a traversal.
        def container_traversal?(path)
          text = path.to_s
          return false unless emittable_path?(text)

          definitions = data_definitions
          return false if definitions.key?(text)

          root = path_root(text)
          return false if root.nil? || root == text

          klass = definitions.fetch(root, {})['class'].to_s.sub(/\?\z/, '')
          JSON_CONTAINER_CLASSES.include?(klass)
        end

        # A Swift string literal. Written with block replacements: gsub with
        # a STRING replacement reads a backslash pair as a back-reference and
        # emits one backslash where two were meant.
        def swift_string_literal(str)
          escaped = str.to_s.gsub(0x5c.chr) { 0x5c.chr * 2 }
                        .gsub(0x22.chr) { 0x5c.chr + 0x22.chr }
          0x22.chr + escaped + 0x22.chr
        end

        # Read the path through the canonical resolver rather than deriving a
        # subscript chain here.
        #
        # ⚠️ The type named MUST be `JsonUIBindingPath`, never
        # `DynamicBindingResolver`. The latter is inside `#if DEBUG`, and
        # generated code is distributed and built for RELEASE: referencing it
        # compiles under DEBUG — so every gate goes green — and breaks in the
        # consumer's release build. Measured 2026-09-05: the conformance host
        # compiles SwiftJsonUI with DEBUG undefined and failed five views with
        # "Type 'SwiftJsonUI' has no member 'DynamicBindingResolver'".
        # `JsonUIBindingPath` exists outside the guard for exactly this
        # caller, and requires SwiftJsonUI >= 10.20.1.
        #
        # Calling it keeps ONE implementation of the rules a hand-written
        # chain would have to restate: an out-of-range index is unresolved and
        # not a trap, the flat key "a.b" shadows the nested path, an integral
        # Double renders "1" and not "1.0", and a container has no text form
        # (interpolating one would render '["name": "Grace"]' into the UI).
        #
        # The container is passed as a one-key map under its own root name, so
        # the resolver sees the shape it sees on the dynamic face. The
        # `as Any` is not decoration: an optional container would otherwise be
        # implicitly coerced to Any, which is a warning, and the build gate
        # requires zero warnings.
        def canonical_resolve_expr(path, coercion, prefix: 'data')
          root = path_root(path)
          lookup = 'SwiftJsonUI.JsonUIBindingPath.resolve(' \
                   "path: #{swift_string_literal(path)}, " \
                   "in: [#{swift_string_literal(root)}: #{prefix}.#{root} as Any])"
          "SwiftJsonUI.JsonUIBindingPath.#{coercion}(#{lookup})"
        end

        # Canonical text form of a number literal, mirroring
        # JsonUIBindingPath.stringify: integral values render without a
        # fractional part, so `?? 42` and a resolved 42 read the same.
        def canonical_number_text(raw)
          value = raw.to_f
          return value.truncate.to_s if value == value.truncate && value.abs < 1e15

          value.to_s
        end

        # The '??' default as a Swift literal for a TEXT position. The
        # release-available core is path resolution and coercion only — it
        # carries no expression parser — so the default is applied here. It
        # has already been parsed, so nothing is lost, but it has to be
        # rendered the canonical way rather than passed through.
        def text_default_literal(parsed)
          case parsed.default_kind
          when :string then swift_default_literal(parsed)
          when :bool then swift_string_literal(parsed.default_value.to_s)
          when :number then swift_string_literal(canonical_number_text(parsed.default_value))
          end
        end

        # The Swift kind a declared class coerces to, or nil when the class
        # is a project model type (nothing can be said about its literals).
        def declared_kind(path)
          klass = data_definitions.fetch(path.to_s, {})['class'].to_s.sub(/\?\z/, '')
          case klass
          when 'String', 'string' then :string
          when 'Int', 'int', 'Double', 'double', 'Float', 'float', 'CGFloat',
               'Number', 'number' then :number
          when 'Bool', 'bool', 'Boolean', 'boolean' then :bool
          end
        end

        # The inline default has to have the DECLARED type of the property:
        # '??' is a Swift coalesce, not a text substitution. A number written
        # against a String property emitted `data.name ?? 42`, which is
        # "cannot convert Int to String" — the expression was well-formed and
        # still did not compile.
        #
        # Returns nil when the mismatch cannot be repaired by quoting, so the
        # caller falls back to its own context literal rather than emitting a
        # coalesce whose two sides have different types.
        def coerced_default_literal(parsed)
          literal = swift_default_literal(parsed)
          return nil if literal.nil?

          kind = declared_kind(parsed.path)
          return literal if kind.nil? || kind == parsed.default_kind

          # Everything has a canonical text form; nothing else converts.
          return swift_string_literal(parsed.default_value.to_s) if kind == :string

          nil
        end

        # Resolver and fallback per value KIND, for container paths.
        RESOLVER_BY_KIND = {
          string: %w[stringify ""],
          bool: %w[bool false],
          number: %w[double 0]
        }.freeze

        # Read-only Swift value expression for a whole-value binding.
        # Boolean negation emits '!' (wrapping optionals so it always
        # compiles); inline defaults emit '?? <literal>' only for optional
        # properties (dead code otherwise, see non_optional?).
        #
        # `kind` selects the resolver for a CONTAINER path only; every other
        # path is emitted identically whatever it says. This one method feeds
        # three different Swift types — `isEnabled:` is Bool, relative
        # positioning is numeric, hint / colour hex / url are String — so the
        # caller names the type it is about to consume. Defaulting to :string
        # rather than requiring it keeps the generic callers working.
        def swift_value_expr(inner, prefix: 'data', kind: :string)
          parsed = parse(inner)
          return swift_literal_for("@{#{inner}}") unless emittable_path?(parsed.path)

          # Emitting the literal token here instead COMPILES, which is worse
          # than failing: the view renders "@{profile.name}" as its own text
          # and every gate stays green. Resolve it.
          if container_traversal?(parsed.path)
            coercion, fallback = RESOLVER_BY_KIND.fetch(kind, RESOLVER_BY_KIND[:string])
            call = canonical_resolve_expr(parsed.path, coercion, prefix: prefix)
            default = kind == :string ? text_default_literal(parsed) : swift_default_literal(parsed)
            return "(#{call} ?? #{default || fallback})"
          end

          base = "#{prefix}.#{parsed.path}"

          if parsed.negated
            return "!#{base}" if non_optional?(parsed.path)
            fallback = coerced_default_literal(parsed) || 'false'
            return "!(#{base} ?? #{fallback})"
          end

          default = coerced_default_literal(parsed)
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
          # No literal fits every value position; `false` is the safest
          # compilable thing in a boolean one.
          return 'false' unless emittable_path?(parsed.path)

          # Negation is applied here: the release-available core coerces a
          # value, it does not parse '!path'.
          if container_traversal?(parsed.path)
            call = canonical_resolve_expr(parsed.path, 'bool', prefix: prefix)
            fallback = parsed.default_kind == :bool ? swift_default_literal(parsed) : 'false'
            resolved = "(#{call} ?? #{fallback})"
            return parsed.negated ? "!#{resolved}" : resolved
          end

          base = "#{prefix}.#{parsed.path}"
          if non_optional?(parsed.path)
            parsed.negated ? "!#{base}" : base
          else
            fallback = coerced_default_literal(parsed) || 'false'
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
          # Not a path: refuse rather than emit code that will not compile.
          # Callers already have a no-expression branch.
          return nil unless emittable_path?(parsed.path)

          if container_traversal?(parsed.path)
            call = canonical_resolve_expr(parsed.path, 'stringify', prefix: prefix)
            return "(#{call} ?? #{text_default_literal(parsed) || '""'})"
          end

          base = "#{prefix}.#{parsed.path}"
          return base if non_optional?(parsed.path)

          default = coerced_default_literal(parsed) || '""'
          "#{base} ?? #{default}"
        end

        # Swift expression for a NUMERIC value context — a bound margin
        # that lands in CGFloat arithmetic, and anything else that has to
        # be a number rather than merely be displayed. Optional properties
        # are unwrapped with the inline default (or 0) because an Optional
        # cannot be subtracted or passed to min(); a non-numeric inline
        # default is not a number either, so it falls back to 0.
        #
        # No outer parentheses, same as swift_text_expr: '??' binds looser
        # than arithmetic, so a caller placing this in an expression must
        # bracket it (CGFloat(...) already does).
        def swift_number_expr(inner, prefix: 'data')
          parsed = parse(inner)
          # The other three contexts refuse a non-path; this one did not, and
          # interpolating one emits Swift that does not compile. Same defect,
          # same fail-closed answer: the context's own literal.
          return '0' unless emittable_path?(parsed.path)

          if container_traversal?(parsed.path)
            call = canonical_resolve_expr(parsed.path, 'double', prefix: prefix)
            fallback = parsed.default_kind == :number ? swift_default_literal(parsed) : '0'
            return "#{call} ?? #{fallback}"
          end

          base = "#{prefix}.#{parsed.path}"
          return base if non_optional?(parsed.path)

          default = parsed.default_kind == :number ? swift_default_literal(parsed) : '0'
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

          # VisibilityWrapper's initializer takes `String?` and
          # `Visibility(from:)` maps nil to .visible, so an unresolved
          # container path needs no fallback literal invented here.
          if container_traversal?(parsed.path)
            if parsed.negated
              call = canonical_resolve_expr(parsed.path, 'bool', prefix: prefix)
              return "!(#{call} ?? false) ? \"visible\" : \"gone\""
            end
            call = canonical_resolve_expr(parsed.path, 'stringify', prefix: prefix)
            default = text_default_literal(parsed)
            return default ? "(#{call} ?? #{default})" : call
          end

          base = "#{prefix}.#{parsed.path}"

          if parsed.negated
            bool_expr = non_optional?(parsed.path) ? "!#{base}" : "!(#{base} ?? false)"
            return "#{bool_expr} ? \"visible\" : \"gone\""
          end

          default = coerced_default_literal(parsed)
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
