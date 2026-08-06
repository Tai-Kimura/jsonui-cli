# frozen_string_literal: true

require 'json'
require_relative 'bound_value'
require_relative 'resource_resolver'

module KjuiTools
  module Compose
    module Helpers
      # Centralised helper for emitting `Configuration.Font.resolve(FontSpec(...))`
      # blocks in generated Compose code.
      #
      # The companion JSON `shared/core/font_weight_mapping.json` (a peer of the
      # other shared metadata) drives the `weight string -> FontWeight.X`
      # conversion. Unknown weight strings emit a warning and fall back to
      # `FontWeight.Normal`.
      class FontSpecHelper
        # Aliases accepted at the JSON layer that aren't keys in the shared
        # weight mapping. These are normalised to a key that IS in the mapping.
        # Data-section classes that mean "this binding carries a weight NUMBER".
        NUMERIC_PROPERTY_CLASSES = %w[Int Integer Long Double Float CGFloat Number].freeze

        WEIGHT_ALIASES = {
          'normal' => 'regular',
          'extralight' => 'ultralight',
          'extrabold' => 'bold' # legacy compat with previous generator output
        }.freeze

        # Cache the parsed mapping so we read the JSON once per process.
        def self.weight_mapping
          @weight_mapping ||= load_weight_mapping
        end

        # Build a hash describing the font emission for a JSON node.
        #
        # Returns:
        #   {
        #     family: <Kotlin literal string for `family =`>,
        #     weight: <Kotlin literal for `weight =`>,
        #     size:   <Kotlin literal for `size =`>,
        #     italic: 'false',  # always; reserved for future "italic" attribute
        #     has_any: <Boolean>  # true when at least one of the above is non-null
        #   }
        #
        # All literals are valid Kotlin expressions; nil-equivalent fields are the
        # string "null" so the caller can paste them directly into a `FontSpec(...)`
        # constructor without further guarding.
        def self.build_font_spec_args(json_data, required_imports = nil)
          family = build_family_literal(json_data, required_imports)
          weight = build_weight_literal(json_data, required_imports)
          size   = build_size_literal(json_data)

          {
            family: family || 'null',
            weight: weight || 'null',
            size:   size   || 'null',
            italic: 'false',
            has_any: !(family.nil? && weight.nil? && size.nil?)
          }
        end

        # Generate the multi-line `val <var_name> = Configuration.Font.resolve(FontSpec(...))`
        # block.
        #
        # `var_name` is whatever unique label the caller picked (e.g. `resolved_text1`).
        # `depth` is the surrounding indentation level (same convention as the rest of
        # the generators).
        def self.emit_resolve_block(var_name, font_spec_args, depth, required_imports = nil)
          required_imports&.add(:configuration)
          required_imports&.add(:font_spec)
          # A BOUND fontSize resolves to `TextUnit.Unspecified` when the
          # property is null — 0.sp would render the text invisible.
          required_imports&.add(:text_unit) if font_spec_args[:size].to_s.include?('TextUnit')

          indent("val #{var_name} = Configuration.Font.resolve(FontSpec(", depth) +
            "\n" + indent("family = #{font_spec_args[:family]},", depth + 1) +
            "\n" + indent("weight = #{font_spec_args[:weight]},", depth + 1) +
            "\n" + indent("size = #{font_spec_args[:size]},", depth + 1) +
            "\n" + indent("italic = #{font_spec_args[:italic]}", depth + 1) +
            "\n" + indent("))", depth)
        end

        # Convenience: produce the four `Text(...)` argument lines that consume a
        # ResolvedFont local. Returns a string already indented at `depth + 1`,
        # suitable for appending after the existing Text(...) parameters.
        def self.text_arg_lines(var_name, depth, required_imports = nil)
          required_imports&.add(:font_style)
          required_imports&.add(:text_unit)
          [
            indent("fontFamily = #{var_name}.family,", depth + 1),
            indent("fontWeight = #{var_name}.weight,", depth + 1),
            indent("fontSize = #{var_name}.size ?: TextUnit.Unspecified,", depth + 1),
            indent("fontStyle = #{var_name}.style ?: FontStyle.Normal,", depth + 1)
          ].join("\n")
        end

        # Produce the four assignments as TextStyle copy() args. Used by callers
        # that emit a `style = TextStyle(...)` block instead of inline Text args
        # (e.g. PartialAttributesText). Returns a list of `key = value` fragments
        # WITHOUT trailing commas; the caller joins them.
        def self.style_arg_fragments(var_name, required_imports = nil)
          required_imports&.add(:font_style)
          required_imports&.add(:text_unit)
          [
            "fontFamily = #{var_name}.family",
            "fontWeight = #{var_name}.weight",
            "fontSize = (#{var_name}.size ?: TextUnit.Unspecified)",
            "fontStyle = (#{var_name}.style ?: FontStyle.Normal)"
          ]
        end

        # Returns the kotlin enum literal for a JSON `font`/`fontWeight` weight
        # string, or nil for unknown / non-weight values. Emits a stderr warning
        # for unknown values.
        def self.weight_literal_for(weight_string)
          return nil if weight_string.nil?
          return nil if weight_string.is_a?(String) && weight_string.match?(/^@\{.*\}$/)

          key = weight_string.to_s.downcase
          mapping = weight_mapping

          # Direct hit on the shared mapping table.
          return mapping[key] if mapping.key?(key)

          # Aliased name that resolves to a real key.
          if WEIGHT_ALIASES.key?(key)
            target = WEIGHT_ALIASES[key]
            return mapping[target] if mapping.key?(target)
          end

          # NUMERIC weight. The SSoT declares ["string", "number"] on all
          # three platforms, and a `600` fell through the name table into the
          # warn+Normal arm — ios drew SemiBold where android drew Normal
          # (run 6 cross_effect: fontWeight__600 active on ios only; ruled a
          # cross-platform divergence to fix, not to ledger). The css column
          # of the SHARED table is the numeric vocabulary, so a number that
          # names a table row resolves through the table (600 -> SemiBold) —
          # one source for all three tools — and any other in-range value is
          # a direct FontWeight(n), which is exactly what the ios converter
          # does with it. Out of Compose's [1, 1000] falls to the same
          # warn+Normal arm as an unknown name.
          if key.match?(/\A\d+\z/)
            css_hit = css_weight_index[key]
            return css_hit if css_hit
            return "FontWeight(#{key.to_i})" if (1..1000).cover?(key.to_i)
          end

          warn "[kjui] Unknown font weight '#{weight_string}', defaulting to FontWeight.Normal"
          'FontWeight.Normal'
        end

        # `css numeric string -> kotlin literal`, derived from the shared
        # table so the numeric vocabulary cannot drift from the name one.
        # Non-numeric css spellings ("normal", "bold") are already reachable
        # as names and stay out.
        def self.css_weight_index
          @css_weight_index ||= raw_weight_rows.each_with_object({}) do |(_, row), index|
            css = row['css'].to_s
            index[css] ||= row['kotlin'] if css.match?(/\A\d+\z/) && row['kotlin']
          end
        end

        # Kotlin `FontWeight` expression for a `font` / `fontWeight` value that
        # MAY be bound. `weight_literal_for` deliberately returns nil for a
        # binding, and every caller then fell through to a `== 'bold'` test
        # that a `"@{...}"` string can never satisfy — so a bound weight froze
        # to `FontWeight.Normal` (plan 49 lane C: CheckBox.font, Radio.font,
        # Button.fontWeight). A binding now emits the whole mapping as a
        # runtime `when`, so the declared weight is honoured.
        #
        # Returns nil for an absent value, so callers keep their "emit nothing"
        # branch.
        def self.weight_expression(value, default: 'FontWeight.Normal')
          return nil if value.nil? || value == ''

          unless BoundValue.bound?(value)
            return weight_literal_for(value)
          end

          # A NUMERIC property is a weight value (`500`), not a vocabulary
          # word — the SSoT declares `["string", "number", "binding"]` — and
          # running it through the name table would collapse every numeric
          # weight onto the default. The data section knows which it is.
          inner = BindingExpression.extract_inner(value)
          path = BindingExpression.parse(inner).path
          if NUMERIC_PROPERTY_CLASSES.include?(ResourceResolver.get_property_class(path).to_s)
            # `FontWeight(n)` THROWS outside [1, 1000], and a non-nullable Int
            # property composes first with its default 0 — the raw emit took
            # the whole codegen host down for Button.fontWeight__binding
            # (5th-round: the one screenshot missing from the run). The
            # dynamic path resolves weights through a name table and cannot
            # throw, so the guard belongs here: out-of-range falls to 400,
            # which is what the fallback already meant.
            expr = BoundValue.int(value, fallback: 400)
            return "FontWeight(#{expr}.let { if (it in 1..1000) it else 400 })"
          end

          # The static path downcases before the lookup, so the runtime one has
          # to as well or `"Bold"` would miss every arm.
          BoundValue.enum(value, bound_weight_mapping, default: default, lowercase: true)
        end

        # The weight vocabulary as one flat `spelling => FontWeight.X` table:
        # the shared mapping plus every alias that resolves into it. Only used
        # for the bound case, where the whole table has to be emitted.
        def self.bound_weight_mapping
          mapping = weight_mapping
          table = mapping.dup
          WEIGHT_ALIASES.each do |alias_key, target|
            table[alias_key] = mapping[target] if mapping.key?(target)
          end
          table
        end

        # Determine whether a `font` JSON value is a weight name (vs a custom
        # family name like "Roboto-Regular").
        def self.weight_name?(value)
          return false if value.nil?
          return false if value.is_a?(String) && value.match?(/^@\{.*\}$/)
          key = value.to_s.downcase
          weight_mapping.key?(key) || WEIGHT_ALIASES.key?(key)
        end

        def self.indent(text, level)
          return text if level == 0
          spaces = '    ' * level
          text.split("\n").map { |line| line.empty? ? line : spaces + line }.join("\n")
        end

        # ── private helpers ──

        def self.build_family_literal(json_data, required_imports)
          # `fontFamily` always wins over `font`-as-family.
          if json_data['fontFamily']
            value = json_data['fontFamily'].to_s
            if value.match?(/^@\{.*\}$/)
              variable = value.match(/@\{([^}]+)\}/)[1]
              # FontSpec.family is a String?; the binding's runtime value is a String.
              return "data.#{variable}"
            end
            return value.inspect # quoted Kotlin string literal
          end

          # `font` is a custom family name when it is NOT a recognised weight.
          if json_data['font']
            value = json_data['font'].to_s
            return nil if value.match?(/^@\{.*\}$/)
            return value.inspect unless weight_name?(value)
          end

          nil
        end

        def self.build_weight_literal(json_data, required_imports)
          if json_data['font']
            value = json_data['font'].to_s
            if BoundValue.bound?(value)
              required_imports&.add(:font_weight)
              # The bound branch used to be `if (data.x == "bold") Bold else
              # Normal` — every other weight in the vocabulary collapsed to
              # Normal, and the comparison could not see a `?? default`.
              # weight_expression emits the whole mapping.
              return weight_expression(value)
            end
            if weight_name?(value)
              required_imports&.add(:font_weight)
              return weight_literal_for(value)
            end
          end

          if json_data['fontWeight']
            value = json_data['fontWeight'].to_s
            required_imports&.add(:font_weight)
            # `weight_literal_for` returns nil for a binding, so a bound
            # fontWeight used to vanish from FontSpec entirely (plan 49 lane C,
            # Button.fontWeight).
            return weight_expression(value)
          end

          nil
        end

        def self.build_size_literal(json_data)
          return nil unless json_data['fontSize']
          # `#{...}.sp` raw interpolation put `@{v}.sp` in code position.
          BoundValue.sp(json_data['fontSize'], null_expr: 'TextUnit.Unspecified')
        end

        # Candidate paths for the shared weight mapping, tried in order.
        # Unified with sjui/rjui resolution:
        #   1. `<tool_dir>/shared/core/...` — the per-tool copy distributed by
        #      `jui sync_tool` into project-local installs.
        #   2. repo-root `shared/core/...` — the library-repo layout, where
        #      `shared/` sits as a sibling of `kjui_tools/`.
        #   3. `~/.jsonui-cli/shared/core/...` — the global install location.
        # If none resolve, fall back to the built-in table below.
        def self.weight_mapping_candidates
          # With a __FILE__ base the FIRST `../` strips the filename, so every
          # hop count reads one deeper than the directory walk it describes.
          # Both paths below were one level short — candidate 1 pointed at
          # lib/shared/core and candidate 2 at kjui_tools/shared/core, neither
          # of which exists in the repo — and every machine with a
          # ~/.jsonui-cli install silently fell through to candidate 3, which
          # made the bug invisible everywhere except CI (84a5cb8 red). The
          # repo-checkout spec now asserts a candidate actually resolves.
          @weight_mapping_candidates || [
            # <tool_dir>/shared/core: font_spec_helper.rb → helpers → compose
            # → lib → kjui_tools (consumer layout, tool dir carries the table)
            File.expand_path('../../../../shared/core/font_weight_mapping.json', __FILE__),
            # repo-root shared/core: one level above kjui_tools (this repo)
            File.expand_path('../../../../../shared/core/font_weight_mapping.json', __FILE__),
            # global install
            File.expand_path('~/.jsonui-cli/shared/core/font_weight_mapping.json')
          ]
        end

        # Test-only seam: inject candidate paths (highest priority first).
        def self.weight_mapping_candidates=(paths)
          @weight_mapping_candidates = paths
          reset_weight_mapping_cache!
        end

        # Test-only seam: drop the cached mapping — all three derived caches,
        # or a candidate swap serves rows from the previous file.
        def self.reset_weight_mapping_cache!
          @weight_mapping = nil
          @raw_weight_rows = nil
          @css_weight_index = nil
        end

        def self.load_weight_mapping
          mapped = raw_weight_rows.each_with_object({}) do |(name, platforms), acc|
            kotlin = platforms['kotlin']
            acc[name.downcase] = kotlin if kotlin
          end
          mapped.empty? ? fallback_weight_mapping : mapped
        end

        # The shared table's rows whole, css column included — the numeric
        # weight vocabulary lives there and `css_weight_index` needs it.
        def self.raw_weight_rows
          @raw_weight_rows ||= begin
            path = weight_mapping_candidates.find { |p| p && File.exist?(p) }
            if path
              JSON.parse(File.read(path))['weights'] || {}
            else
              warn '[kjui] font_weight_mapping.json not found on any candidate path; using built-in fallback.'
              {}
            end
          rescue JSON::ParserError
            {}
          end
        end

        def self.fallback_weight_mapping
          {
            'ultralight' => 'FontWeight.ExtraLight',
            'thin' => 'FontWeight.Thin',
            'light' => 'FontWeight.Light',
            'regular' => 'FontWeight.Normal',
            'medium' => 'FontWeight.Medium',
            'semibold' => 'FontWeight.SemiBold',
            'bold' => 'FontWeight.Bold',
            'heavy' => 'FontWeight.Black',
            'black' => 'FontWeight.Black'
          }
        end
      end
    end
  end
end
