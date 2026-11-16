# frozen_string_literal: true

require_relative '../../lib/core/language_code'

# Ticket jui-strings-language-code-with-script-subtag-lost: a tag has more than
# one word, and the paths used to keep only one of them.
RSpec.describe JsonUIShared::LanguageCode do
  describe '.of_lproj' do
    {
      'app/zh-Hant.lproj/Localizable.strings' => 'zh-Hant',
      'zh-Hans.lproj/Localizable.strings' => 'zh-Hans',
      'zh-TW.lproj/Localizable.strings' => 'zh-TW',
      'zh_TW.lproj/Localizable.strings' => 'zh-TW',
      'pt-BR.lproj/Localizable.strings' => 'pt-BR',
      'a.b/ja.lproj/Localizable.stringsdict' => 'ja',
      'en.lproj/Localizable.strings' => 'en',
      'Base.lproj/Localizable.strings' => 'en',
      'Localizable.strings' => 'en'
    }.each do |path, code|
      it("reads #{path} as #{code}") { expect(described_class.of_lproj(path)).to eq(code) }
    end
  end

  describe '.of_values_dir' do
    {
      'values' => 'en', 'values-ja' => 'ja', 'values-ko' => 'ko',
      'values-b+zh+Hant' => 'zh-Hant', 'values-b+zh+Hans' => 'zh-Hans',
      'values-b+zh+Hant+HK' => 'zh-Hant-HK', 'values-b+pt+BR' => 'pt-BR',
      'values-zh-rTW' => 'zh-TW', 'values-zh-rCN' => 'zh-CN', 'values-pt-rBR' => 'pt-BR',
      'values-zh-rTW-night' => 'zh-TW', 'values-ja-land' => 'ja', 'values-mcc310-ja' => 'ja',
      'values-land' => 'en', 'values-night' => 'en', 'values-sw600dp' => 'en', 'values-v21' => 'en',
      'values-tv' => 'en', 'values-car' => 'en'
    }.each do |dir, code|
      it("reads #{dir} as #{code}") { expect(described_class.of_values_dir(dir)).to eq(code) }
    end
  end

  describe '.candidates' do
    {
      'zh-Hant' => %w[zh-Hant zh-TW zh-HK zh-MO],
      'zh-TW' => %w[zh-TW zh-Hant zh-HK zh-MO],
      'zh-HK' => %w[zh-HK zh-Hant zh-TW zh-MO],
      'zh-Hant-HK' => %w[zh-Hant-HK zh-HK zh-Hant zh-TW zh-MO],
      'zh-Hans' => %w[zh-Hans zh-CN zh-SG zh],
      'zh-CN' => %w[zh-CN zh-Hans zh-SG zh],
      'zh' => %w[zh zh-Hans zh-CN zh-SG],
      'pt-BR' => %w[pt-BR pt],
      'en-GB' => %w[en-GB en],
      'ja' => %w[ja]
    }.each do |code, spellings|
      it("gives #{code} #{spellings.join(', ')}") { expect(described_class.candidates(code)).to eq(spellings) }
    end

    it 'never gives a Traditional output the zh text: both systems treat zh as Simplified' do
      %w[zh-Hant zh-TW zh-HK zh-MO zh-Hant-TW zh-Hant-HK].each do |code|
        expect(described_class.candidates(code)).not_to include('zh')
      end
    end

    it 'never crosses the scripts' do
      expect(described_class.candidates('zh-Hant') & described_class::SIMPLIFIED).to be_empty
      expect(described_class.candidates('zh-Hans') & described_class::TRADITIONAL).to be_empty
    end
  end

  describe '.resolve' do
    it "takes the language's own text" do
      expect(described_class.resolve({ 'en' => 'E', 'zh-Hant' => 'H' }, 'zh-Hant')).to eq('H')
    end

    it 'takes the other spelling of the same script' do
      expect(described_class.resolve({ 'en' => 'E', 'zh-Hant' => 'H' }, 'zh-TW')).to eq('H')
    end

    it 'falls to the default language, then to the first there is' do
      expect(described_class.resolve({ 'en' => 'E', 'zh' => 'Z' }, 'zh-Hant')).to eq('E')
      expect(described_class.resolve({ 'ja' => 'J' }, 'zh-Hant')).to eq('J')
    end

    it 'keeps an empty text: it is that language having said nothing, not a missing one' do
      expect(described_class.resolve({ 'en' => 'E', 'ja' => '' }, 'ja')).to eq('')
      expect(described_class.spelling_in({ 'en' => 'E', 'ja' => '' }, 'ja')).to eq('ja')
    end

    it 'takes the given default language' do
      expect(described_class.resolve({ 'en' => 'E', 'ja' => 'J' }, 'ko', 'ja')).to eq('J')
    end
  end

  describe '.fallback_warning' do
    it 'is silent when nothing fell back' do
      expect(described_class.fallback_warning('ja.lproj', 'ja', [])).to be_nil
    end

    it 'names the output, the language and the keys' do
      line = described_class.fallback_warning('zh-Hant.lproj', 'zh-Hant', %w[a b])
      expect(line).to include('zh-Hant.lproj', '2 key(s)', 'zh-Hant', 'a, b')
    end

    it 'names the first keys and counts the rest' do
      line = described_class.fallback_warning('x', 'ja', %w[a b c d e f g])
      expect(line).to include('a, b, c, d, e and 2 more')
      expect(line).not_to include('f,')
    end
  end
end
