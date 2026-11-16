# frozen_string_literal: true

require 'tmpdir'
require 'fileutils'
require 'rexml/document'
require 'core/resources/string_manager'
require 'core/config_manager'
require 'core/project_finder'

# Ticket jui-strings-language-code-with-script-subtag-lost.
RSpec.describe KjuiTools::Core::Resources::StringManager, 'language codes with a script or a region' do
  let(:temp_dir) { Dir.mktmpdir }
  let(:config) { { 'source_directory' => 'src/main', 'package_name' => 'com.example.app' } }
  let(:resources_dir) { File.join(temp_dir, 'src/main/assets/Layouts/Resources') }
  let(:plural) { ->(v) { { 'plural' => { 'other' => "{count} #{v}" } } } }
  let(:strings) do
    {
      'home' => {
        'hello' => { 'en' => 'EN', 'zh-Hant' => 'HANT', 'zh-Hans' => 'HANS', 'zh' => 'ZH', 'pt-BR' => 'PTBR', 'ko' => 'KO', 'ja' => 'JA' },
        'items' => { 'en' => plural.call('EN'), 'zh-Hant' => plural.call('HANT'), 'zh-Hans' => plural.call('HANS'),
                     'zh' => plural.call('ZH'), 'pt-BR' => plural.call('PTBR'), 'ko' => plural.call('KO'), 'ja' => plural.call('JA') }
      }
    }
  end

  before { FileUtils.mkdir_p(resources_dir) }
  after { FileUtils.rm_rf(temp_dir) }

  def build(lang_dir, data = strings)
    File.write(File.join(resources_dir, 'strings.json'), JSON.pretty_generate(data))
    described_class.new(config, temp_dir, resources_dir).send(:update_strings_xml, lang_dir)
    REXML::Document.new(File.read(File.join(temp_dir, 'src/main/res', lang_dir, 'strings.xml')))
  end

  {
    'values-b+zh+Hant' => 'HANT', 'values-b+zh+Hans' => 'HANS', 'values-zh-rTW' => 'HANT', 'values-zh-rCN' => 'HANS',
    'values-zh-rTW-night' => 'HANT', 'values-zh' => 'ZH', 'values-b+pt+BR' => 'PTBR', 'values-pt-rBR' => 'PTBR',
    'values-ko' => 'KO', 'values-ja-land' => 'JA', 'values' => 'EN', 'values-land' => 'EN', 'values-night' => 'EN'
  }.each do |dir, text|
    it "gives #{dir} the text and the plural forms of #{text}" do
      doc = build(dir)
      expect(doc.root.elements["string[@name='home_hello']"].text).to eq(text)
      expect(doc.root.elements["plurals[@name='home_items']/item"].text).to eq("%d #{text}")
    end
  end

  it 'does not give a Traditional output the zh text: it shows the default language and says so' do
    data = { 'home' => { 'k' => { 'en' => 'EN', 'zh' => 'ZH' } } }
    expect(KjuiTools::Core::Logger).to receive(:warn).once.with(/values-zh-rTW: 1 key\(s\) have no zh-TW text.*home_k/)
    allow(KjuiTools::Core::Logger).to receive(:info)
    doc = build('values-zh-rTW', data)
    expect(doc.root.elements["string[@name='home_k']"].text).to eq('EN')
  end

  it 'keeps the zh text in a Simplified output, with nothing to say' do
    data = { 'home' => { 'k' => { 'en' => 'EN', 'zh' => 'ZH' } } }
    expect(KjuiTools::Core::Logger).not_to receive(:warn)
    allow(KjuiTools::Core::Logger).to receive(:info)
    expect(build('values-zh-rCN', data).root.elements["string[@name='home_k']"].text).to eq('ZH')
  end

  it 'says nothing for a text with no language, or a directory with no language' do
    data = { 'home' => { 'a' => 'plain', 'b' => { 'en' => 'EN' } } }
    expect(KjuiTools::Core::Logger).not_to receive(:warn)
    allow(KjuiTools::Core::Logger).to receive(:info)
    build('values-night', data)
  end

  describe '#get_translated_value' do
    let(:manager) { described_class.new(config, temp_dir, resources_dir) }

    it 'reads the whole language of the directory' do
      expect(manager.send(:get_translated_value, 'k', { 'en' => 'E', 'zh-Hant' => 'H' }, 'values-b+zh+Hant')).to eq('H')
    end
  end
end
