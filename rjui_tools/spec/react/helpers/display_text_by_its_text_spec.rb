# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'fileutils'
require 'core/logger'
require 'core/config_manager'
require 'react/converters/label_converter'
require 'react/converters/button_converter'
require 'react/converters/text_field_converter'
require_relative '../../support/typescript_compiler'

# Display text written as the text a strings.json key holds resolves to that
# key — a plain string or any language of a per-language value, the layout's
# own sections first — through JsonUIShared::StringManagerCore
# .resolve_string_reference, the one lookup sjui, kjui and rjui make (ticket
# rjui-display-text-is-not-looked-up-by-the-text-a-key-holds, ruling
# 2026-10-03). Through jsonui-cli 1.9.7 rjui's Label and Button looked the
# key up only, and its TextField's hint went through a lookup of its own
# (file order, a per-language value's first language). The same three arms
# sit in sjui's and kjui's specs.
RSpec.describe 'rjui: display text by the text a key holds' do
  let(:dir) { Dir.mktmpdir('rjui_display_text') }
  let(:options) { { '_current_namespaces' => ['screen'] } }

  before do
    %i[info debug success error warn].each { |m| allow(RjuiTools::Core::Logger).to receive(m) }
    resources = File.join(dir, 'Layouts', 'Resources')
    FileUtils.mkdir_p(resources)
    # `other` comes first: file order alone would pick its key.
    File.write(File.join(resources, 'strings.json'), JSON.generate(
      'other' => { 'shared_word' => { 'en' => 'Shared', 'ja' => '共有' }, 'elsewhere' => { 'en' => 'Elsewhere', 'ja' => 'よそ' } },
      'screen' => { 'tone_bold_short' => { 'en' => 'BOLD', 'ja' => '太字' }, 'blank' => { 'en' => '', 'ja' => '' },
                    'greeting' => 'Hello', 'search_hint' => { 'en' => 'Search', 'ja' => '検索' }, 'bold' => 'BOLD',
                    'shared_word' => { 'en' => 'Shared', 'ja' => '共有' } }
    ))
    allow(RjuiTools::Core::ConfigManager).to receive(:load_config)
      .and_return('layouts_directory' => File.join(dir, 'Layouts'))
  end

  after { FileUtils.rm_rf(dir) }

  def label(text)
    RjuiTools::React::Converters::LabelConverter.new({ 'type' => 'Label', 'id' => 'l', 'text' => text }, options).convert
  end

  def button(text)
    RjuiTools::React::Converters::ButtonConverter.new({ 'type' => 'Button', 'id' => 'b', 'text' => text }, options).convert
  end

  def hint(text)
    RjuiTools::React::Converters::TextFieldConverter
      .new({ 'type' => 'TextField', 'id' => 'f', 'text' => '@{q}', 'hint' => text }, options).convert
  end

  it 'resolves any language of a per-language value, on a Label and a Button' do
    expect(label('検索')).to include('StringManager.currentLanguage.screenSearchHint')
    expect(label('Search')).to include('StringManager.currentLanguage.screenSearchHint')
    expect(button('Search')).to include('StringManager.currentLanguage.screenSearchHint')
  end

  it "prefers the layout's own section over one earlier in the file" do
    expect(label('Shared')).to include('StringManager.currentLanguage.screenSharedWord')
    expect(label('Shared')).not_to include('otherSharedWord')
  end

  it "keeps a TextField hint written as a per-language value's text resolved (a web app's hints measured in that shape)" do
    expect(hint('Search')).to include('StringManager.currentLanguage.screenSearchHint')
  end

  it 'resolves a plain-string value (until 1.9.8 a Label drew it as written) and a key; text no entry holds is written as is' do
    expect(label('Hello')).to include('StringManager.currentLanguage.screenGreeting')
    expect(label('greeting')).to include('StringManager.currentLanguage.screenGreeting')
    expect(label('Nope')).to include('>Nope<')
  end

  # 28 texts measured on two apps: a plain string that is the
  # text wins over a per-language entry earlier in the section, so a text
  # that resolved before 1.9.8 resolves to the same key.
  it 'keeps a text a plain string holds on that key, before a per-language entry that holds it too' do
    expect(label('BOLD')).to include('StringManager.currentLanguage.screenBold')
    expect(label('BOLD')).not_to include('screenToneBoldShort')
  end

  # Labels and a Button: a TextField's JSX needs the screen's refs and state,
  # which a fragment does not carry; its placeholder writes the same reference.
  it 'emits Labels and a Button that type-check against the StringManager they name', :aggregate_failures do
    ambient = <<~TS
      declare const StringManager: { currentLanguage: { [key: string]: string } };
    TS
    [label('検索'), label('Shared'), label('BOLD'), button('Search')].each do |jsx|
      expect(TypeScriptCompiler.component(jsx)).to compile_as_typescript.with_ambient(ambient)
    end
  end

  # The per-language pass looks in the layout's own sections only, and not
  # for an empty text: a text no plain string holds stays as written rather
  # than landing in another screen's section (a warning 1.9.7 did not print),
  # and `""` does not match an entry with an empty language.
  it "does not look a per-language value up in a section the layout does not own" do
    expect(label('Elsewhere')).not_to include('StringManager.')
  end

  it 'does not look an empty text up, though an entry has an empty language' do
    expect(label('')).not_to include('StringManager.')
  end
end
