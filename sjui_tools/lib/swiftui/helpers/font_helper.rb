# frozen_string_literal: true

require 'json'
require_relative '../views/value_expression_helper'

module SjuiTools
  module SwiftUI
    module Helpers
      # Helper module for font-related conversions and processing.
      #
      # As of SwiftJsonUI 9.5.0 every font-bearing component routes through
      # `SwiftJsonUIConfiguration.shared.resolveFont(FontSpec(...))`. The
      # generator collapses the JSON-level `fontFamily` / `font` (weight or
      # family) / `fontSize` attributes into a single FontSpec, so apps only
      # need one provider closure to control all weight × family × size
      # combinations.
      module FontHelper
        # Both forms are needed: converters `include FontHelper` and call the
        # methods on themselves, and the module is also driven directly as
        # `FontHelper.apply_font_modifiers(component, converter)`. The
        # bound-value emitters have to be reachable from either entry point.
        include SjuiTools::SwiftUI::Views::ValueExpressionHelper
        extend SjuiTools::SwiftUI::Views::ValueExpressionHelper

        # Candidate paths for the shared weight-name → platform-enum mapping,
        # tried in order. Resolution is unified with kjui/rjui:
        #   1. `<tool_dir>/shared/core/...` — the per-tool copy that
        #      `jui sync_tool` distributes into project-local installs.
        #   2. repo-root `shared/core/...` — the library-repo layout, where
        #      `shared/` sits as a sibling of `sjui_tools/`.
        #   3. `~/.jsonui-cli/shared/core/...` — the global install location.
        # If none resolve, `load_weight_mapping` falls back to the built-in
        # table below (defensive parity with kjui): a missing file must never
        # silently change generated output.
        WEIGHT_MAPPING_CANDIDATES = [
          # <tool_dir>/shared/core: helpers → swiftui → lib → sjui_tools
          File.expand_path('../../../../shared/core/font_weight_mapping.json', __FILE__),
          # repo-root shared/core: one level above sjui_tools (library layout)
          File.expand_path('../../../../../shared/core/font_weight_mapping.json', __FILE__),
          # global install
          File.expand_path('~/.jsonui-cli/shared/core/font_weight_mapping.json')
        ].freeze

        # Built-in fallback mapping, mirroring shared/core/font_weight_mapping.json
        # (swift column). Used only when no candidate file resolves, so that a
        # missing distributed file degrades to correct output instead of an
        # empty mapping that rounds every weight to `.regular`.
        BUILTIN_WEIGHT_MAPPING = {
          'weights' => {
            'ultralight' => { 'swift' => '.ultraLight' },
            'thin' => { 'swift' => '.thin' },
            'light' => { 'swift' => '.light' },
            'regular' => { 'swift' => '.regular' },
            'medium' => { 'swift' => '.medium' },
            'semibold' => { 'swift' => '.semibold' },
            'bold' => { 'swift' => '.bold' },
            'heavy' => { 'swift' => '.heavy' },
            'black' => { 'swift' => '.black' }
          },
          'default_on_unknown' => 'regular'
        }.freeze

        # Weight keywords recognised in the `font` attribute. Anything else in
        # `font` is treated as a family name. Compared case-insensitively.
        WEIGHT_KEYWORDS = %w[
          ultralight thin light regular normal medium semibold bold heavy black
        ].freeze

        # Lazy-load the shared mapping so we read the file at most once per
        # process. Falls back to the built-in table (BUILTIN_WEIGHT_MAPPING)
        # when no candidate file resolves, so a missing distributed file never
        # silently rounds every weight to `.regular`.
        # The keys are normalised to lowercase so JSON-side `ultraLight` matches
        # generator-side `ultralight` lookups transparently.
        def self.weight_mapping
          @weight_mapping ||= load_weight_mapping
        end

        # Reset the cached mapping. Test-only seam.
        def self.reset_weight_mapping_cache!
          @weight_mapping = nil
        end

        # Allow tests to inject custom candidate paths (highest priority first).
        # Passing nil restores the default WEIGHT_MAPPING_CANDIDATES chain.
        def self.weight_mapping_candidates
          @weight_mapping_candidates || WEIGHT_MAPPING_CANDIDATES
        end

        def self.weight_mapping_candidates=(paths)
          @weight_mapping_candidates = paths
          reset_weight_mapping_cache!
        end

        def self.load_weight_mapping
          path = weight_mapping_candidates.find { |p| p && File.exist?(p) }
          return builtin_weight_mapping unless path

          raw = JSON.parse(File.read(path))
          weights = (raw['weights'] || {}).each_with_object({}) do |(k, v), acc|
            acc[k.to_s.downcase] = v
          end
          return builtin_weight_mapping if weights.empty?

          { 'weights' => weights, 'default_on_unknown' => raw['default_on_unknown'] || 'regular' }
        rescue JSON::ParserError
          builtin_weight_mapping
        end
        private_class_method :load_weight_mapping

        # Deep copy of the frozen built-in table with lowercased keys.
        def self.builtin_weight_mapping
          weights = BUILTIN_WEIGHT_MAPPING['weights'].each_with_object({}) do |(k, v), acc|
            acc[k.to_s.downcase] = v.dup
          end
          { 'weights' => weights, 'default_on_unknown' => BUILTIN_WEIGHT_MAPPING['default_on_unknown'] }
        end
        private_class_method :builtin_weight_mapping

        # Apply font modifiers based on component attributes.
        #
        # Emits a single `.font(SwiftJsonUIConfiguration.shared.resolveFont(...))`
        # line when at least one of `fontFamily` / `font` / `fontSize` is
        # present, and nothing otherwise (system default behaviour).
        #
        # @param component [Hash] The component hash containing font attributes
        # @param converter [BaseViewConverter] The converter instance to add modifier lines to
        def apply_font_modifiers(component, converter)
          family_literal, weight_literal, size_literal = build_font_spec_args(component)

          # Skip emission entirely when nothing was specified — the view will
          # pick up the system default.
          return if family_literal.nil? && weight_literal.nil? && size_literal.nil?

          # A bound family used to be quoted like a literal, which compiled
          # and then asked the font provider for a family called
          # "@{fontName}"; a bound size was interpolated bare into
          # `CGFloat(...)`, which does not compile at all. Both go through the
          # canonical emitters now. The static branches are untouched.
          family_arg = bound_string(family_literal) ||
                       (family_literal.nil? ? 'nil' : "\"#{family_literal}\"")
          weight_arg = weight_literal.nil? ? 'nil' : weight_literal
          size_arg   = bound_number(size_literal) ||
                       (size_literal.nil? ? 'nil' : "CGFloat(#{size_literal})")

          # A bound `font` is the ambiguous spelling and owns both slots.
          # `fontFamily` / `fontWeight` are unambiguous and keep theirs, so
          # this only fires when `font` is what fed the family slot.
          if family_literal.equal?(component['font']) && weight_literal.nil? &&
             (pair = bound_font_args(component['font']))
            family_arg, weight_arg = pair
          end

          converter.add_modifier_line(
            ".font(SwiftJsonUIConfiguration.shared.resolveFont(" \
              "FontSpec(family: #{family_arg}, weight: #{weight_arg}, size: #{size_arg}, italic: false)))"
          )
        end

        # Decompose the component's font attributes into the three generator
        # inputs: family literal, weight enum literal (e.g. `.bold`), size
        # numeric literal. Any of them can be nil when the JSON did not
        # specify the corresponding attribute.
        #
        # @return [Array<String, String, Numeric>] [family, weight, size]
        def build_font_spec_args(component)
          font_attr = component['font']
          font_is_weight = font_attr.is_a?(String) && WEIGHT_KEYWORDS.include?(font_attr.downcase)

          family_literal = component['fontFamily']
          family_literal ||= font_attr if font_attr.is_a?(String) && !font_is_weight

          weight_source = component['fontWeight']
          weight_source ||= font_attr if font_is_weight
          weight_literal = if weight_source.nil?
                             nil
                           else
                             # `font_weight_to_swiftui` looks the string up in
                             # the shared table at GENERATION time and warns on
                             # anything it does not know, so a `@{...}` froze to
                             # `.regular` with a spurious warning. A bound weight
                             # carries the same table into the emitted Swift
                             # instead — one vocabulary, resolved a step later.
                             swift_weight_expr(weight_source) ||
                               font_weight_to_swiftui(weight_source)
                           end

          size_literal = component['fontSize']

          [family_literal, weight_literal, size_literal]
        end

        # A BOUND weight as a Swift expression, or nil when *value* is not a
        # binding.
        #
        # `Font.Weight` is not RawRepresentable and SwiftJsonUI's own
        # `Font.Weight.from(string:)` is internal to the module, so generated
        # app code cannot ask the library to do this lookup. The shared table
        # is written into the emission instead — which keeps the vocabulary in
        # `shared/core/font_weight_mapping.json` alone, where kjui and rjui
        # read it too, rather than forking a second copy into Swift.
        def swift_weight_expr(value, default: :fallback)
          return nil unless bound_value?(value)

          # `fontWeight` is declared `["string", "number", "binding"]`, and
          # the two halves of the codegen were reading the union differently:
          # the Data model generator saw `number` and declared
          # `var boundFontWeight: Int`, while this emitter saw `string` and
          # sent it through the NAME table — `[…][data.boundFontWeight
          # .lowercased()]`, i.e. `value of type 'Int' has no member
          # 'lowercased'`. Nothing before the compiler could see it: the
          # binding survived, no `@{` is left, and the dictionary key really
          # is a String, so the type sweep agreed with itself.
          #
          # The data section is the only place that knows which half was
          # taken, so it decides. kjui reached the same answer independently
          # for the same attribute (`font_spec_helper.rb#weight_expression`).
          if numeric_property?(value)
            return bound_numeric_weight(value, default: default)
          end

          mapping = FontHelper.weight_mapping
          weights = mapping['weights'] || {}
          table = {}
          weights.each { |name, entry| table[name] = entry['swift'] if entry['swift'] }
          # The generation-time aliases resolve at run time too, or a weight
          # spelling that works statically would stop working when bound.
          { 'normal' => 'regular', 'ultra-light' => 'ultralight', 'semi-bold' => 'semibold' }
            .each { |from, to| table[from] = table[to] if table[to] }
          fallback_key = (mapping['default_on_unknown'] || 'regular').to_s.downcase
          fallback = default == :fallback ? (table[fallback_key] || '.regular') : default

          bound_enum(value, table, default: fallback, type: 'Font.Weight')
        end

        #: Data-section classes that make a weight a NUMBER rather than a name.
        NUMERIC_PROPERTY_CLASSES = %w[Int Int32 Int64 Double Float CGFloat NSNumber].freeze

        # Whether the bound property is declared numeric in the data section.
        def numeric_property?(value)
          path = Binding::BindingExpression.parse(binding_inner(value)).path
          definition = (Thread.current[:sjui_data_definitions] || {})[path]
          return false unless definition

          NUMERIC_PROPERTY_CLASSES.include?(definition['class'].to_s)
        end

        #: CSS weight number -> SwiftUI literal, derived from the shared
        #: mapping's own `css` column rather than a second scale invented
        #: here. `normal` and `bold` are the two word spellings CSS defines as
        #: 400 and 700; everything else in the table is already a number.
        #: First spelling wins a collision — `heavy` and `black` both declare
        #: 900, and `heavy` is the one the table lists first.
        def numeric_weight_table
          weights = (FontHelper.weight_mapping['weights'] || {})
          words = { 'normal' => 400, 'bold' => 700 }
          table = {}
          weights.each do |name, entry|
            swift = entry['swift']
            css = entry['css'].to_s
            number = css.match?(/\A\d+\z/) ? css.to_i : words[css]
            next if swift.nil? || number.nil?

            table[number] = swift unless table.key?(number)
          end
          table
        end

        # A numeric weight resolved at run time: `[700: Font.Weight.bold, …]`.
        def bound_numeric_weight(value, default: :fallback)
          table = numeric_weight_table
          return nil if table.empty?

          fallback = default == :fallback ? '.regular' : default
          pairs = table.sort.each_with_index.map do |(number, swift), index|
            "#{number}: #{index.zero? ? "Font.Weight#{swift}" : swift}"
          end
          lookup = "[#{pairs.join(', ')}][#{bound_number(value, cast: 'Int')}]"
          fallback.nil? ? "(#{lookup})" : "(#{lookup} ?? #{fallback})"
        end

        # The two FontSpec arguments a bound `font` decomposes into, or nil
        # when *value* is not a binding.
        #
        # `font` is ambiguous by declaration — "Font weight name … or font
        # name" — and the static path resolves it by testing the string
        # against WEIGHT_KEYWORDS. A binding is not a weight keyword, so it
        # always fell through to the family branch and was emitted QUOTED:
        # the provider was then asked for a family literally called
        # "@{fontName}". The rule does not change here, only when it is
        # applied: the same table decides at run time, so a bound `font`
        # naming a weight IS the weight and anything else is the family,
        # exactly as a written-out one would be.
        def bound_font_args(value)
          lookup = swift_weight_expr(value, default: nil)
          return nil if lookup.nil?

          text = bound_string(value)
          # The family branch only has to know whether the string NAMES a
          # weight, so it tests membership against the same keys rather than
          # repeating the whole dictionary — a second 12-entry literal in the
          # same expression is what makes Swift's type checker crawl.
          names = weight_vocabulary.map { |name| name.to_s.inspect }.join(', ')
          ["([#{names}].contains(#{text}.lowercased()) ? nil : #{text})", lookup]
        end

        # Every weight spelling the generator accepts, aliases included.
        def weight_vocabulary
          mapping = FontHelper.weight_mapping
          names = (mapping['weights'] || {}).keys
          names + %w[normal ultra-light semi-bold]
        end

        # Convert a JSON `font` weight string to the corresponding SwiftUI
        # `Font.Weight` enum literal using the shared mapping.
        #
        # Unknown values produce a warning and fall back to `.regular`.
        #
        # @param weight [String] The weight string (e.g., "bold", "semibold", "light")
        # @return [String, nil] SwiftUI font weight literal, or nil if input is nil/empty
        def font_weight_to_swiftui(weight)
          return nil if weight.nil?

          key = weight.to_s.downcase
          return nil if key.empty?

          # A numeric weight is a declared spelling — "e.g. 'bold',
          # 'semibold', '500', 600" — and the name table has no entry for it,
          # so `600` warned and froze to `.regular`. Same table the bound
          # numeric path uses, so the two spellings of one weight agree.
          if key.match?(/\A\d+\z/)
            numeric = numeric_weight_table[key.to_i]
            return numeric if numeric
          end

          # Aliases not present in the shared mapping but historically accepted.
          aliases = {
            'normal' => 'regular',
            'ultra-light' => 'ultralight',
            'semi-bold' => 'semibold'
          }
          key = aliases[key] || key

          mapping = FontHelper.weight_mapping
          weights = mapping['weights'] || {}
          if (entry = weights[key]) && entry['swift']
            return entry['swift']
          end

          fallback_key = mapping['default_on_unknown'] || 'regular'
          warn "[FontHelper] unknown font weight '#{weight}', falling back to '#{fallback_key}'"
          (weights[fallback_key.to_s.downcase] && weights[fallback_key.to_s.downcase]['swift']) || '.regular'
        end

        module_function :apply_font_modifiers,
                        :build_font_spec_args,
                        :swift_weight_expr,
                        :bound_font_args,
                        :numeric_property?,
                        :numeric_weight_table,
                        :bound_numeric_weight,
                        :weight_vocabulary,
                        :font_weight_to_swiftui
      end
    end
  end
end
