# frozen_string_literal: true

require 'core/resources/string_manager'
require 'core/config_manager'
require 'core/project_finder'
require 'core/logger'
require 'fileutils'
require 'tmpdir'
require 'json'
require 'open3'
require_relative '../../support/swift_compiler'

# The generated plural accessor picks the CLDR category in the language its
# format came from, not by the device locale.
#
# Until jsonui-cli 1.9.10 it returned String.localizedStringWithFormat(format,
# count): the format came from the app's language (SwiftJsonUI's in-app
# switch, String.currentLanguage) and the category from Locale.current. A
# device in ja-JP with the app in en drew "1 notes" — Japanese has only
# `other` (ticket sjui-plural-accessor-picks-category-by-device-locale).
#
# This arm BUILDS the generated StringManager.swift and the generated
# .stringsdict files into a macOS executable and runs it with the device
# locale set to ja_JP (-AppleLanguages / -AppleLocale), switching the app's
# language in-app as SwiftJsonUI does. Russian is the third language: its
# rules (one / few / many) differ from both en and ja.
#
# SwiftJsonUI's String.localized / String.currentLanguage are TRANSCRIBED
# below from SwiftJsonUI v10.29.4 (Extensions/StringExtension.swift) — a
# copy, not a compile against the library. The file prefix lookup is left
# out (it changes the key, not the language).
RSpec.describe 'sjui plural accessor: the category follows the app language' do
  def swiftjsonui_string_extension
    <<~SWIFT
    import Foundation
    public extension String {
        nonisolated(unsafe) static var currentLanguage: String?
        func localized(tableName: String? = nil, bundle: Bundle? = nil, value: String? = nil, comment: String = "") -> String {
            if let bundle = bundle {
                return NSLocalizedString(self, tableName: tableName, bundle: bundle, value: value ?? self, comment: comment)
            }
            if let currentLanguage = String.currentLanguage, let bundlePath = Bundle.main.path(forResource: currentLanguage, ofType: "lproj"), let bundle = Bundle(path: bundlePath) {
                return NSLocalizedString(self, tableName: nil, bundle: bundle, value: value ?? self, comment: comment)
            } else {
                return NSLocalizedString(self, comment: comment)
            }
        }
    }
    SWIFT
  end

  def probe_main
    <<~SWIFT
    import Foundation
    for language in ["en", "ru"] {
        String.currentLanguage = language
        for count in [1, 2, 5] {
            print("\\(language) \\(count): \\(StringManager.Notes.noteCount(count: count))")
        }
    }
    SWIFT
  end

  let(:temp_dir) { Dir.mktmpdir('plural_category') }
  let(:resources_dir) { File.join(temp_dir, 'Layouts', 'Resources') }
  let(:languages) { %w[en ja ru] }

  before do
    skip 'swiftc is not on PATH' unless system('which swiftc > /dev/null 2>&1')
    skip 'macOS only (the device locale is set through NSArgumentDomain)' unless RUBY_PLATFORM.include?('darwin')

    FileUtils.mkdir_p(resources_dir)
    languages.each do |l|
      FileUtils.mkdir_p(File.join(temp_dir, "#{l}.lproj"))
      File.write(File.join(temp_dir, "#{l}.lproj", 'Localizable.strings'), "\"manual_key\" = \"Manual\";\n")
    end
    File.write(File.join(resources_dir, 'strings.json'), JSON.generate(
      'notes' => {
        'note_count' => {
          'en' => { 'plural' => { 'one' => '{count} note', 'other' => '{count} notes' } },
          'ja' => { 'plural' => { 'other' => '{count}件' } },
          'ru' => { 'plural' => { 'one' => '{count} one', 'few' => '{count} few',
                                  'many' => '{count} many', 'other' => '{count} other' } }
        }
      }
    ))
    allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return(
      'layouts_directory' => 'Layouts', 'resource_manager_directory' => 'ResourceManager',
      'string_files' => languages.map { |l| "#{l}.lproj/Localizable.strings" }
    )
    allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
  end

  after { FileUtils.rm_rf(temp_dir) }

  def build_and_run(manager_swift)
    bin_dir = File.join(temp_dir, 'bin')
    FileUtils.mkdir_p(bin_dir)
    # Bundle.main of a command-line tool is the binary's directory.
    languages.each { |l| FileUtils.cp_r(File.join(temp_dir, "#{l}.lproj"), bin_dir) }
    sources = {
      'StringExtension.swift' => swiftjsonui_string_extension,
      'StringManager.swift' => manager_swift.sub(/^import SwiftJsonUI\n/, ''),
      'main.swift' => probe_main
    }.map do |name, code|
      path = File.join(temp_dir, name)
      File.write(path, code)
      path
    end
    exe = File.join(bin_dir, 'plural_probe')
    out, status = Open3.capture2e('swiftc', '-o', exe, *sources)
    raise "swiftc failed:\n#{out}" unless status.success?

    out, status = Open3.capture2e(exe, '-AppleLanguages', '(ja)', '-AppleLocale', 'ja_JP')
    raise "probe failed:\n#{out}" unless status.success?

    out
  end

  def generated
    manager = SjuiTools::Core::Resources::StringManager.new
    manager.apply_to_strings_files
    manager.generate_swift_file
    File.read(File.join(temp_dir, 'ResourceManager', 'StringManager.swift'))
  end

  # The gate's compile arm (emitted_swift_reaches_a_compiler_spec): the
  # generated file with the transcribed SwiftJsonUI extension type-checks.
  # The two examples below go further and build and run it.
  it 'type-checks the generated StringManager with its plural locale helper' do
    unit = generated.sub(/^import SwiftJsonUI\n/, '') + "\n" +
           swiftjsonui_string_extension.sub(/^import Foundation\n/, '')
    expect(unit).to include('fileprivate static func pluralLocale(bundle: Bundle?) -> Locale')
    expect(unit).to compile_as_swift
  end

  it 'draws "1 note" in en on a ja device, and ru one / few / many' do
    out = build_and_run(generated)
    expect(out).to include("en 1: 1 note\n")
    expect(out).to include("en 2: 2 notes\n")
    expect(out).to include("ru 1: 1 one\n")
    expect(out).to include("ru 2: 2 few\n")
    expect(out).to include("ru 5: 5 many\n")
  end

  it 'control: the 1.9.9 accessor (localizedStringWithFormat) draws "1 notes" in the same run' do
    old = generated.sub('String(format: format, locale: pluralLocale(bundle: bundle), count)',
                        'String.localizedStringWithFormat(format, count)')
    expect(old).to include('String.localizedStringWithFormat(format, count)')
    out = build_and_run(old)
    expect(out).to include("en 1: 1 notes\n")
    expect(out).to include("ru 2: 2 other\n")
  end
end
