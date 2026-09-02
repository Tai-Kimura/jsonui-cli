# frozen_string_literal: true

require 'json'
require 'fileutils'

module JsonUIShared
  # Shared body of the three toolchain ColorManagers: the themed
  # colors.json model (modes / fallback / systemModeMapping, flat-schema
  # migration), the defined_colors ledger, and the extraction pipeline
  # that rewrites raw hex values in layouts into palette keys. Canonical
  # copy lives in shared/core/color_manager_core.rb; the per-tool copies
  # under <tool>/lib/core/ must stay byte-identical (pinned by each
  # tool's shared_core_mirror_spec).
  #
  # Platform outputs stay in the profile
  # (<tool>/lib/core/resources/color_manager.rb): the generated
  # ColorManager.swift / .kt / .ts|.js, Android colors.xml / values-night,
  # the web Tailwind @theme CSS suite, and each tool's process/apply
  # orchestration. The only hook the core needs is `logger`.
  #
  # Unified 2026-08-02 (W3-2, file 6). Divergences resolved toward the
  # correct side:
  #   - 8-digit hex is alpha-FIRST (#AARRGGBB) everywhere — the convention
  #     rjui's css_color_value already documents and kjui's colors.xml
  #     writer already assumes. sjui read the alpha from the WRONG END
  #     (named 8-digit colors from AARRGG and detected transparency on the
  #     trailing byte), and rjui's own key naming did the same
  #   - fully transparent 8-digit values collapse to the shared
  #     'transparent' key on every platform (was sjui/kjui-only)
  #   - the extraction property list is the cross-tool union (kjui had a
  #     much wider list — gradient/pressed/ripple etc.; layouts are shared,
  #     so per-tool coverage gaps meant per-platform keying divergence)
  #   - hue-carrying near-white/near-black colors demote to pale/deep and
  #     keep their hue suffix (rjui semantics: bare white/black discard
  #     the hue and, on the web, collide with Tailwind's fixed builtins)
  #   - the orange/pink discrimination is a proper either/or (sjui/kjui
  #     semantics; rjui's fall-through overwrote orange with pink whenever
  #     b > 0.7g)
  class ColorManagerCore
    # Top-level keys in colors.json that are NOT color modes. Everything
    # else at the top level is a mode name whose value is a palette.
    RESERVED_META_KEYS = %w[fallback_mode systemModeMapping modes].freeze
    DEFAULT_MODE_NAME = 'light'
    DEFAULT_DARK_MODE_NAME = 'dark'

    # Layout attributes whose String values are color-like — the
    # cross-tool union (layouts are shared; every tool must key the same
    # attributes or the platforms drift apart).
    COLOR_PROPERTY_NAMES = %w[
      background backgroundColor tapBackground pressedBackground
      selectedBackground focusedBackground checkedBackground
      disabledBackground rippleColor
      borderColor strokeColor
      fontColor textColor color hintColor
      shadowColor tintColor tint
      selectedColor unselectedColor
      overlayColor caretColor blurOverlayColor
      cancelButtonBackgroundColor cancelButtonTextColor
      gradientStartColor startColor gradientEndColor endColor
      gradientCenterColor centerColor
    ].freeze

    attr_reader :modes, :palettes, :fallback_mode, :system_mode_mapping

    # Names registered in EVERY mode — the curated vocabulary a theme
    # mirror can rely on. Machine-extracted colors land in one mode only,
    # so they are never mode-complete until a human promotes them.
    def mode_complete_keys
      return [] if @modes.empty?

      @modes.map { |m| (@palettes[m] || {}).keys }.reduce(:&)
    end

    # name => hex in the fallback mode, for resolving a non-theme-safe
    # name back to a displayable value.
    def fallback_hexes
      mode = @fallback_mode || DEFAULT_MODE_NAME
      (@palettes[mode] || @palettes.values.first || {}).dup
    end

    #: Set when colors.json existed but could not be parsed. Distinct from
    #: an absent file and from an empty one, which are both ordinary states
    #: for a project that has not defined colours yet.
    def load_failed?
      !@load_failure.nil?
    end

    def load_failure_message
      @load_failure
    end

    private

    # ---- platform profile hooks ------------------------------------------

    def logger
      raise NotImplementedError, 'platform profile must define logger'
    end

    # ----------------------------------------------------------------------

    def any_extracted?
      @extracted_colors.any? { |_, palette| palette.any? }
    end

    def load_colors_json
      @migrated = false
      @palettes = {}
      @modes = []
      @fallback_mode = nil
      @system_mode_mapping = nil
      @load_failure = nil

      if File.exist?(@colors_file)
        # A FAILURE IS NOT AN EMPTY FILE. This used to hand `nil` to
        # detect_schema, which answers :empty for it — the same answer it
        # gives for a file that is absent and for one holding `{}`. Three
        # different situations became one state, and nothing downstream
        # could tell them apart, so an unreadable file was treated as a
        # project that has not defined any colours yet.
        #
        # Two things followed. The generated ColorManager came out with
        # every colour `undefined` — syntactically valid, so it builds and
        # type-checks and only fails at runtime. And, worse, the seeded
        # palette is a palette like any other, so the write-back below
        # replaced the unreadable file with a valid-looking one holding
        # only the colours this run happened to extract from layouts.
        # Measured: a file with `brand_primary` defined came back holding
        # `dark_cyan` and `pale_cyan` and nothing else, exit 0. The text
        # the author would have fixed was gone, and the next build parses
        # the replacement without complaint.
        raw = begin
          JSON.parse(File.read(@colors_file))
        rescue JSON::ParserError => e
          logger.warn "Failed to parse colors.json: #{e.message}"
          @load_failure = e.message
          nil
        end

        if @load_failure
          # Seeded so nothing downstream crashes on a nil palette, never
          # persisted: `load_failed?` gates every write.
          seed_default_empty
        else
          case detect_schema(raw)
          when :themed then ingest_themed(raw)
          when :flat then ingest_flat(raw)
          else seed_default_empty
          end
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

    def detect_schema(raw)
      return :empty unless raw.is_a?(Hash)
      return :empty if raw.empty?

      content_keys = raw.keys - RESERVED_META_KEYS
      return :empty if content_keys.empty?

      case raw[content_keys.first]
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
                 ordered + (@palettes.keys - ordered)
               else
                 @palettes.keys
               end

      @fallback_mode ||= @modes.include?(DEFAULT_MODE_NAME) ? DEFAULT_MODE_NAME : @modes.first
      @system_mode_mapping ||= default_system_mode_mapping
    end

    def ingest_flat(raw)
      logger.info "Migrating colors.json from flat schema to themed (default mode: '#{DEFAULT_MODE_NAME}')"
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
    #   1. @config['extract_into_mode'] if present (created when missing)
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

    def load_defined_colors_json
      return {} unless File.exist?(@defined_colors_file)

      begin
        JSON.parse(File.read(@defined_colors_file))
      rescue JSON::ParserError => e
        logger.warn "Failed to parse defined_colors.json: #{e.message}"
        {}
      end
    end

    def save_colors_json
      # Never write over a file we could not read. The palette in memory is
      # the seeded default plus whatever this run extracted, so writing it
      # back replaces the author's text with a valid-looking file holding
      # only the extracted colours — and the definitions that were in there
      # cannot be recovered from it afterwards.
      if load_failed?
        logger.error "colors.json was not written: it could not be parsed " \
                     "(#{@load_failure}). Fix the file; this run left it as " \
                     "it is rather than replacing it with the colours it " \
                     "extracted."
        return
      end
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
        logger.info "Updated colors.json with #{total_new} new colors across #{@extracted_colors.size} mode(s)"
      elsif @migrated
        logger.info "Migrated colors.json to themed schema"
      end

      @extracted_colors.clear
      @migrated = false
    end

    def save_defined_colors_json
      return if load_failed?

      @defined_colors_data.merge!(@undefined_colors)
      FileUtils.mkdir_p(@resources_dir)
      File.write(@defined_colors_file, JSON.pretty_generate(@defined_colors_data))
      logger.info "Updated defined_colors.json with #{@undefined_colors.size} undefined color keys"
      @undefined_colors.clear
    end

    def extract_colors(processed_files)
      @modified_files = []

      logger.debug "Processing #{processed_files.size} files for colors"

      processed_files.each do |json_file|
        begin
          logger.debug "Processing file: #{json_file}"
          content = File.read(json_file)
          data = JSON.parse(content)

          modified = replace_colors_recursive(data)

          if modified
            File.write(json_file, JSON.pretty_generate(data))
            @modified_files << json_file
            logger.debug "Updated colors in: #{json_file}"
          end
        rescue JSON::ParserError => e
          logger.warn "Failed to parse #{json_file}: #{e.message}"
        rescue => e
          logger.error "Error processing #{json_file}: #{e.message}"
        end
      end

      if @modified_files.any?
        logger.info "Replaced colors in #{@modified_files.size} files"
      end
    end

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
            end
          end
        end

        data.each do |key, value|
          if is_color_property?(key) && value.is_a?(String)
            next if value.start_with?('@{') && value.end_with?('}')

            new_value = process_and_replace_color(value)
            if new_value != value
              data[key] = new_value
              modified = true
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

    def is_color_property?(key)
      COLOR_PROPERTY_NAMES.include?(key.to_s)
    end

    def process_and_replace_color(color_value)
      if color_value.is_a?(String) && color_value.start_with?('@{') && color_value.end_with?('}')
        return color_value
      end

      if is_hex_color?(color_value)
        # Any 8-digit hex with alpha 00 collapses to the 'transparent' key,
        # shared across ALL modes (theme switching doesn't change transparency).
        if is_transparent_color?(color_value)
          unless color_key_exists_anywhere?('transparent')
            @extracted_colors[@extract_into_mode]['transparent'] ||= '#00000000'
          end
          return 'transparent'
        end

        hex_color = normalize_hex_color(color_value)

        existing_key = find_color_key(hex_color, @extract_into_mode)

        if existing_key
          return existing_key
        else
          new_key = generate_color_key(hex_color, @extract_into_mode)
          @extracted_colors[@extract_into_mode][new_key] = hex_color
          return new_key
        end
      elsif color_value.is_a?(String) && !color_value.empty?
        if color_key_exists_anywhere?(color_value)
          return color_value
        elsif @defined_colors_data.key?(color_value)
          return color_value
        elsif !color_key_shaped?(color_value)
          # Not a hex, not a declared key, and not shaped like one either —
          # a platform literal such as `Color.Green` reaching this through a
          # data section's `defaultValue`. Registering it would put a key
          # holding a `.` into defined_colors.json, and every generated
          # ColorManager then emits `val Color.Green`, which is an extension
          # property on Color and does not compile (measured on the sample
          # app 2026-09-02). The value passes through untouched; the codegen
          # emits it as the literal it already is.
          Core::Logger.warn "Not treating '#{color_value}' as a color key (not a valid key name) — passing it through"
          return color_value
        else
          @undefined_colors[color_value] = nil
          return color_value
        end
      else
        return color_value
      end
    end

    # A color key is considered to exist if ANY mode's palette (committed
    # or just-extracted) references it — the key itself is mode-agnostic
    # from the layout side (resolution happens at runtime).
    def color_key_exists_anywhere?(key)
      @palettes.any? { |_, p| p.key?(key) } ||
        @extracted_colors.any? { |_, p| p.key?(key) }
    end

    # Could this string be a color KEY at all? A key ends up as an Android
    # resource name and as a generated Kotlin/Swift property, so it can hold
    # only letters, digits and underscores. Anything else reaching the
    # colour path is a value of some other kind — a platform literal, an
    # expression — and must not be recorded as an undefined colour.
    def color_key_shaped?(value)
      value.match?(/\A[A-Za-z_][A-Za-z0-9_]*\z/)
    end

    # Find existing key for a hex color WITHIN the given mode. A collision
    # in another mode is fine — the same key name in different modes can
    # point to different hex values (that's the whole point of theming).
    def find_color_key(hex_color, mode = nil)
      mode ||= @extract_into_mode || DEFAULT_MODE_NAME
      palette = (@palettes[mode] || {}).merge(@extracted_colors[mode] || {})
      palette.find { |_, value| value.is_a?(String) && value.upcase == hex_color.upcase }&.first
    end

    # Generate a descriptive key name based on RGB values. Uniqueness is
    # scoped to the target mode.
    def generate_color_key(hex_color, mode = nil)
      mode ||= @extract_into_mode || DEFAULT_MODE_NAME
      rgb = parse_hex_to_rgb(hex_color)
      return 'unknown_color' unless rgb

      r, g, b = rgb
      brightness = (r + g + b) / 3.0

      base_name = if brightness > 230 then 'white'
                  elsif brightness > 200 then 'pale'
                  elsif brightness > 150 then 'light'
                  elsif brightness > 100 then 'medium'
                  elsif brightness > 50 then 'dark'
                  elsif brightness > 20 then 'deep'
                  else 'black'
                  end

      max_diff = [r, g, b].max - [r, g, b].min
      color_suffix = nil
      if max_diff > 30
        if r > g && r > b
          if r - g > 50 && r - b > 50
            color_suffix = '_red'
          elsif r > b
            color_suffix = g > b ? '_orange' : (b > g * 0.7 ? '_pink' : nil)
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
        end

        # Hue-carrying colors must never collapse to bare `white`/`black`:
        # bare names discard the hue (#DBEAFE is a blue, not a white) and,
        # on the web, collide with Tailwind's fixed builtins (bg-white
        # never follows dark mode). Demote to pale/deep and keep the
        # suffix; bare white/black remain reserved for true neutrals.
        if color_suffix
          base_name = 'pale' if base_name == 'white'
          base_name = 'deep' if base_name == 'black'
          base_name += color_suffix
        end
      elsif !%w[white black].include?(base_name)
        base_name += '_gray'
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

    # Parse hex color to RGB. JsonUI 8-digit hex is alpha-FIRST
    # (#AARRGGBB) — strip the alpha byte before reading RGB.
    def parse_hex_to_rgb(hex_color)
      hex = hex_color.gsub('#', '')
      hex = hex.chars.map { |c| c * 2 }.join if hex.length == 3
      hex = hex[2..7] if hex.length == 8

      return nil unless hex.length == 6

      [hex[0..1].to_i(16), hex[2..3].to_i(16), hex[4..5].to_i(16)]
    rescue
      nil
    end

    def is_hex_color?(value)
      return false unless value.is_a?(String)
      value.match?(/^#?([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$/)
    end

    # JsonUI 8-digit hex is alpha-FIRST (#AARRGGBB): fully transparent
    # means the LEADING byte is 00.
    def is_transparent_color?(value)
      return false unless value.is_a?(String)
      hex = value.gsub('#', '').upcase
      return false unless hex.length == 8
      hex[0..1] == '00'
    end

    def normalize_hex_color(hex_color)
      hex = hex_color.gsub('#', '').upcase
      hex = hex.chars.map { |c| c * 2 }.join if hex.length == 3
      "##{hex}"
    end

    def deep_clone_palettes
      @palettes.each_with_object({}) { |(m, p), acc| acc[m] = p.dup }
    end

    # The full set of color keys across every palette (union), for
    # dynamic current-mode accessors in the generated managers.
    def all_color_keys(merged_palettes)
      merged_palettes.values.flat_map(&:keys).uniq.sort
    end

    def snake_to_camel(snake_case)
      parts = snake_case.to_s.split('_')
      first_part = parts.shift || ''
      first_part + parts.map(&:capitalize).join
    end
  end
end
