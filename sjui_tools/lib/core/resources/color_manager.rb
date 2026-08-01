# frozen_string_literal: true

require 'json'
require 'fileutils'
require_relative '../logger'
require_relative '../generated_marker'
require_relative '../color_manager_core'

module SjuiTools
  module Core
    module Resources
      # iOS profile over the shared color-manager body
      # (lib/core/color_manager_core.rb — byte-identical mirror of
      # shared/core/color_manager_core.rb, pinned by
      # spec/core/shared_core_mirror_spec.rb). The themed colors.json
      # model, extraction/rewrite pipeline and key naming live in the
      # shared core; this class owns the generated ColorManager.swift.
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

        private

        def logger
          Core::Logger
        end

        # ======================================================================
        # Swift code generation
        # ======================================================================

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

        def swift_enum_case(mode)
          # `light` / `dark` / `highContrast` (camelCase).
          snake_to_camel(mode)
        end

        def generate_swift_code(merged_palettes)
          # Deterministic marker header — no timestamp. A Time.now header
          # here used to make every build rewrite ColorManager.swift,
          # breaking the "run twice, diff zero" idempotency invariant.
          marker_header = Core::GeneratedMarker.comment_header(
            source: "ColorManager (colors from #{File.basename(@colors_file)})",
            generator: 'sjui build'
          )
          all_keys = all_color_keys(merged_palettes)

          lines = []
          lines.concat(marker_header.split("\n"))
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
          lines << ''
          lines << Core::GeneratedMarker.comment_footer

          lines.join("\n")
        end
      end
    end
  end
end
