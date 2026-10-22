# frozen_string_literal: true

require 'swiftui/data_model_updater'
require 'core/resources/color_manager'
require 'fileutils'
require 'json'
require 'open3'
require 'tmpdir'

# The `{Name}Data.swift` and `ColorManager.swift` sjui writes compile with no
# error and no warning in the three configurations a consumer builds with:
# Swift 5 (a SwiftPM package at tools-version 5.x), Swift 6 with no default
# isolation (a package at tools-version 6), and Swift 6 with
# SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor (a new Xcode app).
#
# Tickets sjui-data-struct-empty-layout-swift-warnings (a layout with no data:
# `value` never used, `dict` never mutated twice) and
# 2026-10-23-sjui-swift6-nonisolated-colormanager-and-binding-dict
# (ColorManager did not compile in Swift 6 without MainActor; a Data with a
# callback field warned once per binding accessor there). Measured with Xcode
# 27.2 before the fix: Swift 6 without MainActor 7 errors / 18 warnings, the
# other two 6 warnings each; after: 0 / 0 in all three.
#
# Compiled by swiftc directly (the iOS Simulator SDK, to an object), not through `compile_as_swift`, which
# type-checks a fragment against the macOS SDK: these files import UIKit, and "never mutated" is not a
# -typecheck diagnostic. Compiled to an object with DEBUG set (toDictionary(binding:) is DEBUG-only,
# and -typecheck skips the checks a build runs). `import SwiftJsonUI` is a
# module of the names these files use, with the library's public signatures.
RSpec.describe 'Data and ColorManager compile clean' do
  CLEAN_COMPILE_SWIFTJSONUI = <<~SWIFT
    import SwiftUI
    import UIKit
    public struct JsonUIRejectedKey: Equatable {
        public let key: String
        public let reason: String
        public init(key: String, reason: String) { self.key = key; self.reason = reason }
        public static func notADataField(_ key: String) -> JsonUIRejectedKey { JsonUIRejectedKey(key: key, reason: "not a data field") }
    }
    public enum JsonUITestValue {
        public enum Outcome { case accept(Any?); case reject(String) }
        public static func check(_ value: Any?, declaredClass: String) -> Outcome { .accept(value) }
    }
    public extension String {
        func localized(tableName: String? = nil, bundle: Bundle? = nil, value: String? = nil, comment: String = "") -> String { self }
    }
    public class SwiftJsonUIConfiguration: ObservableObject {
        public static let shared = SwiftJsonUIConfiguration()
        public func getColor(for identifier: Any) -> Color? { nil }
    }
    public extension UIColor {
        class func colorWithHexString(_ hex: String, alpha: CGFloat) -> UIColor { .clear }
        class func colorWithHexString(_ hex: String) -> UIColor! { .clear }
    }
  SWIFT

  # The report's shape (a partial with no data), a screen with none, one field, and many — a callback (a Data
  # with one is not Sendable), an optional bindable field, a colour.
  CLEAN_COMPILE_LAYOUTS = {
    'empty_screen' => { 'type' => 'View', 'child' => [{ 'type' => 'Label', 'text' => 'hi' }] },
    'empty_part' => { 'type' => 'View', 'role' => 'partial', 'child' => [{ 'type' => 'Label', 'text' => 'part' }] },
    'one_field' => { 'type' => 'View', 'data' => [{ 'name' => 'title', 'class' => 'String', 'defaultValue' => 'x' }],
                     'child' => [{ 'type' => 'Label', 'text' => '@{title}' }] },
    'many_fields' => { 'type' => 'View', 'data' => [
      { 'name' => 'title', 'class' => 'String', 'defaultValue' => 'x' }, { 'name' => 'count', 'class' => 'Int', 'defaultValue' => 0 },
      { 'name' => 'on', 'class' => 'Bool', 'defaultValue' => false }, { 'name' => 'ratio', 'class' => 'Double', 'defaultValue' => 0.5 },
      { 'name' => 'note', 'class' => 'String?' }, { 'name' => 'tint', 'class' => 'Color' },
      { 'name' => 'onTap', 'class' => '(() -> Void)?' }
    ], 'child' => [{ 'type' => 'Label', 'text' => '@{title}' }] }
  }.freeze

  CLEAN_COMPILE_MODES = { 'Swift 5' => %w[-swift-version 5], 'Swift 6' => %w[-swift-version 6],
            'Swift 6 + MainActor' => %w[-swift-version 6 -default-isolation MainActor] }.freeze

  def self.emitted
    @emitted ||= Dir.mktmpdir do |dir|
      FileUtils.mkdir_p(File.join(dir, 'Layouts', 'Resources'))
      CLEAN_COMPILE_LAYOUTS.each { |name, json| File.write(File.join(dir, 'Layouts', "#{name}.json"), JSON.generate(json)) }
      File.write(File.join(dir, 'Layouts', 'Resources', 'colors.json'), JSON.generate('light' => { 'ink' => '#111111' }))
      files = {}
      RSpec::Mocks.with_temporary_scope do
        RSpec::Mocks.allow_message(SjuiTools::Core::ConfigManager, :load_config).and_return(
          { 'layouts_directory' => 'Layouts', 'data_directory' => 'Data', 'styles_directory' => 'Styles' }
        )
        RSpec::Mocks.allow_message(SjuiTools::Core::ProjectFinder, :get_full_source_path).and_return(dir)
        RSpec::Mocks.allow_message(SjuiTools::Core::Logger, :info)
        $stdout = StringIO.new
        begin
          SjuiTools::SwiftUI::DataModelUpdater.new.update_data_models
          SjuiTools::Core::Resources::ColorManager.new({ 'resource_manager_directory' => 'RM' }, dir,
                                                       File.join(dir, 'Layouts', 'Resources')).apply_to_color_assets
        ensure
          $stdout = STDOUT
        end
      end
      Dir.glob(File.join(dir, '{Data,RM}', '*.swift')).sort.each { |f| files[File.basename(f)] = File.read(f) }
      files
    end
  end

  def ios_sdk
    @ios_sdk ||= begin
      out, status = Open3.capture2e('xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path')
      status.success? ? out.strip : ''
    rescue Errno::ENOENT
      ''
    end
  end

  def swiftc(*args)
    Open3.capture2e('xcrun', '--sdk', 'iphonesimulator', 'swiftc', *args)
  end

  # Every diagnostic swiftc prints for the files sjui writes, in one configuration; [] is clean.
  def diagnostics(flags)
    skip 'no iOS simulator SDK here (xcrun --sdk iphonesimulator); the macOS leg runs this' if ios_sdk.empty?
    Dir.mktmpdir do |dir|
      File.write(File.join(dir, 'SwiftJsonUI.swift'), CLEAN_COMPILE_SWIFTJSONUI)
      target = ['-sdk', ios_sdk, '-target', 'arm64-apple-ios16.0-simulator']
      out, status = swiftc('-emit-module', '-parse-as-library', '-module-name', 'SwiftJsonUI', *target,
                           '-emit-module-path', File.join(dir, 'SwiftJsonUI.swiftmodule'), File.join(dir, 'SwiftJsonUI.swift'))
      raise "the SwiftJsonUI stand-in did not build:\n#{out}" unless status.success?

      sources = self.class.emitted.map do |name, text|
        File.join(dir, name).tap { |path| File.write(path, text) }
      end
      out, status = swiftc('-c', '-wmo', '-parse-as-library', '-module-name', 'App', *target, '-I', dir, '-DDEBUG',
                           *flags, '-o', File.join(dir, 'App.o'), *sources)
      found = out.lines.grep(/: (?:warning|error):/).map { |l| l.sub("#{dir}/", '').strip }.uniq
      raise "swiftc exited #{status.exitstatus} with no diagnostic:\n#{out}" if !status.success? && found.empty?

      found
    end
  end

  it 'writes the four Data files and the ColorManager it compiles' do
    expect(self.class.emitted.keys.sort).to eq(%w[ColorManager.swift EmptyPartData.swift EmptyScreenData.swift
                                             ManyFieldsData.swift OneFieldData.swift])
    # the shapes each configuration is asked about are there
    many = self.class.emitted['ManyFieldsData.swift']
    expect(many).to include('var onTap: (() -> Void)? = nil').and include('dict["title"] = dataBinding.title')
    expect(many).to include('let noteField = dataBinding.note')
    expect(self.class.emitted['EmptyPartData.swift']).to include('for (key, _) in values').and include('let dict: [String: Any] = [:]')
  end

  CLEAN_COMPILE_MODES.each do |label, flags|
    it "compiles with no error and no warning in #{label}" do
      if flags.include?('-default-isolation')
        probe, = swiftc('-typecheck', '-default-isolation', 'MainActor', '-sdk', ios_sdk, '-target',
                        'arm64-apple-ios16.0-simulator', '-e', 'let x = 1') unless ios_sdk.empty?
        skip "this swiftc has no -default-isolation (6.2+): #{probe.to_s.lines.first}" if probe.to_s.include?('unknown argument')
      end
      expect(diagnostics(flags)).to eq([])
    end
  end
end
