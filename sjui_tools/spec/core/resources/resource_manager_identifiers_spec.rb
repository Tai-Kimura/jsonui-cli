# frozen_string_literal: true

require 'tmpdir'
require 'json'
require 'open3'
require 'fileutils'
require 'core/swift_identifier'
require 'core/resources/color_manager'
require 'core/resources/string_manager'

# Ticket sjui-resource-managers-emit-swift-that-does-not-compile.
#
# StringManager and ColorManager name their members after strings.json /
# colors.json keys, and three kinds of key gave a file that did not compile
# (measured on a test app: 436 errors): a key that starts with a digit
# ("15 Minute Intervals" → `func 15MinuteIntervals(`), a key that is a
# reserved word (`func default(`), and a colour named like a palette (the
# palette struct `light` beside the colour `light`). Only those names change:
# a leading digit gets `_`, a reserved word is back-quoted where it is
# declared (and written plainly after a dot), and the palette of a colour's
# name is `<mode>Palette`. Measured over the downstream apps that build today, whose keys have none
# of the three shapes: the generated public names are the same before and
# after.
RSpec.describe 'generated Swift names from resource keys' do
  describe SjuiTools::Core::SwiftIdentifier do
    it 'prefixes a leading digit everywhere, and back-quotes a reserved word only where it is declared' do
      id = described_class
      expect([id.reference('15MinuteIntervals'), id.declaration('15MinuteIntervals')]).to eq(%w[_15MinuteIntervals _15MinuteIntervals])
      expect([id.reference('default'), id.declaration('default')]).to eq(['default', '`default`'])
    end

    it 'control: an ordinary name and a contextual keyword are left alone' do
      %w[logoutText open get light].each do |name|
        expect([described_class.reference(name), described_class.declaration(name)]).to eq([name, name])
      end
    end
  end

  # The compile arm: these files import UIKit, so they type-check with swiftc
  # against the iOS simulator SDK (as color_manager_empty_dictionary_spec.rb
  # checks its ColorManager) rather than through `compile_as_swift`, which
  # type-checks for the macOS host. The arms are tagged :swift_compile.
  def ios_sdk
    @ios_sdk ||= begin
      out, status = Open3.capture2e('xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path')
      status.success? ? out.strip : ''
    rescue Errno::ENOENT
      ''
    end
  end

  def stub_source
    <<~SWIFT
    import UIKit
    import SwiftUI
    extension UIColor {
        static func colorWithHexString(_ hex: String) -> UIColor { .black }
    }
    extension String {
        func localized(tableName: String? = nil, bundle: Bundle? = nil, value: String? = nil, comment: String = "") -> String { self }
    }
    SWIFT
  end

  def ios_typecheck(*sources)
    skip 'no iOS simulator SDK here (xcrun --sdk iphonesimulator); the macOS leg runs this' if ios_sdk.empty?

    Dir.mktmpdir do |dir|
      files = ([stub_source] + sources).each_with_index.map do |src, i|
        path = File.join(dir, "F#{i}.swift")
        File.write(path, src.gsub(/^import SwiftJsonUI\n/, ''))
        path
      end
      Open3.capture2e('xcrun', '--sdk', 'iphonesimulator', 'swiftc', '-typecheck',
                      '-target', 'arm64-apple-ios17.0-simulator', *files)
    end
  end

  describe 'StringManager' do
    let(:dir) { Dir.mktmpdir }
    after { FileUtils.rm_rf(dir) }

    def emit(strings_data)
      allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({ 'source_directory' => '' })
      allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(dir)
      manager = SjuiTools::Core::Resources::StringManager.new
      manager.instance_variable_set(:@strings_cache, { '24_hours' => '24 Hours', 'logout_text' => 'Logout' })
      manager.send(:generate_swift_content, strings_data)
    end

    let(:sections) do
      { 'date_picker_test' => { '15_minute_intervals' => '15 Minute Intervals', 'default' => 'Default', 'open' => 'Open',
                                'title' => 'Title' } }
    end

    it 'declares a digit-led key with `_` and a reserved word back-quoted; other names as they were' do
      swift = emit(sections)
      expect(swift).to include('public static func _15MinuteIntervals(', 'public static func `default`(',
                               'public static func open(', 'public static func title(',
                               'public static func _24Hours() -> String {', 'public static func logoutText() -> String {')
      expect(swift).not_to match(/func \d/)
    end

    it 'type-checks for iOS, with the references the generated views write', :swift_compile do
      id = SjuiTools::Core::SwiftIdentifier
      refs = %w[15MinuteIntervals default open title].map { |m| "_ = StringManager.DatePickerTest.#{id.reference(m)}()" } +
             ["_ = StringManager.#{id.reference('24Hours')}()"]
      output, status = ios_typecheck(emit(sections), "func useStrings() {\n#{refs.join("\n")}\n}\n")
      expect(status.success?).to be(true), output
    end
  end

  describe 'ColorManager' do
    def generate(colors)
      Dir.mktmpdir do |dir|
        resources = File.join(dir, 'Resources')
        FileUtils.mkdir_p(resources)
        File.write(File.join(resources, 'colors.json'), JSON.generate(colors))
        manager = SjuiTools::Core::Resources::ColorManager.new({ 'resource_manager_directory' => 'RM' }, dir, resources)
        allow(SjuiTools::Core::Logger).to receive(:info)
        manager.apply_to_color_assets
        File.read(File.join(dir, 'RM', 'ColorManager.swift'))
      end
    end

    # The flat colors.json form: its colours are the `light` palette.
    let(:clashing) { { 'light' => '#FFFFFF', 'ink' => '#111111', '4ecdc4' => '#4ECDC4' } }

    it 'names the palette `lightPalette` when a colour is named `light`, and prefixes a digit-led colour' do
      swift = generate(clashing)
      expect(swift).to include('public struct lightPalette {', 'public static var light: UIColor?', 'public static var _4ecdc4: Color?',
                               'uikit.lightPalette.ink.map(Color.init(uiColor:))')
      expect(swift).not_to include('public struct light {')
    end

    it 'control: with no colour of a palette name the palette keeps its name' do
      swift = generate({ 'light' => { 'ink' => '#111111' }, 'dark' => { 'ink' => '#EEEEEE' } })
      expect(swift).to include('public struct light {', 'public struct dark {')
      expect(swift).not_to include('Palette {')
    end

    it 'type-checks for iOS, with the references the generated views write', :swift_compile do
      id = SjuiTools::Core::SwiftIdentifier
      use = "func useColors() {\n" \
            "_ = ColorManager.swiftui.#{id.reference('light')}\n_ = ColorManager.swiftui.#{id.reference('4ecdc4')}\n" \
            "_ = ColorManager.uikit.lightPalette.ink\n}\n"
      output, status = ios_typecheck(generate(clashing), use)
      expect(status.success?).to be(true), output
    end
  end
end
