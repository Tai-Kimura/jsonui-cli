# frozen_string_literal: true

require 'json'

module RjuiTools
  module React
    module Helpers
      # Builds the JS source for `Configuration.Font.resolve({ family, weight,
      # size, italic })` invocations emitted by the rjui generator. Shared
      # between BaseConverter (the primary call site) and any custom
      # converter that wants to route a font spec through the host-supplied
      # provider.
      #
      # Cross-platform contract: the JSON layout's `font`, `fontFamily`, and
      # `fontSize` keys all flow through one `FontSpec` per text site, mirroring
      # SwiftJsonUI / KotlinJsonUI. See
      # docs/plans/2026-04-28-font-provider-unification.md §3 for the canonical
      # FontSpec shape and weight-mapping table.
      module FontSpecHelper
        # Sentinel key used inside `@dynamic_styles` to mark a JS spread
        # expression rather than a `key: value` pair. Subclass `build_style_attr`
        # render loops detect this prefix and emit `...<value>` instead.
        SPREAD_KEY_PREFIX = '__SPREAD__'

        module_function

        # Build a JS expression like:
        #   ...Configuration.Font.resolve({ family: 'Helvetica', weight: 'bold', size: 16, italic: false })
        # for spreading into a JSX inline `style={{ ... }}` attribute.
        #
        # Returns nil when no font_spec field is set — caller should skip the
        # Configuration emission entirely in that case.
        def build_resolve_spread(family: nil, weight: nil, size: nil, italic: false)
          return nil if family.nil? && weight.nil? && size.nil? && !italic

          fields = []
          fields << "family: #{js_string(family)}" unless family.nil?
          fields << "weight: #{format_weight(weight)}" unless weight.nil?
          fields << "size: #{size}" unless size.nil?
          fields << "italic: #{italic ? 'true' : 'false'}"

          "...Configuration.Font.resolve({ #{fields.join(', ')} })"
        end

        # Map a JsonUI weight string (e.g. "bold", "semibold") to its CSS-side
        # representation per shared/core/font_weight_mapping.json. Unknown
        # weights fall back to the string verbatim so app-side providers can
        # still route them.
        def map_weight_for_css(weight_string)
          return nil if weight_string.nil?

          weight_lower = weight_string.to_s.downcase
          mapping = weight_mapping
          entry = mapping['weights'][weight_lower]
          entry ? entry['css'] : weight_string.to_s
        end

        # Treat the JsonUI weight string as a *family* name when it isn't a
        # recognized weight token AND isn't one of the family aliases that
        # `TailwindMapper.map_font` already rewrites to a Tailwind class.
        # Returns true when the string should be passed through to the
        # provider's `family` slot instead of `weight`.
        def font_string_is_family?(font_string)
          return false if font_string.nil?
          lower = font_string.to_s.downcase
          weight_names = %w[ultraLight thin light regular normal medium semibold bold heavy black extralight extrabold].map(&:downcase)
          family_aliases = %w[monospace mono sans sans-serif serif]
          !weight_names.include?(lower) && !family_aliases.include?(lower)
        end

        # Lazy-load the shared weight mapping JSON. Mirrors binding_validator's
        # candidate-path approach so deployed (synced) copies of rjui_tools
        # without the shared/ tree still resolve.
        def weight_mapping
          @weight_mapping ||= load_weight_mapping
        end

        # Built-in fallback mapping, mirroring shared/core/font_weight_mapping.json
        # (css column). Used only when no candidate file resolves, so a missing
        # distributed file degrades to the correct CSS weights instead of an
        # empty mapping that passes every weight through verbatim.
        BUILTIN_WEIGHT_MAPPING = {
          'weights' => {
            'ultralight' => { 'css' => '200' },
            'thin' => { 'css' => '100' },
            'light' => { 'css' => '300' },
            'regular' => { 'css' => 'normal' },
            'medium' => { 'css' => '500' },
            'semibold' => { 'css' => '600' },
            'bold' => { 'css' => 'bold' },
            'heavy' => { 'css' => '900' },
            'black' => { 'css' => '900' }
          },
          'default_on_unknown' => 'regular'
        }.freeze

        # File layout reminder (resolution unified with sjui/kjui):
        # - this file:      .../jsonui-cli/rjui_tools/lib/react/helpers/font_spec_helper.rb
        # - per-tool copy:  .../rjui_tools/shared/core/font_weight_mapping.json (synced by jui sync_tool)
        # - repo-root copy: .../jsonui-cli/shared/core/font_weight_mapping.json (library layout)
        # - global copy:    ~/.jsonui-cli/shared/core/font_weight_mapping.json
        # - legacy mirror:  .../rjui_tools/lib/core/font_weight_mapping.json
        def weight_mapping_candidates
          [
            # <tool_dir>/shared/core: helpers → react → lib → rjui_tools
            File.expand_path('../../../shared/core/font_weight_mapping.json', __FILE__),
            # repo-root shared/core: one level above rjui_tools (library layout)
            File.expand_path('../../../../shared/core/font_weight_mapping.json', __FILE__),
            # global install
            File.expand_path('~/.jsonui-cli/shared/core/font_weight_mapping.json'),
            # legacy in-tool mirror
            File.expand_path('../../core/font_weight_mapping.json', __FILE__)
          ]
        end

        def load_weight_mapping
          path = weight_mapping_candidates.find { |p| p && File.exist?(p) }
          return builtin_weight_mapping unless path

          parsed = JSON.parse(File.read(path, encoding: 'UTF-8'))
          weights = parsed['weights'] || {}
          weights.empty? ? builtin_weight_mapping : parsed
        rescue JSON::ParserError
          builtin_weight_mapping
        end

        def builtin_weight_mapping
          weights = BUILTIN_WEIGHT_MAPPING['weights'].each_with_object({}) do |(k, v), acc|
            acc[k.to_s.downcase] = v.dup
          end
          { 'weights' => weights, 'default_on_unknown' => BUILTIN_WEIGHT_MAPPING['default_on_unknown'] }
        end

        def js_string(value)
          escaped = value.to_s.gsub('\\', '\\\\').gsub("'", "\\\\'")
          "'#{escaped}'"
        end

        # Render the weight as a JS literal. Numeric → bare number,
        # everything else → quoted string.
        def format_weight(weight)
          return weight.to_s if weight.is_a?(Numeric)
          js_string(weight)
        end
      end
    end
  end
end
