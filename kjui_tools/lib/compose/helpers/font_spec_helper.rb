# frozen_string_literal: true

require 'json'

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

          warn "[kjui] Unknown font weight '#{weight_string}', defaulting to FontWeight.Normal"
          'FontWeight.Normal'
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
            if value.match?(/^@\{.*\}$/)
              variable = value.match(/@\{([^}]+)\}/)[1]
              required_imports&.add(:font_weight)
              # Bound binding returns a String at runtime; convert to FontWeight inline.
              return "if (data.#{variable} == \"bold\") FontWeight.Bold else FontWeight.Normal"
            end
            if weight_name?(value)
              required_imports&.add(:font_weight)
              return weight_literal_for(value)
            end
          end

          if json_data['fontWeight']
            value = json_data['fontWeight'].to_s
            required_imports&.add(:font_weight)
            return weight_literal_for(value)
          end

          nil
        end

        def self.build_size_literal(json_data)
          return nil unless json_data['fontSize']
          "#{json_data['fontSize']}.sp"
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
          @weight_mapping_candidates || [
            # <tool_dir>/shared/core: helpers → compose → lib → kjui_tools
            File.expand_path('../../../shared/core/font_weight_mapping.json', __FILE__),
            # repo-root shared/core: one level above kjui_tools (library layout)
            File.expand_path('../../../../shared/core/font_weight_mapping.json', __FILE__),
            # global install
            File.expand_path('~/.jsonui-cli/shared/core/font_weight_mapping.json')
          ]
        end

        # Test-only seam: inject candidate paths (highest priority first).
        def self.weight_mapping_candidates=(paths)
          @weight_mapping_candidates = paths
          @weight_mapping = nil
        end

        # Test-only seam: drop the cached mapping.
        def self.reset_weight_mapping_cache!
          @weight_mapping = nil
        end

        def self.load_weight_mapping
          path = weight_mapping_candidates.find { |p| p && File.exist?(p) }
          unless path
            warn '[kjui] font_weight_mapping.json not found on any candidate path; using built-in fallback.'
            return fallback_weight_mapping
          end
          parsed = JSON.parse(File.read(path))
          weights = parsed['weights'] || {}
          mapped = weights.each_with_object({}) do |(name, platforms), acc|
            kotlin = platforms['kotlin']
            acc[name.downcase] = kotlin if kotlin
          end
          mapped.empty? ? fallback_weight_mapping : mapped
        rescue JSON::ParserError
          fallback_weight_mapping
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
