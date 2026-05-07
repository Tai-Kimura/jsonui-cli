# frozen_string_literal: true

require 'json'
require 'fileutils'
require_relative '../logger'
require_relative '../generated_marker'

module RjuiTools
  module Core
    module Resources
      class ColorManager
        # Top-level keys in colors.json that are NOT color modes. Everything
        # else at the top level is treated as a mode name whose value is a
        # `{key => "#HEX"}` palette.
        RESERVED_META_KEYS = %w[fallback_mode systemModeMapping modes].freeze
        DEFAULT_MODE_NAME = 'light'
        DEFAULT_DARK_MODE_NAME = 'dark'

        def initialize(config, source_path, resources_dir)
          @config = config
          @source_path = source_path
          @resources_dir = resources_dir
          @colors_file = File.join(@resources_dir, 'colors.json')
          @defined_colors_file = File.join(@resources_dir, 'defined_colors.json')

          # Extracted colors during this build pass: { mode => { key => hex } }.
          # They land in the same mode (@extract_into_mode) unless a caller
          # routes per-color-value to a different mode.
          @extracted_colors = Hash.new { |h, k| h[k] = {} }
          @undefined_colors = {}

          load_colors_json
          @defined_colors_data = load_defined_colors_json
        end

        # Main process method called from ResourcesManager.
        def process_colors(processed_files, processed_count, skipped_count, config)
          return if processed_files.empty?

          Core::Logger.info "Extracting colors from #{processed_count} files (#{skipped_count} skipped)..."

          extract_colors(processed_files)

          # Always save if we migrated the schema (flat → themed) even when no
          # new colors were extracted — the on-disk file still needs to be
          # rewritten into the new shape so subsequent reads are consistent.
          save_colors_json if any_extracted? || @migrated

          save_defined_colors_json if @undefined_colors.any?

          generate_color_manager if @config['generated_directory']
        end

        # Apply extracted colors to color asset files.
        def apply_to_color_assets
          save_colors_json if any_extracted? || @migrated
          save_defined_colors_json if @undefined_colors.any?
        end

        # Public API for other components that need to know about themes.
        attr_reader :modes, :palettes, :fallback_mode, :system_mode_mapping

        private

        def any_extracted?
          @extracted_colors.any? { |_, palette| palette.any? }
        end

        # Load existing colors.json. Detects flat-legacy vs themed schema and
        # populates @palettes / @modes / @fallback_mode / @system_mode_mapping.
        # Sets @migrated = true if a flat-legacy file needs to be rewritten.
        def load_colors_json
          @migrated = false
          @palettes = {}
          @modes = []
          @fallback_mode = nil
          @system_mode_mapping = nil

          if File.exist?(@colors_file)
            raw = begin
              JSON.parse(File.read(@colors_file))
            rescue JSON::ParserError => e
              Core::Logger.warn "Failed to parse colors.json: #{e.message}"
              nil
            end

            case detect_schema(raw)
            when :themed
              ingest_themed(raw)
            when :flat
              ingest_flat(raw)
            else
              seed_default_empty
            end
          else
            seed_default_empty
          end

          @system_mode_mapping ||= default_system_mode_mapping
          @extract_into_mode = resolve_extract_into_mode
        end

        def seed_default_empty
          @modes = [DEFAULT_MODE_NAME]
          @palettes[DEFAULT_MODE_NAME] = {}
          @fallback_mode = DEFAULT_MODE_NAME
        end

        # Schema classification.
        def detect_schema(raw)
          return :empty unless raw.is_a?(Hash)
          return :empty if raw.empty?

          content_keys = raw.keys - RESERVED_META_KEYS
          return :empty if content_keys.empty?

          sample_value = raw[content_keys.first]
          case sample_value
          when Hash then :themed
          when String then :flat
          else :empty
          end
        end

        def ingest_themed(raw)
          meta_modes_hint = raw['modes'].is_a?(Array) ? raw['modes'] : nil
          @fallback_mode = raw['fallback_mode'] if raw['fallback_mode'].is_a?(String)
          @system_mode_mapping = raw['systemModeMapping'] if raw['systemModeMapping'].is_a?(Hash)

          palette_keys = raw.keys - RESERVED_META_KEYS
          palette_keys.each do |mode_name|
            value = raw[mode_name]
            next unless value.is_a?(Hash)

            @palettes[mode_name] = value.each_with_object({}) do |(k, v), acc|
              acc[k] = v if v.is_a?(String) || v.nil?
            end
          end

          @modes = if meta_modes_hint
                     ordered = meta_modes_hint.select { |m| @palettes.key?(m) }
                     extras = @palettes.keys - ordered
                     ordered + extras
                   else
                     @palettes.keys
                   end

          @fallback_mode ||= @modes.include?(DEFAULT_MODE_NAME) ? DEFAULT_MODE_NAME : @modes.first
          @system_mode_mapping ||= default_system_mode_mapping
        end

        def ingest_flat(raw)
          Core::Logger.info "Migrating colors.json from flat schema to themed (default mode: '#{DEFAULT_MODE_NAME}')"
          @migrated = true

          flat_palette = raw.each_with_object({}) do |(k, v), acc|
            next if RESERVED_META_KEYS.include?(k)
            acc[k] = v if v.is_a?(String) || v.nil?
          end

          @modes = [DEFAULT_MODE_NAME]
          @palettes[DEFAULT_MODE_NAME] = flat_palette
          @fallback_mode = DEFAULT_MODE_NAME
          @system_mode_mapping = default_system_mode_mapping
        end

        def default_system_mode_mapping
          mapping = {}
          mapping['light'] = DEFAULT_MODE_NAME if @palettes.key?(DEFAULT_MODE_NAME)
          mapping['dark'] = DEFAULT_DARK_MODE_NAME if @palettes.key?(DEFAULT_DARK_MODE_NAME)
          mapping
        end

        # Determine which mode extraction writes to. Precedence:
        #   1. @config['extract_into_mode'] if present and mode exists (or create)
        #   2. 'light' if present
        #   3. First mode in @modes
        #   4. Create 'light' from scratch
        def resolve_extract_into_mode
          requested = @config['extract_into_mode']
          if requested.is_a?(String) && !requested.empty?
            unless @palettes.key?(requested)
              @palettes[requested] = {}
              @modes << requested unless @modes.include?(requested)
            end
            return requested
          end

          return DEFAULT_MODE_NAME if @palettes.key?(DEFAULT_MODE_NAME)
          return @modes.first unless @modes.empty?

          @palettes[DEFAULT_MODE_NAME] = {}
          @modes << DEFAULT_MODE_NAME
          @fallback_mode ||= DEFAULT_MODE_NAME
          @system_mode_mapping ||= default_system_mode_mapping
          DEFAULT_MODE_NAME
        end

        # Load existing defined_colors.json file.
        def load_defined_colors_json
          return {} unless File.exist?(@defined_colors_file)

          begin
            JSON.parse(File.read(@defined_colors_file))
          rescue JSON::ParserError => e
            Core::Logger.warn "Failed to parse defined_colors.json: #{e.message}"
            {}
          end
        end

        # Write @palettes back out as themed schema, preserving meta keys.
        def save_colors_json
          # Merge extracted into palettes (per mode).
          @extracted_colors.each do |mode, new_entries|
            @palettes[mode] ||= {}
            @palettes[mode].merge!(new_entries)
            @modes << mode unless @modes.include?(mode)
          end

          FileUtils.mkdir_p(@resources_dir)

          out = {}
          out['modes'] = @modes if @modes.size > 1 || @migrated
          out['fallback_mode'] = @fallback_mode if @fallback_mode
          out['systemModeMapping'] = @system_mode_mapping if @system_mode_mapping && !@system_mode_mapping.empty?

          @modes.each do |mode|
            out[mode] = @palettes[mode] || {}
          end

          File.write(@colors_file, JSON.pretty_generate(out))

          total_new = @extracted_colors.sum { |_, p| p.size }
          if total_new.positive?
            Core::Logger.info "Updated colors.json with #{total_new} new colors across #{@extracted_colors.size} mode(s)"
          elsif @migrated
            Core::Logger.info "Migrated colors.json to themed schema"
          end

          @extracted_colors.clear
          @migrated = false
        end

        # Save undefined colors to defined_colors.json.
        def save_defined_colors_json
          @defined_colors_data.merge!(@undefined_colors)

          FileUtils.mkdir_p(@resources_dir)

          File.write(@defined_colors_file, JSON.pretty_generate(@defined_colors_data))
          Core::Logger.info "Updated defined_colors.json with #{@undefined_colors.size} undefined color keys"

          @undefined_colors.clear
        end

        # Extract color values from processed JSON files.
        def extract_colors(processed_files)
          @modified_files = []

          Core::Logger.debug "Processing #{processed_files.size} files for colors"

          processed_files.each do |json_file|
            begin
              Core::Logger.debug "Processing file: #{json_file}"
              content = File.read(json_file)
              data = JSON.parse(content)

              modified = replace_colors_recursive(data)

              Core::Logger.debug "File modified: #{modified}"

              if modified
                File.write(json_file, JSON.pretty_generate(data))
                @modified_files << json_file
                Core::Logger.debug "Updated colors in: #{json_file}"
              end
            rescue JSON::ParserError => e
              Core::Logger.warn "Failed to parse #{json_file}: #{e.message}"
            rescue => e
              Core::Logger.error "Error processing #{json_file}: #{e.message}"
            end
          end

          if @modified_files.any?
            Core::Logger.info "Replaced colors in #{@modified_files.size} files"
          end
        end

        # Replace colors recursively in JSON data.
        def replace_colors_recursive(data, parent_key = nil)
          modified = false

          case data
          when Hash
            if data['class'] == 'Color' && data['defaultValue'].is_a?(String)
              value = data['defaultValue']
              unless value.start_with?('@{') && value.end_with?('}')
                new_value = process_and_replace_color(value)
                if new_value != value
                  data['defaultValue'] = new_value
                  modified = true
                  Core::Logger.debug "Replaced data defaultValue #{value} with #{new_value}"
                end
              end
            end

            data.each do |key, value|
              if is_color_property?(key) && value.is_a?(String)
                if value.start_with?('@{') && value.end_with?('}')
                  Core::Logger.debug "Skipping binding expression: #{value}"
                  next
                end

                new_value = process_and_replace_color(value)
                if new_value != value
                  data[key] = new_value
                  modified = true
                  Core::Logger.debug "Replaced #{value} with #{new_value} in #{key}"
                end
              elsif value.is_a?(Hash) || value.is_a?(Array)
                child_modified = replace_colors_recursive(value, key)
                modified ||= child_modified
              end
            end
          when Array
            data.each do |item|
              if item.is_a?(Hash) || item.is_a?(Array)
                child_modified = replace_colors_recursive(item, parent_key)
                modified ||= child_modified
              end
            end
          end

          modified
        end

        # Check if a property name is likely to contain a color.
        def is_color_property?(key)
          color_properties = %w[background tapBackground borderColor]

          additional_color_properties = %w[
            fontColor textColor hintColor shadowColor tintColor
            selectedColor unselectedColor backgroundColor strokeColor
            overlayColor caretColor disabledBackground
          ]

          (color_properties + additional_color_properties).include?(key.to_s)
        end

        # Process and replace a color value, returning the color key.
        def process_and_replace_color(color_value)
          if color_value.is_a?(String) && color_value.start_with?('@{') && color_value.end_with?('}')
            return color_value
          end

          if is_hex_color?(color_value)
            hex_color = normalize_hex_color(color_value)

            existing_key = find_color_key(hex_color, @extract_into_mode)

            if existing_key
              Core::Logger.debug "Found existing color: #{existing_key} = #{hex_color}"
              return existing_key
            else
              new_key = generate_color_key(hex_color, @extract_into_mode)
              @extracted_colors[@extract_into_mode][new_key] = hex_color
              Core::Logger.debug "New color found: #{new_key} = #{hex_color} (mode: #{@extract_into_mode})"
              return new_key
            end
          elsif color_value.is_a?(String) && !color_value.empty?
            if color_key_exists_anywhere?(color_value)
              Core::Logger.debug "Color key exists: #{color_value}"
              return color_value
            elsif @defined_colors_data.key?(color_value)
              Core::Logger.debug "Color key already in defined_colors: #{color_value}"
              return color_value
            else
              @undefined_colors[color_value] = nil
              Core::Logger.debug "Undefined color key found: #{color_value}"
              return color_value
            end
          else
            return color_value
          end
        end

        # A color key is considered to exist if ANY mode's palette (committed
        # or just-extracted) references it. Each key may be defined per-mode
        # with different values, but from the layout side the key itself is
        # mode-agnostic (resolution happens at runtime).
        def color_key_exists_anywhere?(key)
          @palettes.any? { |_, p| p.key?(key) } ||
            @extracted_colors.any? { |_, p| p.key?(key) }
        end

        # Find existing key for a hex color WITHIN the given mode. A collision
        # in another mode is fine — the same key name in different modes can
        # point to different hex values (that's the whole point of theming).
        # When called without a mode (spec helpers / callers outside the
        # extraction loop), fall back to the extract-into mode.
        def find_color_key(hex_color, mode = nil)
          mode ||= @extract_into_mode || DEFAULT_MODE_NAME
          palette = (@palettes[mode] || {}).merge(@extracted_colors[mode] || {})
          palette.find { |_, value| value.is_a?(String) && value.upcase == hex_color.upcase }&.first
        end

        # Generate a descriptive key name based on RGB values. Uniqueness is
        # scoped to the target mode — ColorManager.dark.red and
        # ColorManager.light.red are two separate colors sharing one key.
        def generate_color_key(hex_color, mode = nil)
          mode ||= @extract_into_mode || DEFAULT_MODE_NAME
          rgb = parse_hex_to_rgb(hex_color)
          return 'unknown_color' unless rgb

          r, g, b = rgb

          brightness = (r + g + b) / 3.0

          base_name = if brightness > 230
                        'white'
                      elsif brightness > 200
                        'pale'
                      elsif brightness > 150
                        'light'
                      elsif brightness > 100
                        'medium'
                      elsif brightness > 50
                        'dark'
                      elsif brightness > 20
                        'deep'
                      else
                        'black'
                      end

          max_diff = [r, g, b].max - [r, g, b].min
          if max_diff > 30
            if r > g && r > b
              if r - g > 50 && r - b > 50
                color_suffix = '_red'
              elsif r > b
                color_suffix = '_orange' if g > b
                color_suffix = '_pink' if b > g * 0.7
              else
                color_suffix = '_magenta'
              end
            elsif g > r && g > b
              if g - r > 50 && g - b > 50
                color_suffix = '_green'
              elsif g > b && r > b * 0.7
                color_suffix = '_yellow'
              else
                color_suffix = '_lime'
              end
            elsif b > r && b > g
              if b - r > 50 && b - g > 50
                color_suffix = '_blue'
              elsif b > r && g > r * 0.7
                color_suffix = '_cyan'
              else
                color_suffix = '_purple'
              end
            else
              color_suffix = ''
            end

            base_name = base_name + color_suffix unless base_name == 'white' || base_name == 'black'
          elsif base_name != 'white' && base_name != 'black'
            base_name = base_name + '_gray'
          end

          final_key = base_name
          counter = 2
          existing_keys = (@palettes[mode] || {}).merge(@extracted_colors[mode] || {})

          while existing_keys.key?(final_key)
            final_key = "#{base_name}_#{counter}"
            counter += 1
          end

          final_key
        end

        # Parse hex color to RGB values.
        def parse_hex_to_rgb(hex_color)
          hex = hex_color.gsub('#', '')

          case hex.length
          when 3
            hex = hex.chars.map { |c| c * 2 }.join
            [hex[0..1].to_i(16), hex[2..3].to_i(16), hex[4..5].to_i(16)]
          when 6
            [hex[0..1].to_i(16), hex[2..3].to_i(16), hex[4..5].to_i(16)]
          when 8
            [hex[0..1].to_i(16), hex[2..3].to_i(16), hex[4..5].to_i(16)]
          else
            nil
          end
        rescue
          nil
        end

        # Check if a value is a hex color.
        def is_hex_color?(value)
          return false unless value.is_a?(String)
          value.match?(/^#?([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$/)
        end

        # Normalize hex color format.
        def normalize_hex_color(hex_color)
          hex = hex_color.gsub('#', '').upcase

          if hex.length == 3
            hex = hex.chars.map { |c| c * 2 }.join
          end

          "##{hex}"
        end

        # ==========================================================
        # ColorManager (TypeScript / JavaScript) code generation.
        # ==========================================================

        def generate_color_manager
          return unless @config['generated_directory']

          generated_dir = File.join(@source_path, @config['generated_directory'])
          FileUtils.mkdir_p(generated_dir)

          ext = @config['typescript'] ? 'ts' : 'js'
          output_file = File.join(generated_dir, "ColorManager.#{ext}")

          # Attach undefined-key stubs to the extract_into_mode palette so
          # they appear as dynamic accessors (guarded against being undefined
          # at runtime).
          merged_palettes = deep_clone_palettes
          @defined_colors_data.each do |key, _|
            merged_palettes[@extract_into_mode] ||= {}
            merged_palettes[@extract_into_mode][key] ||= nil
          end

          code = generate_ts_code(merged_palettes, ext == 'ts')

          File.write(output_file, code)
          Core::Logger.info "✓ Generated ColorManager.#{ext}"
        end

        # Kept for backwards compat with existing specs.
        def generate_color_manager_js
          generate_color_manager
        end

        def deep_clone_palettes
          @palettes.each_with_object({}) do |(mode, palette), acc|
            acc[mode] = palette.dup
          end
        end

        # The full set of color keys across every palette (union). Used for
        # dynamic current-mode accessors — any key in ANY mode appears as a
        # getter on the ColorManager instance that resolves via current mode.
        def all_color_keys(merged_palettes)
          merged_palettes.values.flat_map(&:keys).uniq.sort
        end

        def generate_ts_code(merged_palettes, typescript)
          marker_header = Core::GeneratedMarker.comment_header(
            source: "ColorManager (colors from #{File.basename(@colors_file)})",
            generator: "rjui build"
          )

          nl = "\n"
          lines = []
          lines << '"use client";'
          lines << ''
          lines.concat(marker_header.split("\n"))
          lines << ''

          # --- ColorMode enum / type ---
          lines << '// Color modes discovered in colors.json. Add a new top-level'
          lines << '// mode object to colors.json to grow this list.'
          if typescript
            lines << "export const ColorMode = Object.freeze({"
            @modes.each do |mode|
              lines << "  #{mode_const(mode)}: '#{mode}',"
            end
            lines << "} as const);"
            lines << "export type ColorMode = typeof ColorMode[keyof typeof ColorMode];"
          else
            lines << "export const ColorMode = Object.freeze({"
            @modes.each do |mode|
              lines << "  #{mode_const(mode)}: '#{mode}',"
            end
            lines << "});"
          end
          lines << ''

          # --- Palettes ---
          lines << '// Per-mode palettes. Each mode holds a frozen camelCase-keyed'
          lines << '// map of color values. Missing keys fall back to `fallback_mode`.'
          @modes.each do |mode|
            palette = merged_palettes[mode] || {}
            lines << "const _#{js_ident(mode)}Palette = Object.freeze({"
            palette.keys.sort.each do |key|
              camel = snake_to_camel(key)
              value = palette[key]
              if value.is_a?(String)
                lines << "  #{camel}: '#{value}',"
              else
                lines << "  #{camel}: undefined,"
              end
            end
            lines << '});'
          end
          lines << ''

          # Raw snake_case maps (for `color(key)` lookups that need the
          # original key name from colors.json).
          #
          # Under `tsconfig strict: true`, `Object.freeze({literal})` infers
          # each palette as a tight readonly type with no string index
          # signature — so `_rawPalettes[mode][key]` (where `key: string`)
          # errors with TS7053. Declare an explicit loose index type on the
          # outer const for TS so string-keyed lookups stay legal while the
          # literal hex values are preserved at runtime.
          palette_type = typescript ? ': Record<string, Readonly<Record<string, string | undefined>>>' : ''
          lines << "const _rawPalettes#{palette_type} = Object.freeze({"
          @modes.each do |mode|
            palette = merged_palettes[mode] || {}
            lines << "  #{js_string_or_ident(mode)}: Object.freeze({"
            palette.keys.sort.each do |key|
              value = palette[key]
              value_lit = value.is_a?(String) ? "'#{value}'" : 'undefined'
              lines << "    '#{key}': #{value_lit},"
            end
            lines << '  }),'
          end
          lines << '});'
          lines << ''

          # --- Config ---
          lines << "const FALLBACK_MODE = '#{@fallback_mode}';"
          lines << 'const SYSTEM_MODE_MAPPING = Object.freeze({'
          (@system_mode_mapping || {}).each do |os_mode, project_mode|
            lines << "  #{js_string_or_ident(os_mode)}: '#{project_mode}',"
          end
          lines << '});'
          lines << "const AVAILABLE_MODES = Object.freeze([#{@modes.map { |m| "'#{m}'" }.join(', ')}]);"
          lines << ''

          # --- Class body ---
          type_suffix = typescript ? ': ColorMode' : ''
          lines << 'class ColorManagerClass {'
          if typescript
            lines << '  private _currentMode: ColorMode = FALLBACK_MODE as ColorMode;'
            lines << '  private _followSystemMode: boolean = true;'
            lines << '  private _listeners: Set<() => void> = new Set();'
            lines << '  private _mediaQuery: MediaQueryList | null = null;'
            lines << '  private _mediaListener: ((e: MediaQueryListEvent) => void) | null = null;'
          else
            lines << '  constructor() {'
            lines << '    this._currentMode = FALLBACK_MODE;'
            lines << '    this._followSystemMode = true;'
            lines << '    this._listeners = new Set();'
            lines << '    this._mediaQuery = null;'
            lines << '    this._mediaListener = null;'
            lines << '  }'
          end
          lines << ''
          # Bootstrap system-mode tracking if in browser.
          lines << (typescript ? '  init(): void {' : '  init() {')
          lines << "    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;"
          lines << "    this._mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');"
          lines << '    this._applySystemMode();'
          lines << '    this._mediaListener = () => { if (this._followSystemMode) this._applySystemMode(); };'
          lines << "    this._mediaQuery.addEventListener('change', this._mediaListener);"
          lines << '  }'
          lines << ''
          lines << "  get currentMode()#{typescript ? ': ColorMode' : ''} { return this._currentMode; }"
          lines << ''
          lines << "  setMode(mode#{type_suffix})#{typescript ? ': void' : ''} {"
          lines << '    if (!AVAILABLE_MODES.includes(mode)) {'
          lines << '      console.warn(`[ColorManager] Unknown mode: ${mode}. Ignoring.`);'
          lines << '      return;'
          lines << '    }'
          lines << '    if (this._currentMode === mode) return;'
          lines << '    this._currentMode = mode;'
          lines << '    this._notify();'
          lines << '  }'
          lines << ''
          lines << "  get followSystemMode()#{typescript ? ': boolean' : ''} { return this._followSystemMode; }"
          lines << "  set followSystemMode(v#{typescript ? ': boolean' : ''}) {"
          lines << '    this._followSystemMode = v;'
          lines << '    if (v) this._applySystemMode();'
          lines << '  }'
          lines << ''
          lines << "  subscribe(cb#{typescript ? ': () => void' : ''})#{typescript ? ': () => void' : ''} {"
          lines << '    this._listeners.add(cb);'
          lines << '    return () => { this._listeners.delete(cb); };'
          lines << '  }'
          lines << ''
          lines << "  _notify()#{typescript ? ': void' : ''} {"
          lines << '    this._listeners.forEach((cb) => { try { cb(); } catch (_) {} });'
          lines << '  }'
          lines << ''
          lines << "  _applySystemMode()#{typescript ? ': void' : ''} {"
          lines << '    if (!this._mediaQuery) return;'
          lines << "    const osMode = this._mediaQuery.matches ? 'dark' : 'light';"
          lines << '    const mapped = SYSTEM_MODE_MAPPING[osMode];'
          lines << "    if (mapped && AVAILABLE_MODES.includes(mapped#{typescript ? ' as ColorMode' : ''})) {"
          lines << "      this.setMode(mapped#{typescript ? ' as ColorMode' : ''});"
          lines << '    }'
          lines << '  }'
          lines << ''

          # color(key) — snake_case-keyed lookup in the current mode with
          # lenient fallback to FALLBACK_MODE. For explicit per-mode lookup
          # without switching, use the palette accessor (e.g. ColorManager.dark.red).
          lines << "  color(key#{typescript ? ': string' : ''})#{typescript ? ': string | undefined' : ''} {"
          lines << "    if (typeof key === 'string' && key.startsWith('@{') && key.endsWith('}')) {"
          lines << '      return undefined;'
          lines << '    }'
          lines << '    const m = this._currentMode;'
          lines << '    const p = _rawPalettes[m];'
          lines << '    if (p && p[key] !== undefined) return p[key];'
          lines << '    const fb = _rawPalettes[FALLBACK_MODE];'
          lines << '    if (fb && fb[key] !== undefined) return fb[key];'
          lines << '    if (this.isHexColor(key)) return key;'
          lines << '    console.warn(`[ColorManager] Warning: Color key "${key}" not found in any palette`);'
          lines << '    return undefined;'
          lines << '  }'
          lines << ''

          lines << "  isHexColor(value#{typescript ? ': unknown' : ''})#{typescript ? ': boolean' : ''} {"
          lines << "    if (typeof value !== 'string') return false;"
          lines << '    return /^#?([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$/.test(value);'
          lines << '  }'
          lines << ''
          lines << "  get availableModes()#{typescript ? ': readonly string[]' : ''} { return AVAILABLE_MODES; }"
          lines << ''

          # Per-mode palette accessors: ColorManager.light, ColorManager.dark, …
          @modes.each do |mode|
            lines << "  get #{snake_to_camel(mode)}() { return _#{js_ident(mode)}Palette; }"
          end
          lines << ''

          # Dynamic current-mode accessors on the instance.
          all_keys = all_color_keys(merged_palettes)
          unless all_keys.empty?
            lines << '  // Dynamic current-mode accessors (camelCase)'
            all_keys.each do |key|
              camel = snake_to_camel(key)
              lines << "  get #{camel}() { return this.color('#{key}'); }"
            end
            lines << ''
          end

          lines << '}'
          lines << ''
          lines << 'export const ColorManager = new ColorManagerClass();'
          lines << "if (typeof window !== 'undefined') { ColorManager.init(); }"
          lines << 'export default ColorManager;'
          lines << ''
          lines << Core::GeneratedMarker.comment_footer

          lines.join(nl)
        end

        def snake_to_camel(snake_case)
          parts = snake_case.to_s.split('_')
          first_part = parts.shift || ''
          first_part + parts.map(&:capitalize).join
        end

        def mode_const(mode)
          mode.to_s.upcase.gsub(/[^A-Z0-9]/, '_').gsub(/^([0-9])/, '_\1')
        end

        def js_ident(mode)
          snake_to_camel(mode.to_s.gsub(/[^A-Za-z0-9_]/, '_'))
        end

        def js_string_or_ident(mode)
          if mode.to_s.match?(/\A[A-Za-z_$][A-Za-z0-9_$]*\z/)
            mode.to_s
          else
            "'#{mode}'"
          end
        end
      end
    end
  end
end
