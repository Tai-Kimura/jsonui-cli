# frozen_string_literal: true

require 'json'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'
require_relative '../../core/logger'

module SjuiTools
  module SwiftUI
    module Views
      # Which colour names the app will actually be able to resolve at runtime.
      #
      # `SwiftJsonUIConfiguration.getColor(for:)` answers from the palette the
      # generated ColorManager carries, and that palette is copied verbatim
      # from colors.json — so "resolvable" means "a key in colors.json", plus
      # hex, which getColor parses itself (`init?(hex:)`, 3/6/8 digits).
      #
      # The lookup is MODE-AGNOSTIC on purpose. A layout names a key, not a
      # mode; a colour defined only under `dark` still resolves when the app
      # runs dark. `TypeConverterCore.color_exists?` flattens to ONE mode and
      # would call such a key undefined, so it is the wrong predicate here.
      #
      # Read from disk rather than from the ColorManager's extraction pass:
      # on iOS `process_resources` runs AFTER codegen and skips files the
      # build cache calls unchanged, so a predicate hung off it would answer
      # from build history — the defect 1.8.45 removed from validation.
      module ColorPalette
        META_KEYS = %w[fallback_mode systemModeMapping modes].freeze

        class << self
          # nil means "could not be determined" — NOT "empty". Callers must
          # treat nil as "assume defined": an unreadable colors.json is not an
          # empty one, and guessing "undefined" there would warn about every
          # colour in the project and rewrite every fallback.
          # Wrapped in a one-element array so that a cached nil ("could not
          # be determined") is distinguishable from "not loaded yet" without
          # relying on Thread#key?, which `= nil` does not clear.
          def names
            cached = Thread.current[:sjui_palette_names]
            return cached.first if cached.is_a?(Array)

            Thread.current[:sjui_palette_names] = [load_names]
            Thread.current[:sjui_palette_names].first
          end

          # Specs and long-lived processes only: a build reads colors.json once.
          def reset!
            Thread.current[:sjui_palette_names] = nil
            Thread.current[:sjui_warned_colors] = nil
          end

          # A colour string the runtime will not resolve: shaped like a
          # palette key, absent from every mode. Hex, binding expressions and
          # platform literals (`Color.Green`) are not key-shaped and are left
          # to the paths that already handle them.
          def undefined?(color_value)
            return false unless color_value.is_a?(String)
            return false unless key_shaped?(color_value)

            known = names
            return false if known.nil?

            !known.include?(color_value)
          end

          # Once per name per build: a colour repeated across forty layouts is
          # one authoring mistake, not forty findings.
          def warn_once(color_value)
            warned = (Thread.current[:sjui_warned_colors] ||= {})
            return if warned[color_value]

            warned[color_value] = true
            Core::Logger.warn(
              "Color '#{color_value}' is not defined in colors.json — " \
              'getColor returns nil at runtime and the view falls back to ' \
              'Color.clear. Add it to colors.json (every mode) or use a hex value.'
            )
          end

          # Same shape rule the colour extractor uses to decide whether a
          # string could be a key at all (color_manager_core#color_key_shaped?).
          def key_shaped?(value)
            value.match?(/\A[A-Za-z_][A-Za-z0-9_]*\z/)
          end

          private

          def load_names
            path = colors_file_path
            return nil if path.nil? || !File.exist?(path)

            raw = JSON.parse(File.read(path))
            return nil unless raw.is_a?(Hash)

            union_of_modes(raw)
          rescue JSON::ParserError, SystemCallError, IOError
            nil
          end

          def union_of_modes(raw)
            content = raw.reject { |k, _| META_KEYS.include?(k) }
            # An empty palette really does define nothing; that is a different
            # answer from the unreadable file above, which returns nil.
            return [] if content.empty?

            if content.values.all? { |v| v.is_a?(Hash) }
              content.values.flat_map(&:keys).uniq
            else
              content.keys
            end
          end

          def colors_file_path
            config = Core::ConfigManager.load_config
            source_path = Core::ProjectFinder.get_full_source_path || Dir.pwd
            layouts_dir = File.join(source_path, config['layouts_directory'] || 'Layouts')
            File.join(layouts_dir, 'Resources', 'colors.json')
          rescue StandardError
            nil
          end
        end
      end
    end
  end
end
