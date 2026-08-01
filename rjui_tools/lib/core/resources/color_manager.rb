# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'pathname'
require_relative '../logger'
require_relative '../generated_marker'
require_relative '../color_manager_core'

module RjuiTools
  module Core
    module Resources
      # Web profile over the shared color-manager body
      # (lib/core/color_manager_core.rb — byte-identical mirror of
      # shared/core/color_manager_core.rb, pinned by
      # spec/core/shared_core_mirror_spec.rb). The themed colors.json
      # model, extraction/rewrite pipeline and key naming live in the
      # shared core; this class owns the generated ColorManager.ts|js and
      # the Tailwind @theme CSS suite.
      class ColorManager < ::JsonUIShared::ColorManagerCore
        def initialize(config, source_path, resources_dir)
          @config = config
          @source_path = source_path
          @resources_dir = resources_dir
          @colors_file = File.join(@resources_dir, 'colors.json')
          @defined_colors_file = File.join(@resources_dir, 'defined_colors.json')

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

          save_colors_json if any_extracted? || @migrated

          save_defined_colors_json if @undefined_colors.any?

          generate_color_manager if @config['generated_directory']
          generate_theme_css if @config['generated_directory']
        end

        # Apply extracted colors to color asset files.
        def apply_to_color_assets
          save_colors_json if any_extracted? || @migrated
          save_defined_colors_json if @undefined_colors.any?
        end

        private

        def logger
          Core::Logger
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
          # Same TS7053 story as _rawPalettes above: with a single-mode
          # colors.json the frozen literal infers as e.g. { light: 'light' }
          # and indexing it with `'light' | 'dark'` fails under strict. A
          # loose readonly record keeps the lookup legal for any mode set.
          mapping_type = typescript ? ': Readonly<Record<string, string | undefined>>' : ''
          lines << "const SYSTEM_MODE_MAPPING#{mapping_type} = Object.freeze({"
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

          # resolveColor(value) — what a color ATTRIBUTE means at runtime.
          # A colors.json key becomes the current mode's value; anything else
          # (hex, rgb(), a CSS color name) is handed back untouched so CSS
          # keeps accepting everything it accepted before. This is the inline
          # -style counterpart of the build-time bg-*/text-* mapping, and it
          # matches iOS Configuration.getColor / Android ColorManager.color:
          # a bound color is resolved BY NAME
          # (rjui-dynamic-color-binding-emits-raw-token).
          #
          # Unlike color(), an unresolved value is not a warning here: the
          # caller cannot tell a mistyped key from a valid CSS color name, so
          # warning on every render would cry wolf over working code.
          lines << "  resolveColor(value#{typescript ? ': unknown' : ''})#{typescript ? ': string | undefined' : ''} {"
          lines << "    if (typeof value !== 'string' || value.length === 0) return undefined;"
          lines << "    if (value.startsWith('@{') && value.endsWith('}')) return undefined;"
          lines << '    const m = this._currentMode;'
          lines << '    const p = _rawPalettes[m];'
          lines << '    if (p && p[value] !== undefined) return p[value];'
          lines << '    const fb = _rawPalettes[FALLBACK_MODE];'
          lines << '    if (fb && fb[value] !== undefined) return fb[value];'
          lines << '    return value;'
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

        # ==========================================================
        # Tailwind @theme CSS generation (web).
        # ==========================================================
        #
        # Generated components emit color utility classes by token name
        # (`bg-surface`, `text-ink`). Under Tailwind v4 those resolve only
        # when the project registers `--color-<name>` in an `@theme` block.
        # Rather than leave that mirror to the consumer (drift on every token
        # change), emit it as a @generated CSS file the consumer imports with
        # a single line. Only mode-complete (theme-safe) tokens are mirrored —
        # the same set the mapper treats as resolvable (a name missing from
        # some mode would emit a dead class anyway).
        def generate_theme_css
          keys = mode_complete_keys

          generated_dir = File.join(@source_path, @config['generated_directory'])
          FileUtils.mkdir_p(generated_dir)
          output_file = File.join(generated_dir, 'theme.css')

          base_mode = @fallback_mode || DEFAULT_MODE_NAME
          base_palette = @palettes[base_mode] || @palettes.values.first || {}

          lines = []
          lines << css_marker_header
          lines << ''
          if keys.any?
            lines << '@theme {'
            keys.sort.each do |key|
              css = css_color_value(base_palette[key])
              lines << "  --color-#{key}: #{css};" if css
            end
            lines << '}'

            # Per-mode overrides for any non-base mode (future dark support).
            # The @theme block above fixes the token→utility mapping; a mode
            # switch only needs to rebind the CSS variable under a selector.
            (@modes - [base_mode]).each do |mode|
              palette = @palettes[mode] || {}
              overrides = keys.sort.filter_map do |key|
                css = css_color_value(palette[key])
                "  --color-#{key}: #{css};" if css
              end
              next if overrides.empty?

              lines << ''
              lines << ":root[data-theme=\"#{mode}\"] {"
              lines.concat(overrides)
              lines << '}'
            end

            lines << ''
          end
          lines.concat(static_utility_lines)

          lines << ''
          lines << css_marker_footer
          lines << ''

          File.write(output_file, lines.join("\n"))
          Core::Logger.info "✓ Generated theme.css (#{keys.size} tokens)"

          announce_theme_import(output_file)
        end

        # Converter-emitted classes with no Tailwind-core backing — the
        # generated theme.css is the one stylesheet consumers import, so it
        # supplies them. Declared via `@utility` (Tailwind v4) rather than a
        # plain rule so variant forms (`md:scrollbar-hide` from a responsive
        # re-emit) resolve too. Emitted unconditionally: the converters emit
        # these classes whether or not the project has any colors.
        def static_utility_lines
          [
            '/* Converter-emitted utilities with no Tailwind-core backing. */',
            '@utility scrollbar-hide {',
            '  -ms-overflow-style: none;',
            '  scrollbar-width: none;',
            '  &::-webkit-scrollbar {',
            '    display: none;',
            '  }',
            '}'
          ]
        end

        # Convert a colors.json hex value to a CSS color. JsonUI hex is
        # alpha-FIRST (#AARRGGBB); CSS/Tailwind cannot parse that (it reads
        # #RRGGBBAA), so 8-digit values become rgba(). 3/6-digit hex is CSS
        # already. Returns nil for non-hex / nil values (skip the token).
        def css_color_value(value)
          return nil unless value.is_a?(String)

          hex = value.strip
          return nil unless hex.match?(/\A#?([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})\z/)

          hex = hex.sub(/\A#/, '')
          case hex.length
          when 3
            "##{hex}"
          when 6
            "##{hex}"
          when 8
            a = hex[0..1].to_i(16)
            r = hex[2..3].to_i(16)
            g = hex[4..5].to_i(16)
            b = hex[6..7].to_i(16)
            alpha = (a / 255.0).round(3)
            # Trim a trailing ".0" so 1.0 -> 1 (canonical CSS alpha).
            alpha = alpha.to_i if alpha == alpha.to_i
            "rgba(#{r}, #{g}, #{b}, #{alpha})"
          end
        end

        # One-time guidance: the consumer wires the generated theme with a
        # single @import. We don't edit their globals.css (not a @generated
        # file), but we compute the exact import path when we can find it.
        def announce_theme_import(theme_path)
          globals = find_globals_css
          if globals
            return if globals_imports_theme?(globals, theme_path)

            rel = relative_import_path(globals, theme_path)
            Core::Logger.info(
              "To activate the generated theme (colors + utilities), add to #{globals} (once):\n" \
              "  @import \"#{rel}\";"
            )
          else
            Core::Logger.info(
              'To activate the generated theme (colors + utilities), @import the generated ' \
              'theme.css from your global stylesheet (after `@import "tailwindcss";`).'
            )
          end
        end

        def find_globals_css
          %w[
            src/app/globals.css app/globals.css
            src/styles/globals.css styles/globals.css
            src/app/global.css app/global.css
          ].map { |p| File.join(@source_path, p) }.find { |p| File.exist?(p) }
        end

        def globals_imports_theme?(globals, theme_path)
          content = File.read(globals)
          base = File.basename(theme_path)
          content.include?(base)
        rescue StandardError
          false
        end

        def relative_import_path(globals, theme_path)
          from_dir = Pathname.new(File.dirname(globals))
          Pathname.new(theme_path).relative_path_from(from_dir).to_s
        rescue StandardError
          theme_path
        end

        def css_marker_header
          [
            '/*',
            " * #{Core::GeneratedMarker::SENTINEL} AUTO-GENERATED FILE — DO NOT EDIT",
            " * Source:    colors.json",
            " * Generator: rjui build",
            " * #{Core::GeneratedMarker::HUMAN_WARNING}",
            " * #{Core::GeneratedMarker::AGENT_WARNING}",
            ' */'
          ].join("\n")
        end

        def css_marker_footer
          "/* ══ #{Core::GeneratedMarker::END_LINE} ══ */"
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
