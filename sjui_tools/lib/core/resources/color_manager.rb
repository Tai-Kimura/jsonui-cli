# frozen_string_literal: true

require 'json'
require 'fileutils'
require_relative '../logger'

module SjuiTools
  module Core
    module Resources
      class ColorManager
        # Top-level keys in colors.json that are NOT color modes. Everything
        # else at the top level is a mode name whose value is a palette.
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
          if processed_files.any?
            Core::Logger.info "Extracting colors from #{processed_count} files (#{skipped_count} skipped)..."

            extract_colors(processed_files)

            save_colors_json if any_extracted? || @migrated

            save_defined_colors_json if @undefined_colors.any?
          end

          generate_color_manager_swift if @config['resource_manager_directory']
        end

        def apply_to_color_assets
          save_colors_json if any_extracted? || @migrated
          save_defined_colors_json if @undefined_colors.any?

          generate_color_manager_swift if @config['resource_manager_directory']
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
          color_properties = %w[background tapBackground borderColor]
          additional = %w[
            fontColor textColor hintColor shadowColor tintColor
            selectedColor unselectedColor backgroundColor strokeColor
            overlayColor caretColor disabledBackground
          ]
          (color_properties + additional).include?(key.to_s)
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

        def is_hex_color?(value)
          return false unless value.is_a?(String)
          value.match?(/^#?([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$/)
        end

        def is_transparent_color?(value)
          return false unless value.is_a?(String)
          hex = value.gsub('#', '').upcase
          return false unless hex.length == 8
          hex[-2..-1] == '00'
        end

        def normalize_hex_color(hex_color)
          hex = hex_color.gsub('#', '').upcase
          hex = hex.chars.map { |c| c * 2 }.join if hex.length == 3
          "##{hex}"
        end

        # ========================================================================
        # Swift code generation
        # ========================================================================

        def generate_color_manager_swift
          return unless @config['resource_manager_directory']

          resource_manager_dir = File.join(@source_path, @config['resource_manager_directory'])
          FileUtils.mkdir_p(resource_manager_dir)

          output_file = File.join(resource_manager_dir, 'ColorManager.swift')

          merged_palettes = deep_clone_palettes
          @defined_colors_data.each do |key, _|
            merged_palettes[@extract_into_mode] ||= {}
            merged_palettes[@extract_into_mode][key] ||= nil
          end

          File.write(output_file, generate_swift_code(merged_palettes))
          Core::Logger.info "✓ Generated ColorManager.swift"
        end

        def deep_clone_palettes
          @palettes.each_with_object({}) { |(m, p), acc| acc[m] = p.dup }
        end

        def all_color_keys(merged_palettes)
          merged_palettes.values.flat_map(&:keys).uniq.sort
        end

        def swift_enum_case(mode)
          # `light` / `dark` / `highContrast` (camelCase).
          snake_to_camel(mode)
        end

        def generate_swift_code(merged_palettes)
          timestamp = Time.now.strftime('%Y-%m-%d %H:%M:%S')
          all_keys = all_color_keys(merged_palettes)

          lines = []
          lines << '// ColorManager.swift'
          lines << '// Auto-generated file - DO NOT EDIT'
          lines << "// Generated at: #{timestamp}"
          lines << ''
          lines << 'import UIKit'
          lines << 'import SwiftUI'
          # Combine is required because `ColorManager.Observable` uses
          # `ObservableObject` + `@Published` to re-render SwiftUI views on
          # mode switch. `SwiftUI` *usually* re-exports Combine, but under
          # Xcode iOS SDK 26 / some toolchain versions that transitive
          # import fails — `@Published` errors with "initializer
          # 'init(wrappedValue:)' is not available due to missing import of
          # defining module 'Combine'" at archive time. Emit it
          # unconditionally; it's harmless when already in scope.
          lines << 'import Combine'
          lines << 'import SwiftJsonUI'
          lines << ''
          lines << 'public struct ColorManager {'
          lines << '    private init() {}'
          lines << ''

          # ---- ColorMode enum ----
          lines << '    /// Color modes discovered in colors.json. Add a new top-level mode object to colors.json to grow this list.'
          lines << '    public enum ColorMode: String, CaseIterable {'
          @modes.each do |mode|
            case_name = swift_enum_case(mode)
            if case_name == mode
              lines << "        case #{case_name}"
            else
              lines << "        case #{case_name} = \"#{mode}\""
            end
          end
          lines << '    }'
          lines << ''

          # ---- Fallback + system mapping ----
          lines << "    public static let fallbackMode: ColorMode = .#{swift_enum_case(@fallback_mode)}"
          lines << ''
          lines << '    /// Map from OS-reported appearance to project-specific mode.'
          lines << '    public static let systemModeMapping: [UIUserInterfaceStyle: ColorMode] = ['
          (@system_mode_mapping || {}).each do |os_mode, project_mode|
            os_case = os_mode == 'light' ? '.light' : (os_mode == 'dark' ? '.dark' : '.unspecified')
            lines << "        #{os_case}: .#{swift_enum_case(project_mode)},"
          end
          lines << '    ]'
          lines << ''

          # ---- Raw palettes ----
          lines << '    /// Raw snake_case-keyed palette tables per mode.'
          lines << '    fileprivate static let palettes: [ColorMode: [String: String]] = ['
          @modes.each do |mode|
            palette = merged_palettes[mode] || {}
            lines << "        .#{swift_enum_case(mode)}: ["
            palette.keys.sort.each do |key|
              value = palette[key]
              value_lit = value.is_a?(String) ? "\"#{value}\"" : 'nil as String? ?? ""'
              lines << "            \"#{key}\": #{value_lit}," unless value.nil?
            end
            lines << '        ],'
          end
          lines << '    ]'
          lines << ''

          # ---- Mutable state + observers ----
          lines << '    private static var _currentMode: ColorMode = fallbackMode'
          lines << '    private static var _followSystemMode: Bool = true'
          lines << '    private static var _observers: [UUID: () -> Void] = [:]'
          lines << ''
          lines << '    public static var currentMode: ColorMode { _currentMode }'
          lines << '    public static var followSystemMode: Bool {'
          lines << '        get { _followSystemMode }'
          lines << '        set {'
          lines << '            _followSystemMode = newValue'
          lines << '            if newValue { applySystemMode() }'
          lines << '        }'
          lines << '    }'
          lines << ''
          lines << '    /// Switch the active color mode and notify subscribers + Observable.'
          lines << '    public static func setMode(_ mode: ColorMode) {'
          lines << '        guard _currentMode != mode else { return }'
          lines << '        _currentMode = mode'
          lines << '        Observable.shared.publish(mode)'
          lines << '        _observers.values.forEach { $0() }'
          lines << '    }'
          lines << ''
          lines << '    /// Subscribe to mode changes. Returns a closure that unsubscribes.'
          lines << '    @discardableResult'
          lines << '    public static func subscribe(_ callback: @escaping () -> Void) -> () -> Void {'
          lines << '        let id = UUID()'
          lines << '        _observers[id] = callback'
          lines << '        return { _observers.removeValue(forKey: id) }'
          lines << '    }'
          lines << ''
          lines << '    /// Apply the OS appearance via systemModeMapping. Call this from the'
          lines << '    /// app delegate or when the trait collection changes. Prefer'
          lines << '    /// `applySystemMode(from:)` with the owning view/scene trait collection —'
          lines << '    /// this no-argument overload falls back to walking the active window scene'
          lines << '    /// (UIScreen.main was deprecated in iOS 16).'
          lines << '    public static func applySystemMode() {'
          lines << '        #if canImport(UIKit)'
          lines << '        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }'
          lines << '        let scene = scenes.first(where: { $0.activationState == .foregroundActive }) ?? scenes.first'
          lines << '        guard let traits = scene?.traitCollection else { return }'
          lines << '        applySystemMode(from: traits)'
          lines << '        #endif'
          lines << '    }'
          lines << ''
          lines << '    /// Explicit entry point — pass the trait collection of the owning view/scene.'
          lines << '    /// SwiftUI: use `.onChange(of: colorScheme)` and call this with a cached'
          lines << '    /// `UITraitCollection` or feed the mode directly via `setMode(_:)`.'
          lines << '    public static func applySystemMode(from traits: UITraitCollection) {'
          lines << '        #if canImport(UIKit)'
          lines << '        if let mapped = systemModeMapping[traits.userInterfaceStyle] {'
          lines << '            setMode(mapped)'
          lines << '        }'
          lines << '        #endif'
          lines << '    }'
          lines << ''

          # ---- Observable wrapper for SwiftUI ----
          lines << '    /// SwiftUI-friendly wrapper. Inject via `.environmentObject(ColorManager.Observable.shared)`'
          lines << '    /// and observe `@EnvironmentObject var theme: ColorManager.Observable` in any View.'
          lines << '    public final class Observable: ObservableObject {'
          lines << '        public static let shared = Observable()'
          lines << '        @Published public private(set) var currentMode: ColorMode = ColorManager.fallbackMode'
          lines << '        fileprivate init() {}'
          lines << '        fileprivate func publish(_ mode: ColorMode) { currentMode = mode }'
          lines << '    }'
          lines << ''

          # ---- UIKit namespace ----
          lines << '    // ========== UIKit ==========='
          lines << '    public struct uikit {'
          lines << '        private init() {}'
          lines << ''
          lines << '        /// Resolve a color key against the current mode with lenient fallback to `fallbackMode`.'
          lines << '        public static func color(for key: String) -> UIColor? {'
          lines << '            if key.hasPrefix("@{") && key.hasSuffix("}") { return nil }'
          lines << '            let mode = ColorManager._currentMode'
          lines << '            if let hex = ColorManager.palettes[mode]?[key] ?? ColorManager.palettes[ColorManager.fallbackMode]?[key], !hex.isEmpty {'
          lines << '                return UIColor.colorWithHexString(hex)'
          lines << '            }'
          lines << '            return UIColor.colorWithHexString(key)'
          lines << '        }'
          lines << ''

          # Dynamic current-mode accessors.
          all_keys.each do |key|
            camel = snake_to_camel(key)
            lines << "        public static var #{camel}: UIColor? { color(for: \"#{key}\") }"
          end
          lines << ''

          # Per-mode palette structs inside uikit.
          @modes.each do |mode|
            palette = merged_palettes[mode] || {}
            struct_name = swift_enum_case(mode)
            lines << "        /// Fixed values from `#{mode}` palette (not affected by setMode)."
            lines << "        public struct #{struct_name} {"
            lines << '            private init() {}'
            palette.keys.sort.each do |key|
              camel = snake_to_camel(key)
              hex = palette[key]
              if hex.is_a?(String)
                lines << "            public static var #{camel}: UIColor? { UIColor.colorWithHexString(\"#{hex}\") }"
              else
                lines << "            public static var #{camel}: UIColor? { nil }"
              end
            end
            lines << '        }'
          end
          lines << '    }'
          lines << ''

          # ---- SwiftUI namespace ----
          lines << '    // ========== SwiftUI ==========='
          lines << '    public struct swiftui {'
          lines << '        private init() {}'
          lines << ''
          lines << '        public static func color(for key: String) -> Color? {'
          lines << '            if key.hasPrefix("@{") && key.hasSuffix("}") { return nil }'
          lines << '            guard let ui = uikit.color(for: key) else { return nil }'
          lines << '            return Color(uiColor: ui)'
          lines << '        }'
          lines << ''
          all_keys.each do |key|
            camel = snake_to_camel(key)
            lines << "        public static var #{camel}: Color? { color(for: \"#{key}\") }"
          end
          lines << ''
          @modes.each do |mode|
            palette = merged_palettes[mode] || {}
            struct_name = swift_enum_case(mode)
            lines << "        public struct #{struct_name} {"
            lines << '            private init() {}'
            palette.keys.sort.each do |key|
              camel = snake_to_camel(key)
              lines << "            public static var #{camel}: Color? { uikit.#{struct_name}.#{camel}.map(Color.init(uiColor:)) }"
            end
            lines << '        }'
          end
          lines << '    }'
          lines << ''
          lines << '}'
          lines << ''
          lines << '// Note: UIColor.colorWithHexString(_:) is provided by the SwiftJsonUI library.'

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
