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
        # Path to the shared weight-name → platform-enum mapping. Loaded once.
        WEIGHT_MAPPING_PATH = File.expand_path(
          '../../../../../shared/core/font_weight_mapping.json',
          __FILE__
        )

        # Weight keywords recognised in the `font` attribute. Anything else in
        # `font` is treated as a family name. Compared case-insensitively.
        WEIGHT_KEYWORDS = %w[
          ultralight thin light regular normal medium semibold bold heavy black
        ].freeze

        # Lazy-load the shared mapping so we read the file at most once per
        # process. Falls back to an empty mapping if the file is missing —
        # callers will then warn + emit `.regular` for every weight.
        # The keys are normalised to lowercase so JSON-side `ultraLight` matches
        # generator-side `ultralight` lookups transparently.
        def self.weight_mapping
          @weight_mapping ||= load_weight_mapping
        end

        # Reset the cached mapping. Test-only seam.
        def self.reset_weight_mapping_cache!
          @weight_mapping = nil
        end

        def self.load_weight_mapping
          if File.exist?(WEIGHT_MAPPING_PATH)
            raw = JSON.parse(File.read(WEIGHT_MAPPING_PATH))
            weights = (raw['weights'] || {}).each_with_object({}) do |(k, v), acc|
              acc[k.to_s.downcase] = v
            end
            { 'weights' => weights, 'default_on_unknown' => raw['default_on_unknown'] || 'regular' }
          else
            { 'weights' => {}, 'default_on_unknown' => 'regular' }
          end
        end
        private_class_method :load_weight_mapping

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
