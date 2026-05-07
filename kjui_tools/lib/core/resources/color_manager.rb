# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'rexml/document'
require 'rexml/formatters/pretty'
require_relative '../logger'
require_relative '../generated_marker'

module KjuiTools
  module Core
    module Resources
      class ColorManager
        RESERVED_META_KEYS = %w[fallback_mode systemModeMapping modes].freeze
        DEFAULT_MODE_NAME = 'light'
        DEFAULT_DARK_MODE_NAME = 'dark'

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

        def process_colors(processed_files, processed_count, skipped_count, config)
          return if processed_files.empty?

          Core::Logger.info "Extracting colors from #{processed_count} files (#{skipped_count} skipped)..."

          extract_colors(processed_files)
          save_colors_json if any_extracted? || @migrated
          save_defined_colors_json if @undefined_colors.any?

          generate_color_manager_kotlin if @config['resource_manager_directory']
        end

        def apply_to_color_assets
          save_colors_json if any_extracted? || @migrated
          save_defined_colors_json if @undefined_colors.any?
          apply_to_colors_xml
        end

        attr_reader :modes, :palettes, :fallback_mode, :system_mode_mapping

        private

        def any_extracted?
          @extracted_colors.any? { |_, palette| palette.any? }
        end

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
            when :themed then ingest_themed(raw)
            when :flat then ingest_flat(raw)
            else seed_default_empty
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
            Core::Logger.warn "Failed to parse defined_colors.json: #{e.message}"
            {}
          end
        end

        def save_colors_json
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

        # Apply colors to Android colors.xml files. Android's standard resource
        # qualifiers give us TWO reliable native-side files:
        #   - `res/values/colors.xml`        ← fallback mode (light by default)
        #   - `res/values-night/colors.xml`  ← 'dark' mode (if present)
        # Other user-defined modes (`high_contrast`, `christmas`, etc.) live
        # in ColorManager.kt only — Android has no stock qualifier for them.
        def apply_to_colors_xml
          colors_xml_path = File.join(@source_path, @config['source_directory'] || 'src/main', 'res/values/colors.xml')
          colors_xml_night_path = File.join(@source_path, @config['source_directory'] || 'src/main', 'res/values-night/colors.xml')

          # Fallback / light palette → res/values/colors.xml
          write_colors_xml(colors_xml_path, @palettes[@fallback_mode] || {}, "fallback ('#{@fallback_mode}')")

          # Dark palette → res/values-night/colors.xml (Android night mode qualifier)
          if @palettes.key?(DEFAULT_DARK_MODE_NAME) && @fallback_mode != DEFAULT_DARK_MODE_NAME
            write_colors_xml(colors_xml_night_path, @palettes[DEFAULT_DARK_MODE_NAME] || {}, "night ('#{DEFAULT_DARK_MODE_NAME}')")
          end
        end

        def write_colors_xml(path, palette, label)
          unless File.exist?(path)
            Core::Logger.info "colors.xml not found at: #{path}, creating new file"
            FileUtils.mkdir_p(File.dirname(path))
            File.write(path, "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<resources>\n</resources>\n")
          end

          all_colors = palette.dup

          @defined_colors_data.each do |key, value|
            all_colors[key] = value if value && !all_colors.key?(key)
          end

          return if all_colors.empty?

          xml_content = File.read(path)
          doc = REXML::Document.new(xml_content)
          resources = doc.root

          unless resources
            Core::Logger.error "Invalid colors.xml structure at #{path}"
            return
          end

          existing_colors = {}
          resources.elements.each('color') do |elem|
            name = elem.attributes['name']
            existing_colors[name] = elem if name
          end

          colors_added = 0
          colors_updated = 0

          all_colors.each do |key, value|
            next unless value && value.is_a?(String) && value.match?(/^#?[A-Fa-f0-9]{6,8}$/)

            hex_value = value.start_with?('#') ? value.upcase : "##{value.upcase}"
            hex_value = "#FF#{hex_value[1..-1]}" if hex_value.length == 7

            if existing_colors[key]
              if existing_colors[key].text != hex_value
                existing_colors[key].text = hex_value
                colors_updated += 1
              end
            else
              color_elem = REXML::Element.new('color')
              color_elem.add_attribute('name', key)
              color_elem.text = hex_value
              resources.add_element(color_elem)
              colors_added += 1
            end
          end

          if colors_added > 0 || colors_updated > 0
            formatter = REXML::Formatters::Pretty.new(2)
            formatter.compact = true
            output = String.new
            formatter.write(doc, output)
            File.write(path, output)

            Core::Logger.info "Updated #{File.basename(File.dirname(path))}/colors.xml (#{label}): #{colors_added} added, #{colors_updated} updated"
          end
        end

        def save_defined_colors_json
          @defined_colors_data.merge!(@undefined_colors)
          FileUtils.mkdir_p(@resources_dir)
          File.write(@defined_colors_file, JSON.pretty_generate(@defined_colors_data))
          Core::Logger.info "Updated defined_colors.json with #{@undefined_colors.size} undefined color keys"
          @undefined_colors.clear
        end

        def extract_colors(processed_files)
          @modified_files = []

          Core::Logger.debug "Processing #{processed_files.size} files for colors"

          processed_files.each do |json_file|
            begin
              Core::Logger.debug "Processing file: #{json_file}"
              content = File.read(json_file)
              data = JSON.parse(content)

              modified = replace_colors_recursive(data)

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
          color_properties = %w[
            background backgroundColor borderColor strokeColor
            fontColor textColor color
            disabledBackground tapBackground pressedBackground selectedBackground focusedBackground checkedBackground rippleColor
            hintColor cancelButtonBackgroundColor cancelButtonTextColor
            tint tintColor
            gradientStartColor startColor gradientEndColor endColor gradientCenterColor centerColor
            blurOverlayColor shadowColor
          ]
          color_properties.include?(key.to_s)
        end

        def process_and_replace_color(color_value)
          return color_value if color_value.is_a?(String) && color_value.start_with?('@{')

          if is_hex_color?(color_value)
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
            else
              @undefined_colors[color_value] = nil
              return color_value
            end
          else
            return color_value
          end
        end

        def color_key_exists_anywhere?(key)
          @palettes.any? { |_, p| p.key?(key) } ||
            @extracted_colors.any? { |_, p| p.key?(key) }
        end

        def find_color_key(hex_color, mode = nil)
          mode ||= @extract_into_mode || DEFAULT_MODE_NAME
          palette = (@palettes[mode] || {}).merge(@extracted_colors[mode] || {})
          palette.find { |_, value| value.is_a?(String) && value.upcase == hex_color.upcase }&.first
        end

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

            base_name = base_name + (color_suffix || '') unless %w[white black].include?(base_name)
          elsif !%w[white black].include?(base_name)
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
          value.match?(/^#?[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?([0-9A-Fa-f]{2})?$/)
        end

        def is_transparent_color?(value)
          return false unless value.is_a?(String)
          hex = value.gsub('#', '').upcase
          return false unless hex.length == 8
          alpha = hex[0..1]
          alpha == '00'
        end

        def normalize_hex_color(hex_color)
          hex = hex_color.gsub('#', '').upcase
          hex = hex.chars.map { |c| c * 2 }.join if hex.length == 3
          "##{hex}"
        end

        # ========================================================================
        # Kotlin code generation
        # ========================================================================

        def generate_color_manager_kotlin
          return unless @config['resource_manager_directory']

          resource_manager_dir = File.join(@source_path, @config['resource_manager_directory'])
          FileUtils.mkdir_p(resource_manager_dir)

          output_file = File.join(resource_manager_dir, 'ColorManager.kt')

          merged_palettes = deep_clone_palettes
          @defined_colors_data.each do |key, _|
            merged_palettes[@extract_into_mode] ||= {}
            merged_palettes[@extract_into_mode][key] ||= nil
          end

          File.write(output_file, generate_kotlin_code(merged_palettes))
          Core::Logger.info "✓ Generated ColorManager.kt"
        end

        def deep_clone_palettes
          @palettes.each_with_object({}) { |(m, p), acc| acc[m] = p.dup }
        end

        def all_color_keys(merged_palettes)
          merged_palettes.values.flat_map(&:keys).uniq.sort
        end

        def kotlin_enum_case(mode)
          mode.to_s.upcase.gsub(/[^A-Z0-9]/, '_').gsub(/^([0-9])/, '_\1')
        end

        def kotlin_object_name(mode)
          snake_to_camel(mode.to_s.gsub(/[^A-Za-z0-9_]/, '_'))
        end

        def generate_kotlin_code(merged_palettes)
          marker_header = Core::GeneratedMarker.comment_header(
            source: "ColorManager (colors from #{File.basename(@colors_file)})",
            generator: "kjui build"
          )
          all_keys = all_color_keys(merged_palettes)

          lines = []
          lines.concat(marker_header.split("\n"))
          lines << ''
          lines << 'package com.kotlinjsonui.generated'
          lines << ''
          lines << 'import android.graphics.Color'
          lines << 'import android.util.Log'
          lines << 'import androidx.compose.runtime.mutableStateOf'
          lines << 'import androidx.compose.runtime.MutableState'
          lines << 'import androidx.compose.ui.graphics.Color as ComposeColor'
          lines << ''
          lines << 'object ColorManager {'
          lines << '    private const val TAG = "ColorManager"'
          lines << ''

          # ColorMode enum — generated from colors.json mode keys.
          lines << '    /** Color modes discovered in colors.json. Add a new top-level mode object there to grow this list. */'
          lines << '    enum class ColorMode(val raw: String) {'
          @modes.each_with_index do |mode, idx|
            trailing = idx == @modes.size - 1 ? ';' : ','
            lines << "        #{kotlin_enum_case(mode)}(\"#{mode}\")#{trailing}"
          end
          # Companion helper for raw-string → enum resolution.
          lines << ''
          lines << '        companion object {'
          lines << '            fun fromRaw(raw: String): ColorMode? = values().firstOrNull { it.raw == raw }'
          lines << '        }'
          lines << '    }'
          lines << ''

          # Fallback + system mapping.
          lines << "    val fallbackMode: ColorMode = ColorMode.#{kotlin_enum_case(@fallback_mode)}"
          lines << ''
          lines << '    /** Map from OS appearance (light/dark) to project-specific mode. */'
          lines << '    val systemModeMapping: Map<String, ColorMode> = mapOf('
          (@system_mode_mapping || {}).each_with_index do |(os_mode, project_mode), idx|
            comma = idx == (@system_mode_mapping || {}).size - 1 ? '' : ','
            lines << "        \"#{os_mode}\" to ColorMode.#{kotlin_enum_case(project_mode)}#{comma}"
          end
          lines << '    )'
          lines << ''

          # Raw palettes (snake_case → hex) per mode.
          lines << '    /** Raw hex palette per mode (snake_case keys). */'
          lines << '    private val palettes: Map<ColorMode, Map<String, String>> = mapOf('
          @modes.each_with_index do |mode, idx|
            palette = merged_palettes[mode] || {}
            trailing = idx == @modes.size - 1 ? '' : ','
            lines << "        ColorMode.#{kotlin_enum_case(mode)} to mapOf("
            palette.keys.sort.each_with_index do |key, kidx|
              value = palette[key]
              next if value.nil?
              last = kidx == palette.keys.size - 1
              lines << "            \"#{key}\" to \"#{value}\"#{last ? '' : ','}"
            end
            lines << "        )#{trailing}"
          end
          lines << '    )'
          lines << ''

          # Mutable currentMode — mutableStateOf so Compose recomposes on change.
          lines << '    /** Reactive current-mode holder. Reading `value` from @Composable code triggers recomposition. */'
          lines << '    private val _currentMode: MutableState<ColorMode> = mutableStateOf(fallbackMode)'
          lines << '    val currentMode: ColorMode get() = _currentMode.value'
          lines << ''
          lines << '    private val observers: MutableMap<Any, () -> Unit> = mutableMapOf()'
          lines << '    private var followSystemMode: Boolean = true'
          lines << ''
          lines << '    fun setMode(mode: ColorMode) {'
          lines << '        if (_currentMode.value == mode) return'
          lines << '        _currentMode.value = mode'
          lines << '        observers.values.forEach { it.invoke() }'
          lines << '    }'
          lines << ''
          lines << '    fun setFollowSystemMode(follow: Boolean) { followSystemMode = follow }'
          lines << '    fun isFollowingSystemMode(): Boolean = followSystemMode'
          lines << ''
          lines << '    /** Subscribe with any Any key; returns a closure that unsubscribes. */'
          lines << '    fun subscribe(key: Any, callback: () -> Unit): () -> Unit {'
          lines << '        observers[key] = callback'
          lines << '        return { observers.remove(key) }'
          lines << '    }'
          lines << ''
          lines << '    /** Call from Activity/Application when night mode changes, using Configuration.uiMode. */'
          lines << '    fun applySystemMode(osMode: String) {'
          lines << '        if (!followSystemMode) return'
          lines << '        systemModeMapping[osMode]?.let { setMode(it) }'
          lines << '    }'
          lines << ''

          # Views namespace.
          lines << '    // ========== Android Views =========='
          lines << '    object views {'
          lines << '        fun color(key: String): Int? {'
          lines << '            if (key.startsWith("@{") && key.endsWith("}")) return null'
          lines << '            val mode = currentMode'
          lines << '            val hex = palettes[mode]?.get(key) ?: palettes[fallbackMode]?.get(key)'
          lines << '            if (hex != null) {'
          lines << '                return try { Color.parseColor(hex) }'
          lines << '                catch (e: IllegalArgumentException) { Log.w(TAG, "Invalid hex \'$hex\' for key \'$key\'"); null }'
          lines << '            }'
          lines << '            return try { Color.parseColor(key) } catch (e: IllegalArgumentException) { null }'
          lines << '        }'
          lines << ''
          all_keys.each do |key|
            camel = snake_to_camel(key)
            lines << "        val #{camel}: Int? get() = color(\"#{key}\")"
          end
          lines << ''
          @modes.each do |mode|
            palette = merged_palettes[mode] || {}
            obj_name = kotlin_object_name(mode)
            lines << "        /** Fixed values from `#{mode}` palette (not affected by setMode). */"
            lines << "        object #{obj_name} {"
            palette.keys.sort.each do |key|
              camel = snake_to_camel(key)
              hex = palette[key]
              if hex.is_a?(String)
                lines << "            val #{camel}: Int? get() = try { Color.parseColor(\"#{hex}\") } catch (e: IllegalArgumentException) { null }"
              else
                lines << "            val #{camel}: Int? get() = null"
              end
            end
            lines << '        }'
          end
          lines << '    }'
          lines << ''

          # Compose namespace.
          lines << '    // ========== Jetpack Compose =========='
          lines << '    object compose {'
          lines << '        /** Reading this from @Composable code triggers recomposition on mode change. */'
          lines << '        fun color(key: String): ComposeColor? {'
          lines << '            val int = views.color(key) ?: return null'
          lines << '            return ComposeColor(int)'
          lines << '        }'
          lines << ''
          all_keys.each do |key|
            camel = snake_to_camel(key)
            lines << "        val #{camel}: ComposeColor? get() = color(\"#{key}\")"
          end
          lines << ''
          @modes.each do |mode|
            palette = merged_palettes[mode] || {}
            obj_name = kotlin_object_name(mode)
            lines << "        object #{obj_name} {"
            palette.keys.sort.each do |key|
              camel = snake_to_camel(key)
              lines << "            val #{camel}: ComposeColor? get() = views.#{obj_name}.#{camel}?.let { ComposeColor(it) }"
            end
            lines << '        }'
          end
          lines << '    }'
          lines << '}'
          lines << ''
          lines << Core::GeneratedMarker.comment_footer

          lines.join("\n")
        end

        def snake_to_camel(snake_case)
          parts = snake_case.to_s.split('_')
          first_part = parts.shift || ''
          first_part + parts.map(&:capitalize).join
        end
      end
    end
  end
end
