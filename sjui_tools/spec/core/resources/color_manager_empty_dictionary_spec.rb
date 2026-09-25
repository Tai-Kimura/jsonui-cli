# frozen_string_literal: true

require 'tmpdir'
require 'json'
require 'open3'
require 'fileutils'
require 'core/resources/color_manager'

# sjui-color-manager-emits-an-empty-dictionary-as-array-literal.
#
# ColorManager.swift writes its two dictionaries — each mode's palette and
# systemModeMapping — one entry per line between `[` and `]`. With no entries
# that is `[` `]`, which Swift reads as an ARRAY literal, and the
# dictionary-typed declaration stops the build: "use [:] to get an empty
# dictionary literal". It was hit by the iOS codegen conformance host run over
# a corpus with no colours; every input below reaches it.
#
# kjui (`mapOf()`) and rjui (`Object.freeze({})`) emit valid empty literals
# for the same five inputs — measured 2026-09-25 by compiling their output
# (the KotlinJsonUI conformance host's compileDebugKotlin, and tsc --strict),
# each with a planted type error as the negative control. The defect was the
# Swift emitter's alone.
RSpec.describe 'ColorManager.swift with an empty dictionary' do
  EMPTY_INPUTS = {
    'no colors.json at all' => nil,
    'a mode whose palette is {}' => { 'light' => { 'ink' => '#111111' }, 'dark' => {} },
    'a systemModeMapping declared {}' => { 'light' => { 'ink' => '#111111' }, 'systemModeMapping' => {} },
    'modes that are neither light nor dark' => { 'highContrast' => { 'ink' => '#000000' } },
    'a palette whose values are all null' => { 'light' => { 'ink' => nil } }
  }.freeze

  def generate(colors)
    Dir.mktmpdir do |dir|
      resources = File.join(dir, 'Resources')
      FileUtils.mkdir_p(resources)
      File.write(File.join(resources, 'colors.json'), JSON.generate(colors)) if colors
      manager = SjuiTools::Core::Resources::ColorManager.new(
        { 'resource_manager_directory' => 'RM' }, dir, resources
      )
      allow(SjuiTools::Core::Logger).to receive(:info)
      manager.apply_to_color_assets
      File.read(File.join(dir, 'RM', 'ColorManager.swift'))
    end
  end

  # The file imports UIKit, so it type-checks against the iOS simulator SDK,
  # not the macOS one the SwiftUI-fragment arms use. `import SwiftJsonUI` is
  # replaced by the one symbol the file takes from it; a new dependency on the
  # library would fail here by name rather than pass unnoticed.
  LIBRARY_STUB = <<~SWIFT
    import UIKit
    extension UIColor {
        static func colorWithHexString(_ hex: String) -> UIColor { .black }
    }
  SWIFT

  def ios_sdk
    @ios_sdk ||= begin
      out, status = Open3.capture2e('xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path')
      status.success? ? out.strip : ''
    rescue Errno::ENOENT
      ''
    end
  end

  def ios_typecheck(emitted)
    skip 'no iOS simulator SDK here (xcrun --sdk iphonesimulator); the macOS leg runs this' if ios_sdk.empty?

    Dir.mktmpdir do |dir|
      stub = File.join(dir, 'Stub.swift')
      file = File.join(dir, 'ColorManager.swift')
      File.write(stub, LIBRARY_STUB)
      File.write(file, emitted.sub(/^import SwiftJsonUI\n/, ''))
      Open3.capture2e('xcrun', '--sdk', 'iphonesimulator', 'swiftc', '-typecheck',
                      '-target', 'arm64-apple-ios16.0-simulator', stub, file)
    end
  end

  EMPTY_INPUTS.each do |label, colors|
    context "with #{label}" do
      let(:emitted) { generate(colors) }

      it 'writes no dictionary as `[` `]`' do
        expect(emitted).not_to match(/(?:= |: )\[\n\s*\],?\n/)
        expect(emitted).to include('[:]')
      end

      it 'type-checks for iOS' do
        output, status = ios_typecheck(emitted)
        expect(status.success?).to be(true), output
      end
    end
  end

  # The fix changes only the empty case: a populated file is the bytes it was.
  it 'leaves populated dictionaries as they were' do
    emitted = generate(
      'light' => { 'ink' => '#111111', 'paper' => '#FFFFFF' },
      'dark' => { 'ink' => '#EEEEEE', 'paper' => '#000000' }
    )
    expect(emitted).to include(<<~SWIFT)
      public static let systemModeMapping: [UIUserInterfaceStyle: ColorMode] = [
              .light: .light,
              .dark: .dark,
          ]
    SWIFT
    expect(emitted).to include(<<~SWIFT)
      fileprivate static let palettes: [ColorMode: [String: String]] = [
              .light: [
                  "ink": "#111111",
                  "paper": "#FFFFFF",
              ],
              .dark: [
                  "ink": "#EEEEEE",
                  "paper": "#000000",
              ],
          ]
    SWIFT
  end

  it 'type-checks a populated file too' do
    output, status = ios_typecheck(generate('light' => { 'ink' => '#111111' }, 'dark' => { 'ink' => '#EEEEEE' }))
    expect(status.success?).to be(true), output
  end
end
