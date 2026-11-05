# frozen_string_literal: true

require 'tmpdir'
require 'fileutils'
require 'core/resources/string_manager'

# Ticket jui-strings-language-code-with-script-subtag-lost.
RSpec.describe SjuiTools::Core::Resources::StringManager, 'language codes with a script or a region' do
  let(:manager) { described_class.allocate }
  let(:data) do
    plural = ->(v) { { 'plural' => { 'other' => "{count} #{v}" } } }
    {
      'home' => {
        'hello' => { 'en' => 'EN', 'zh-Hant' => 'HANT', 'zh-Hans' => 'HANS', 'zh' => 'ZH', 'pt-BR' => 'PTBR', 'ko' => 'KO' },
        'items' => %w[en zh-Hant zh-Hans zh pt-BR ko].to_h { |l| [l, plural.call(l.upcase)] }
      }
    }
  end

  def build(lang)
    Dir.mktmpdir do |dir|
      path = File.join(dir, "#{lang}.lproj", 'Localizable.strings')
      FileUtils.mkdir_p(File.dirname(path))
      File.write(path, '')
      manager.send(:update_strings_file, path, data)
      manager.send(:update_stringsdict_file, path, data)
      dict = path.sub('.strings', '.stringsdict')
      [File.read(path), File.exist?(dict) ? File.read(dict) : '']
    end
  end

  {
    'zh-Hant' => 'HANT', 'zh-Hans' => 'HANS', 'zh-TW' => 'HANT', 'zh-CN' => 'HANS',
    'zh_TW' => 'HANT', 'zh' => 'ZH', 'pt-BR' => 'PTBR', 'ko' => 'KO', 'en' => 'EN', 'Base' => 'EN'
  }.each do |lang, text|
    it "gives #{lang}.lproj the text and the plural forms of #{text}" do
      strings, dict = build(lang)
      expect(strings).to include(%("home_hello" = "#{text}";))
      expected = text == 'HANT' ? 'ZH-HANT' : text == 'HANS' ? 'ZH-HANS' : text == 'PTBR' ? 'PT-BR' : text
      expect(dict).to include("%ld #{expected}")
    end
  end

  it 'says so when a language has no text of its own, once per file' do
    entries = { 'home' => { 'a' => { 'en' => 'A' }, 'b' => { 'en' => 'B', 'ja' => 'び' } } }
    Dir.mktmpdir do |dir|
      path = File.join(dir, 'ja.lproj', 'Localizable.strings')
      FileUtils.mkdir_p(File.dirname(path))
      File.write(path, '')
      expect(SjuiTools::Core::Logger).to receive(:warn).once.with(/ja\.lproj: 1 key\(s\) have no ja text.*home_a/)
      allow(SjuiTools::Core::Logger).to receive(:info)
      manager.send(:update_strings_file, path, entries)
    end
  end

  it 'counts a plural entry with no forms for the language in that one line' do
    entries = { 'home' => { 'n' => { 'en' => { 'plural' => { 'other' => '{count}' } } } } }
    Dir.mktmpdir do |dir|
      path = File.join(dir, 'ja.lproj', 'Localizable.strings')
      FileUtils.mkdir_p(File.dirname(path))
      File.write(path, '')
      expect(SjuiTools::Core::Logger).to receive(:warn).once.with(/1 key\(s\).*home_n/)
      allow(SjuiTools::Core::Logger).to receive(:info)
      manager.send(:update_strings_file, path, entries)
    end
  end

  it 'says nothing when every text is there, or has no language at all' do
    entries = { 'home' => { 'a' => { 'en' => 'A', 'ja' => 'あ' }, 'b' => 'plain' } }
    Dir.mktmpdir do |dir|
      path = File.join(dir, 'ja.lproj', 'Localizable.strings')
      FileUtils.mkdir_p(File.dirname(path))
      File.write(path, '')
      expect(SjuiTools::Core::Logger).not_to receive(:warn)
      allow(SjuiTools::Core::Logger).to receive(:info)
      manager.send(:update_strings_file, path, entries)
    end
  end
end
