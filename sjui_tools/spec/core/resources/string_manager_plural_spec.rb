# frozen_string_literal: true

require 'core/resources/string_manager'
require 'core/config_manager'
require 'core/project_finder'
require 'core/logger'
require 'fileutils'
require 'tmpdir'
require 'json'

RSpec.describe SjuiTools::Core::Resources::StringManager, 'plural support' do
  let(:temp_dir) { Dir.mktmpdir('string_manager_plural') }
  let(:layouts_dir) { File.join(temp_dir, 'Layouts') }
  let(:resources_dir) { File.join(layouts_dir, 'Resources') }
  let(:config) do
    {
      'layouts_directory' => 'Layouts',
      'resource_manager_directory' => 'ResourceManager',
      'string_files' => ['en.lproj/Localizable.strings', 'ja.lproj/Localizable.strings']
    }
  end
  let(:manager) { described_class.new }

  let(:plural_strings) do
    {
      'home' => {
        'items_count' => {
          'en' => { 'plural' => { 'one' => '{count} item', 'other' => '{count} items' } },
          'ja' => { 'plural' => { 'other' => '{count}件' } }
        },
        'title' => { 'en' => 'Home', 'ja' => 'ホーム' }
      }
    }
  end

  before do
    FileUtils.mkdir_p(resources_dir)
    %w[en.lproj ja.lproj].each do |lproj|
      FileUtils.mkdir_p(File.join(temp_dir, lproj))
      File.write(File.join(temp_dir, lproj, 'Localizable.strings'), "\"manual_key\" = \"Manual\";\n")
    end

    allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
    allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
  end

  after { FileUtils.rm_rf(temp_dir) }

  def write_strings_json(data)
    File.write(File.join(resources_dir, 'strings.json'), JSON.pretty_generate(data))
  end

  describe '#apply_to_strings_files' do
    it 'writes plural keys to a sibling .stringsdict per language, not to .strings' do
      write_strings_json(plural_strings)
      manager.apply_to_strings_files

      en_strings = File.read(File.join(temp_dir, 'en.lproj/Localizable.strings'))
      expect(en_strings).to include('"home_title" = "Home";')
      expect(en_strings).not_to include('home_items_count')

      en_dict = File.read(File.join(temp_dir, 'en.lproj/Localizable.stringsdict'))
      expect(en_dict).to include('<key>home_items_count</key>')
      expect(en_dict).to include('<string>%#@count@</string>')
      expect(en_dict).to include('<key>one</key>')
      expect(en_dict).to include('<string>%ld item</string>')
      expect(en_dict).to include('<string>%ld items</string>')
      expect(en_dict).to include('NSStringPluralRuleType')

      ja_dict = File.read(File.join(temp_dir, 'ja.lproj/Localizable.stringsdict'))
      expect(ja_dict).to include('<string>%ld件</string>')
      expect(ja_dict).not_to include('<key>one</key>')
    end

    it 'uses positional %1$ld when {count} appears more than once' do
      plural_strings['home']['items_count']['en']['plural']['other'] = '{count} of {count} items'
      write_strings_json(plural_strings)
      manager.apply_to_strings_files

      en_dict = File.read(File.join(temp_dir, 'en.lproj/Localizable.stringsdict'))
      expect(en_dict).to include('<string>%1$ld of %1$ld items</string>')
    end

    it 'removes the generated .stringsdict when no plural keys remain' do
      write_strings_json(plural_strings)
      manager.apply_to_strings_files
      dict_path = File.join(temp_dir, 'en.lproj/Localizable.stringsdict')
      expect(File.exist?(dict_path)).to be true

      write_strings_json({ 'home' => { 'title' => 'Home' } })
      described_class.new.apply_to_strings_files
      expect(File.exist?(dict_path)).to be false
    end

    it 'does not touch a hand-written .stringsdict' do
      manual = "<?xml version=\"1.0\"?><plist version=\"1.0\"><dict></dict></plist>\n"
      File.write(File.join(temp_dir, 'en.lproj/Localizable.stringsdict'), manual)
      write_strings_json(plural_strings)
      manager.apply_to_strings_files

      expect(File.read(File.join(temp_dir, 'en.lproj/Localizable.stringsdict'))).to eq(manual)
    end

    it 'creates no .stringsdict for a plural-free strings.json' do
      write_strings_json({ 'home' => { 'title' => 'Home' } })
      manager.apply_to_strings_files
      expect(File.exist?(File.join(temp_dir, 'en.lproj/Localizable.stringsdict'))).to be false
    end
  end

  describe '#generate_swift_file' do
    it 'emits a count accessor routed through String.localizedStringWithFormat' do
      write_strings_json(plural_strings)
      manager.generate_swift_file

      swift = File.read(File.join(temp_dir, 'ResourceManager/StringManager.swift'))
      expect(swift).to include('public static func itemsCount(')
      expect(swift).to include('count: Int,')
      expect(swift).to include('let format = "home_items_count".localized(')
      expect(swift).to include('return String.localizedStringWithFormat(format, count)')
      # Plain keys keep the historical shape
      expect(swift).to include('public static func title(')
      expect(swift).to include('return "home_title".localized(')
    end
  end

  describe '#cache_strings_files + #string_registered?' do
    it 'registers .stringsdict keys without generating plain top-level accessors' do
      write_strings_json(plural_strings)
      manager.apply_to_strings_files
      manager.cache_strings_files(config['string_files'])

      expect(manager.string_registered?('home_items_count')).to be true
      expect(manager.string_registered?('manual_key')).to be true

      manager.generate_swift_file
      swift = File.read(File.join(temp_dir, 'ResourceManager/StringManager.swift'))
      expect(swift).not_to include('public static func homeItemsCount() -> String')
    end
  end

  describe '#process_strings validation' do
    it 'raises when a layout string attribute references a plural key' do
      write_strings_json(plural_strings)
      File.write(File.join(layouts_dir, 'home.json'),
                 JSON.generate({ 'type' => 'Text', 'text' => 'home_items_count' }))

      expect { manager.process_strings([], 0, 0, config) }
        .to raise_error(JsonUIShared::PluralValidator::ValidationError)
    end

    it 'raises for a CLDR-invalid category (en zero)' do
      write_strings_json({ 'home' => { 'k' => {
        'en' => { 'plural' => { 'zero' => 'none', 'other' => '{count}' } }
      } } })

      expect { manager.process_strings([], 0, 0, config) }
        .to raise_error(JsonUIShared::PluralValidator::ValidationError)
    end

    it 'passes for valid plural entries with VM-only usage' do
      write_strings_json(plural_strings)
      File.write(File.join(layouts_dir, 'home.json'),
                 JSON.generate({ 'type' => 'Text', 'text' => '@{itemsCountText}' }))

      expect { manager.process_strings([], 0, 0, config) }.not_to raise_error
    end
  end
end
