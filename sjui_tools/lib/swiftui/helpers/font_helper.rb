# frozen_string_literal: true

require 'json'

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

          family_arg = family_literal.nil? ? 'nil' : "\"#{family_literal}\""
          weight_arg = weight_literal.nil? ? 'nil' : weight_literal
          size_arg   = size_literal.nil? ? 'nil' : "CGFloat(#{size_literal})"

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
          weight_literal = weight_source ? font_weight_to_swiftui(weight_source) : nil

          size_literal = component['fontSize']

          [family_literal, weight_literal, size_literal]
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
                        :font_weight_to_swiftui
      end
    end
  end
end
