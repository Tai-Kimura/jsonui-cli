# frozen_string_literal: true

require 'core/resources/string_manager'
require 'core/config_manager'
require 'core/project_finder'
require 'rexml/document'

RSpec.describe KjuiTools::Core::Resources::StringManager, 'plural support' do
  let(:temp_dir) { Dir.mktmpdir }
  let(:config) do
    {
      'source_directory' => 'src/main',
      'package_name' => 'com.example.app'
    }
  end
  let(:source_path) { temp_dir }
  let(:layouts_dir) { File.join(temp_dir, 'src/main/assets/Layouts') }
  let(:resources_dir) { File.join(layouts_dir, 'Resources') }

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
  end

  after { FileUtils.rm_rf(temp_dir) }

  def write_strings_json(data)
    File.write(File.join(resources_dir, 'strings.json'), JSON.pretty_generate(data))
  end

  def new_manager
    described_class.new(config, source_path, resources_dir)
  end

  def write_layout(relative_path)
    path = File.join(layouts_dir, relative_path)
    FileUtils.mkdir_p(File.dirname(path))
    File.write(path, '{"type": "View"}')
    path
  end

  def read_strings_xml(lang_dir)
    REXML::Document.new(File.read(File.join(temp_dir, 'src/main/res', lang_dir, 'strings.xml')))
  end

  describe '#update_strings_xml' do
    it 'emits <plurals> with CLDR items and %d substitution for the default language' do
      write_strings_json(plural_strings)
      new_manager.send(:update_strings_xml, 'values')

      doc = read_strings_xml('values')
      plurals = doc.root.elements["plurals[@name='home_items_count']"]
      expect(plurals).not_to be_nil
      items = plurals.elements.to_a('item')
      expect(items.map { |i| i.attributes['quantity'] }).to eq(%w[one other])
      expect(items.map(&:text)).to eq(['%d item', '%d items'])

      # Plain keys still emit <string>
      expect(doc.root.elements["string[@name='home_title']"].text).to eq('Home')
      expect(doc.root.elements["string[@name='home_items_count']"]).to be_nil
    end

    it 'resolves language-specific forms for values-ja' do
      write_strings_json(plural_strings)
      new_manager.send(:update_strings_xml, 'values-ja')

      doc = read_strings_xml('values-ja')
      items = doc.root.elements["plurals[@name='home_items_count']"].elements.to_a('item')
      expect(items.map { |i| i.attributes['quantity'] }).to eq(%w[other])
      expect(items.first.text).to eq('%d件')
    end

    it 'uses positional %1$d when {count} appears more than once' do
      plural_strings['home']['items_count']['en']['plural']['other'] = '{count} of {count}'
      write_strings_json(plural_strings)
      new_manager.send(:update_strings_xml, 'values')

      doc = read_strings_xml('values')
      other = doc.root.elements["plurals[@name='home_items_count']/item[@quantity='other']"]
      expect(other.text).to eq('%1$d of %1$d')
    end

    it 'prunes the stale <string> twin when a key switches to plural, and stale managed <plurals>' do
      res_dir = File.join(temp_dir, 'src/main/res/values')
      FileUtils.mkdir_p(res_dir)
      File.write(File.join(res_dir, 'strings.xml'), <<~XML)
        <?xml version='1.0' encoding='utf-8'?>
        <resources>
            <string name='home_items_count'>old flat value</string>
            <string name='hand_written_key'>untouched</string>
            <plurals name='home_removed_count'>
                <item quantity='other'>gone</item>
            </plurals>
        </resources>
      XML

      write_strings_json(plural_strings)
      # Reached the way production reaches it: the prune only deletes
      # inside namespaces this build re-derived from a layout.
      m = new_manager
      m.process_strings([write_layout('home.json')], 1, 0)
      m.send(:update_strings_xml, 'values')

      doc = read_strings_xml('values')
      expect(doc.root.elements["string[@name='home_items_count']"]).to be_nil
      expect(doc.root.elements["plurals[@name='home_items_count']"]).not_to be_nil
      expect(doc.root.elements["plurals[@name='home_removed_count']"]).to be_nil
      # Keys outside managed prefixes are never touched
      expect(doc.root.elements["string[@name='hand_written_key']"]).not_to be_nil
    end

    it 'emits no <plurals> for a plural-free strings.json' do
      write_strings_json({ 'home' => { 'title' => 'Home' } })
      new_manager.send(:update_strings_xml, 'values')

      doc = read_strings_xml('values')
      expect(doc.root.elements.to_a('plurals')).to be_empty
    end
  end

  describe '#process_strings validation' do
    it 'raises when a layout string attribute references a plural key' do
      write_strings_json(plural_strings)
      File.write(File.join(layouts_dir, 'home.json'),
                 JSON.generate({ 'type' => 'Text', 'text' => 'items_count' }))

      expect { new_manager.process_strings([], 0, 0) }
        .to raise_error(JsonUIShared::PluralValidator::ValidationError)
    end

    it 'raises for a CLDR-invalid category (en zero)' do
      write_strings_json({ 'home' => { 'k' => {
        'en' => { 'plural' => { 'zero' => 'none', 'other' => '{count}' } }
      } } })

      expect { new_manager.process_strings([], 0, 0) }
        .to raise_error(JsonUIShared::PluralValidator::ValidationError)
    end

    it 'validates through apply_to_strings_files as well' do
      write_strings_json({ 'home' => { 'k' => {
        'en' => { 'plural' => { 'one' => 'x' } }
      } } })

      expect { new_manager.apply_to_strings_files }
        .to raise_error(JsonUIShared::PluralValidator::ValidationError)
    end
  end

  describe 'copy consistency' do
    it 'stays byte-identical to the canonical shared/core copy' do
      tool_copy = File.expand_path('../../../lib/core/plural_validator.rb', __dir__)
      shared_copy = File.expand_path('../../../../shared/core/plural_validator.rb', __dir__)
      skip 'shared/core copy not present in this layout' unless File.exist?(shared_copy)
      expect(File.read(tool_copy)).to eq(File.read(shared_copy))
    end
  end
end
