# frozen_string_literal: true

require 'spec_helper'
require 'json'
require 'tmpdir'
require 'fileutils'
require 'open3'
require_relative '../../../lib/core/resources/color_manager'
require_relative '../../../lib/swiftui/views/image_converter'
require_relative '../../../lib/swiftui/views/tab_view_converter'
require_relative '../../support/swift_compiler'

# An image could not follow the colour mode: jui build wrote one imageset from
# <name>.svg and nothing chose another (ticket jui-images-no-per-color-mode-
# variants). Now <name>.<mode>.svg is the asset <name>__<mode>, jui build
# writes the table image_modes.json beside colors.json, ColorManager.image(_:)
# answers the current mode's asset, and a generated view (which observes the
# mode) names the image through it. Without a mode's picture, or without a
# ColorManager, nothing new is written.
RSpec.describe 'an image follows the colour mode (iOS)' do
  let(:dir) { Dir.mktmpdir('sjui_image_modes') }
  let(:resources) { File.join(dir, 'Layouts', 'Resources') }
  let(:table) { { 'version' => 1, 'images' => { 'ic_probe' => { 'dark' => 'ic_probe__dark', 'sepia' => 'ic_probe__sepia' } } } }
  let(:config) { { 'layouts_directory' => 'Layouts', 'resource_manager_directory' => 'RM' } }

  before do
    FileUtils.mkdir_p(resources)
    File.write(File.join(resources, 'colors.json'), JSON.generate(
      'light' => { 'surface' => '#FFFFFF' }, 'dark' => { 'surface' => '#202020' }, 'sepia' => { 'surface' => '#F3E7D3' }
    ))
    allow(SjuiTools::Core::Logger).to receive(:info)
    allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
    allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(dir)
  end
  after { FileUtils.rm_rf(dir) }

  def with_table
    File.write(File.join(resources, 'image_modes.json'), JSON.generate(table))
  end

  def color_manager_swift
    SjuiTools::Core::Resources::ColorManager.new(config, dir, resources).apply_to_color_assets
    File.read(File.join(dir, 'RM', 'ColorManager.swift'))
  end

  def image(attrs)
    SjuiTools::SwiftUI::Views::ImageConverter.new({ 'type' => 'Image', 'id' => 'im', 'width' => 24, 'height' => 24 }.merge(attrs)).convert
  end

  describe 'what is written' do
    it 'writes nothing new for a project without a mode picture' do
      expect(color_manager_swift).not_to include('func image(')
      expect(image('srcName' => 'ic_probe')).to include('Image("ic_probe")')
    end

    it "names a written image with a mode's picture through ColorManager, and leaves any other name as it was" do
      with_table
      expect(color_manager_swift).to include('public static func image(_ name: String) -> String')
      expect(image('srcName' => 'ic_probe')).to include('Image(ColorManager.image("ic_probe"))')
      expect(image('src' => 'ic_probe')).to include('Image(ColorManager.image("ic_probe"))')
      expect(image('srcName' => 'ic_plain')).to include('Image("ic_plain")')
    end

    it 'reads a bound name through ColorManager once the project has a mode picture' do
      expect(image('srcName' => '@{icon}')).to include('Image(data.icon)')
      with_table
      expect(image('srcName' => '@{icon}')).to include('Image(ColorManager.image(data.icon))')
    end

    it 'names no ColorManager in a project without one' do
      with_table
      config.delete('resource_manager_directory')
      expect(image('srcName' => 'ic_probe')).to include('Image("ic_probe")')
      expect(image('srcName' => '@{icon}')).to include('Image(data.icon)')
    end
  end

  # ColorManager.swift run as a macOS executable, as the colour-mode arm runs
  # it (colour_mode_follows_the_os_spec.rb): UIKit's names stood in for, the
  # library's configuration records the theme mode, defaults are a map.
  IMAGE_MODE_STUBS = <<~SWIFT
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

  it "answers the current mode's asset, the base where the mode has none" do
    skip 'no swiftc with the macOS SDK here; the macOS leg runs this' unless SwiftCompiler.swiftui_available?

    with_table
    body = color_manager_swift.lines.reject { |l| l.match?(/^import (UIKit|SwiftJsonUI)$/) }.join
                              .gsub('UserDefaults.standard', 'ProbeDefaults.standard')
                              .gsub('Color.init(uiColor:)', 'probeColor').gsub('Color(uiColor: ', 'probeColor(')
    main = <<~SWIFT
      MainActor.assumeIsolated {
          @MainActor func frame(_ label: String) {
              print([label, ColorManager.image("ic_probe"), ColorManager.image("ic_plain"),
                     SwiftJsonUIConfiguration.shared.currentThemeMode].joined(separator: "|"))
          }
          ColorManager.applySystemMode(.light); frame("1 first launch, light OS")
          ColorManager.applySystemMode(.dark); frame("2 the OS turns dark")
          ColorManager.setMode(.sepia); frame("3 setMode(sepia)")
          ColorManager.applySystemMode(.light); frame("4 the OS turns light under the choice")
          ColorManager.setMode(.light); frame("5 setMode(light)")
          ColorManager.followSystemMode = true; ColorManager.applySystemMode(.dark); frame("6 back to the OS, dark")
      }
    SWIFT
    out = Dir.mktmpdir('sjui_image_modes_run') do |run_dir|
      files = { 'Stubs.swift' => IMAGE_MODE_STUBS, 'ColorManager.swift' => body, 'main.swift' => main }.map do |name, src|
        File.join(run_dir, name).tap { |path| File.write(path, src) }
      end
      exe = File.join(run_dir, 'probe')
      text, status = Open3.capture2e('xcrun', 'swiftc', '-swift-version', '5', '-o', exe, *files)
      raise "did not compile: #{text}" unless status.success?

      text, status = Open3.capture2e(exe)
      raise "did not run: #{text}" unless status.success?

      text
    end
    expect(out.lines.map { |l| l.strip.split('|')[1..] }).to eq([
      %w[ic_probe ic_plain light], %w[ic_probe__dark ic_plain dark], %w[ic_probe__sepia ic_plain sepia],
      %w[ic_probe__sepia ic_plain sepia], %w[ic_probe ic_plain light], %w[ic_probe__dark ic_plain dark]
    ])
  end
end
