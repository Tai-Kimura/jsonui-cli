# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'rexml/document'
require 'rexml/formatters/pretty'
require_relative '../logger'
require_relative '../generated_marker'
require_relative '../color_manager_core'

module KjuiTools
  module Core
    module Resources
      # Android profile over the shared color-manager body
      # (lib/core/color_manager_core.rb — byte-identical mirror of
      # shared/core/color_manager_core.rb, pinned by
      # spec/core/shared_core_mirror_spec.rb). The themed colors.json
      # model, extraction/rewrite pipeline and key naming live in the
      # shared core; this class owns colors.xml / values-night emission
      # and the generated ColorManager.kt.
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

        def process_colors(processed_files, processed_count, skipped_count, config)
          return if processed_files.empty?

          Core::Logger.info "Extracting colors from #{processed_count} files (#{skipped_count} skipped)..."

          extract_colors(processed_files)
          save_colors_json if any_extracted? || @migrated
          save_defined_colors_json if @undefined_colors.any?

          # Unconditional: see generate_color_manager_kotlin. The emit
          # references ColorManager whether or not this key is configured.
          generate_color_manager_kotlin
        end

        def apply_to_color_assets
          save_colors_json if any_extracted? || @migrated
          save_defined_colors_json if @undefined_colors.any?
          apply_to_colors_xml
        end

        private

        def logger
          Core::Logger
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

        # ========================================================================
        # Kotlin code generation
        # ========================================================================

        # `ColorManager.kt` is not optional output. The Compose codegen emits
        # `ColorManager.compose.color(...)` for any color attribute bound to a
        # String property and imports `com.kotlinjsonui.generated.ColorManager`
        # to go with it — so a project that never configured
        # `resource_manager_directory` got an emit referencing a class the
        # build had decided not to write. That is what broke five `__binding`
        # fixtures in the android codegen host, whose staging config sets no
        # such key (plan 49 lane C).
        #
        # The package is FIXED (`com.kotlinjsonui.generated`, see
        # generate_kotlin_code), so the path is derivable rather than a
        # convention: `<source_directory>/kotlin/com/kotlinjsonui/generated`.
        # That is byte-for-byte what the shipping consumers configure by hand
        # (`app/src/main` + this suffix), so the default changes nothing for a
        # project that already declares the key.
        DEFAULT_RESOURCE_MANAGER_SUFFIX = File.join('kotlin', 'com', 'kotlinjsonui', 'generated').freeze

        def generate_color_manager_kotlin
          configured = @config['resource_manager_directory'] ||
                       File.join(@config['source_directory'] || 'src/main', DEFAULT_RESOURCE_MANAGER_SUFFIX)
          resource_manager_dir = File.join(@source_path, configured)
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
      end
    end
  end
end
