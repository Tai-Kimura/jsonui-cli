# frozen_string_literal: true

require 'spec_helper'
require 'json'
require 'tmpdir'
require 'fileutils'
require 'open3'
require 'rbconfig'
require_relative '../../../lib/core/resources/color_manager'
require_relative '../../../lib/swiftui/view_updater'
require_relative '../../support/swift_compiler'

# A colors.json with a dark mode did not reach an iOS screen: setMode changed
# ColorManager only and no generated view asked for its colour again;
# SwiftJsonUIConfiguration's theme mode (what Dynamic draws again on) was a
# second switch nothing connected; nothing kept a choice; nothing followed the
# OS (ticket rjui-color-mode-never-sets-data-theme; measured on a simulator).
# Now a mode change sets the theme mode, a generated view observes it and
# hands its colorScheme to ColorManager, a choice is kept and wins over the
# OS, and followSystemMode = true goes back to the last OS mode.
RSpec.describe 'the colour mode follows the OS and a kept choice (iOS)' do
  def color_manager_swift
    Dir.mktmpdir do |dir|
      resources = File.join(dir, 'Resources')
      FileUtils.mkdir_p(resources)
      File.write(File.join(resources, 'colors.json'), JSON.generate(
        'light' => { 'surface' => '#FFFFFF' }, 'dark' => { 'surface' => '#202020' }
      ))
      manager = SjuiTools::Core::Resources::ColorManager.new({ 'resource_manager_directory' => 'RM' }, dir, resources)
      allow(SjuiTools::Core::Logger).to receive(:info)
      manager.apply_to_color_assets
      File.read(File.join(dir, 'RM', 'ColorManager.swift'))
    end
  end

  # The generated file run as a macOS executable. `#if canImport(UIKit)` drops
  # the scene walk; the UIKit names it keeps are stood in for (Color(uiColor:),
  # which macOS declares unavailable, by a function), the library's
  # SwiftJsonUIConfiguration records the theme mode, and UserDefaults is a map
  # seeded with the last run's choice, so nothing is written to the machine's
  # defaults. The OS reaches it as a generated view hands it over:
  # applySystemMode(colorScheme).
  STUBS = <<~SWIFT
    import Foundation
    import SwiftUI
    public enum UIUserInterfaceStyle: Hashable, Sendable { case unspecified, light, dark }
    public final class UITraitCollection { public let userInterfaceStyle: UIUserInterfaceStyle = .light }
    public final class UIColor {
        let hex: String
        init(_ hex: String) { self.hex = hex }
        static func colorWithHexString(_ hex: String) -> UIColor { UIColor(hex) }
    }
    func probeColor(_ ui: UIColor) -> Color { .black }
    public final class SwiftJsonUIConfiguration: @unchecked Sendable {
        public static let shared = SwiftJsonUIConfiguration()
        public var currentThemeMode = "light"
        public func setThemeMode(_ mode: String) { currentThemeMode = mode }
    }
    final class ProbeDefaults: @unchecked Sendable {
        static let standard = ProbeDefaults()
        var store: [String: String] = [:]
        func string(forKey key: String) -> String? { store[key] }
        func set(_ value: String, forKey key: String) { store[key] = value }
    }
  SWIFT

  def run(kept, steps)
    skip 'no swiftc with the macOS SDK here; the macOS leg runs this' unless SwiftCompiler.swiftui_available?

    seed = kept ? "ProbeDefaults.standard.store[\"jsonui-color-mode\"] = \"#{kept}\"\n" : ''
    body = color_manager_swift.lines.reject { |l| l.match?(/^import (UIKit|SwiftJsonUI)$/) }.join.gsub('UserDefaults.standard', 'ProbeDefaults.standard')
                             .gsub('Color.init(uiColor:)', 'probeColor').gsub('Color(uiColor: ', 'probeColor(')
    main = <<~SWIFT
      #{seed}MainActor.assumeIsolated {
          @MainActor func frame(_ label: String) {
              print([label, ColorManager.currentMode.rawValue, "\\(ColorManager.followSystemMode)",
                     SwiftJsonUIConfiguration.shared.currentThemeMode, ColorManager.uikit.color(for: "surface")?.hex ?? "nil",
                     ProbeDefaults.standard.store["jsonui-color-mode"] ?? "nil"].joined(separator: "|"))
          }
      #{steps.gsub(/^/, '    ')}
      }
    SWIFT
    Dir.mktmpdir('sjui_colour_mode') do |dir|
      files = { 'Stubs.swift' => STUBS, 'ColorManager.swift' => body, 'main.swift' => main }.map do |name, src|
        File.join(dir, name).tap { |path| File.write(path, src) }
      end
      exe = File.join(dir, 'probe')
      out, status = Open3.capture2e('xcrun', 'swiftc', '-swift-version', '5', '-o', exe, *files)
      raise "did not compile: #{out}" unless status.success?

      out, status = Open3.capture2e(exe)
      raise "did not run: #{out}" unless status.success?

      out.lines.map { |l| l.strip.split('|') }
    end
  end

  it 'takes the OS at first, keeps a choice over the OS, and goes back to the OS on followSystemMode = true' do
    out = run(nil, <<~SWIFT)
      ColorManager.applySystemMode(.light); frame("1 first launch, light OS")
      ColorManager.applySystemMode(.dark); frame("2 the OS turns dark")
      ColorManager.applySystemMode(.light); frame("3 and light again")
      ColorManager.setMode(.dark); frame("4 setMode(dark)")
      ColorManager.applySystemMode(.dark); ColorManager.applySystemMode(.light); frame("5 the OS moves")
      ColorManager.followSystemMode = true; frame("6 followSystemMode = true, light OS")
      ColorManager.applySystemMode(.dark); frame("7 the OS turns dark")
    SWIFT
    expect(out.map { |o| o[1..] }).to eq([
      %w[light true light #FFFFFF nil], %w[dark true dark #202020 nil], %w[light true light #FFFFFF nil],
      %w[dark false dark #202020 dark], %w[dark false dark #202020 dark],
      %w[light true light #FFFFFF system], %w[dark true dark #202020 system]
    ])
  end

  it 'a kept choice wins over the OS at the next launch, and reaches the theme mode; "system" is the OS again' do
    out = run('dark', 'ColorManager.applySystemMode(.light); frame("next launch, light OS, dark kept")')
    expect(out.first[1..4]).to eq(%w[dark false dark #202020])
    out = run('system', 'ColorManager.applySystemMode(.dark); frame("next launch, dark OS, system kept")')
    expect(out.first[1..4]).to eq(%w[dark true dark #202020])
  end

  describe 'the generated view' do
    def write_stub(dir)
      File.join(dir, 'HomeGeneratedView.swift').tap do |path|
        File.write(path, "struct HomeGeneratedView: View {\n    @SwiftUI.Binding var data: HomeData\n}\n")
      end
    end

    it 'observes the theme mode and hands its colorScheme to ColorManager when the project has a ColorManager' do
      Dir.mktmpdir do |dir|
        updater = SjuiTools::SwiftUI::ViewUpdater.new
        updater.color_mode = true
        updater.update_generated_body(write_stub(dir), 'Text("base")', screen_id: 'home')
        content = File.read(File.join(dir, 'HomeGeneratedView.swift'))
        expect(content).to include('@ObservedObject private var sjuiThemeMode = SwiftJsonUIConfiguration.shared',
                                   '@Environment(\.colorScheme) private var sjuiColorScheme',
                                   '.onAppear { ColorManager.applySystemMode(sjuiColorScheme) }',
                                   '.onChange(of: sjuiColorScheme) { _, scheme in ColorManager.applySystemMode(scheme) }')
        # on the outer Group, as the screen marker: both rendering modes carry it
        expect(content.index('.onAppear { ColorManager')).to be < content.index('.jsonUIScreenMarker("home")')
        expect(content.index('.onAppear { ColorManager')).to be < content.index('private var generatedBody')
      end
    end

    # Through `sjui build`: the build reads sjui.config.json's
    # resource_manager_directory (where ColorManager.swift goes) to decide.
    def build_project(config_extra)
      Dir.mktmpdir('sjui_colour_mode_build') do |dir|
        tool = File.join(dir, 'sjui_tools')
        FileUtils.mkdir_p(tool)
        %w[bin lib].each { |d| raise "could not copy #{d}" unless system('cp', '-RL', File.expand_path("../../../#{d}", __dir__), tool) }
        File.write(File.join(dir, 'sjui.config.json'), JSON.generate({
          'mode' => 'swiftui', 'project_name' => 'Probe', 'project_file_name' => 'Probe', 'source_directory' => 'Probe',
          'layouts_directory' => 'Layouts', 'resources_directory' => 'Resources', 'view_directory' => 'View',
          'data_directory' => 'Data', 'viewmodel_directory' => 'ViewModel', 'use_network' => true
        }.merge(config_extra)))
        FileUtils.mkdir_p(File.join(dir, 'Probe.xcodeproj'))
        FileUtils.mkdir_p(File.join(dir, 'Probe', 'Layouts'))
        File.write(File.join(dir, 'Probe', 'Layouts', 'home.json'), JSON.generate('type' => 'View', 'id' => 'root', 'background' => '#FFFFFF'))
        log, = Open3.capture2e(RbConfig.ruby, File.join(tool, 'bin', 'sjui'), 'build', chdir: dir)
        view = Dir.glob(File.join(dir, 'Probe', '**', 'HomeGeneratedView.swift')).first
        raise "no generated view: #{log}" unless view

        File.read(view)
      end
    end

    it 'sjui build writes it when sjui.config.json has a resource_manager_directory, and not when it has none' do
      with = build_project('resource_manager_directory' => 'ResourceManager')
      expect(with).to include('.onChange(of: sjuiColorScheme) { _, scheme in ColorManager.applySystemMode(scheme) }')
      without = build_project({})
      expect(without).not_to include('sjuiColorScheme')
    end

    it 'names no ColorManager in a project without one' do
      Dir.mktmpdir do |dir|
        SjuiTools::SwiftUI::ViewUpdater.new.update_generated_body(write_stub(dir), 'Text("base")', screen_id: 'home')
        content = File.read(File.join(dir, 'HomeGeneratedView.swift'))
        expect(content).not_to include('ColorManager', 'sjuiThemeMode', 'sjuiColorScheme')
      end
    end
  end
end
