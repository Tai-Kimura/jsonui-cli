# frozen_string_literal: true

require 'json'
require 'set'
require 'tmpdir'
require 'fileutils'
require 'core/logger'
require 'core/config_manager'
require 'core/project_finder'
require 'compose/helpers/resource_resolver'
require 'compose/components/text_component'
require 'compose/components/textfield_component'
require_relative '../../support/kotlin_compiler'

# Display text written as the text a strings.json key holds resolves to that
# key — a plain string or any language of a per-language value, the layout's
# own sections first — through JsonUIShared::StringManagerCore
# .resolve_string_reference, the one lookup sjui, kjui and rjui make (ticket
# rjui-display-text-is-not-looked-up-by-the-text-a-key-holds, ruling
# 2026-10-03). Through jsonui-cli 1.9.7 the shared lookup matched a plain
# string only, so a per-language entry's text was drawn as written here while
# rjui localized it. The same three arms sit in sjui's and rjui's specs.
RSpec.describe 'kjui: display text by the text a key holds' do
  let(:dir) { Dir.mktmpdir('kjui_display_text') }

  before do
    %i[info debug success error warn].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config)
      .and_return('source_directory' => 'src/main', 'layouts_directory' => 'assets/Layouts', 'package_name' => 'probe')
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(dir)
    resources = File.join(dir, 'src/main/assets/Layouts/Resources')
    FileUtils.mkdir_p(resources)
    # `other` comes first: file order alone would pick its key.
    File.write(File.join(resources, 'strings.json'), JSON.generate(
      'other' => { 'shared_word' => { 'en' => 'Shared', 'ja' => '共有' }, 'elsewhere' => { 'en' => 'Elsewhere', 'ja' => 'よそ' } },
      'screen' => { 'tone_bold_short' => { 'en' => 'BOLD', 'ja' => '太字' }, 'blank' => { 'en' => '', 'ja' => '' },
                    'greeting' => 'Hello', 'search_hint' => { 'en' => 'Search', 'ja' => '検索' }, 'bold' => 'BOLD',
                    'shared_word' => { 'en' => 'Shared', 'ja' => '共有' } }
    ))
    KjuiTools::Compose::Helpers::ResourceResolver.current_namespaces = ['screen']
  end

  after do
    KjuiTools::Compose::Helpers::ResourceResolver.current_namespaces = []
    FileUtils.rm_rf(dir)
  end

  def label(text)
    Dir.chdir(dir) { KjuiTools::Compose::Components::TextComponent.generate({ 'type' => 'Label', 'id' => 'l', 'text' => text }, 0, Set.new) }
  end

  def hint(text)
    Dir.chdir(dir) do
      KjuiTools::Compose::Components::TextFieldComponent.generate(
        { 'type' => 'TextField', 'id' => 'f', 'text' => '@{q}', 'hint' => text }, 0, Set.new
      )
    end
  end

  it 'resolves any language of a per-language value' do
    expect(label('検索')).to include('stringResource(R.string.screen_search_hint)')
    expect(label('Search')).to include('stringResource(R.string.screen_search_hint)')
  end

  it "prefers the layout's own section over one earlier in the file" do
    expect(label('Shared')).to include('stringResource(R.string.screen_shared_word)')
    expect(label('Shared')).not_to include('other_shared_word')
  end

  it "resolves a TextField hint written as a per-language value's text (a web app's hints measured in that shape)" do
    expect(hint('Search')).to include('stringResource(R.string.screen_search_hint)')
  end

  it 'control: a plain-string value and a key resolve as before; text no entry holds is written as is' do
    expect(label('Hello')).to include('stringResource(R.string.screen_greeting)')
    expect(label('greeting')).to include('stringResource(R.string.screen_greeting)')
    expect(label('Nope')).to include('"Nope"')
  end

  # 28 texts measured on two apps: a plain string that is the
  # text wins over a per-language entry earlier in the section, so a text
  # that resolved before 1.9.8 resolves to the same key.
  it 'keeps a text a plain string holds on that key, before a per-language entry that holds it too' do
    expect(label('BOLD')).to include('stringResource(R.string.screen_bold)')
    expect(label('BOLD')).not_to include('screen_tone_bold_short')
  end

  # The references, not the whole emit: kotlinc here has no Compose, and what
  # this lookup decides is which R.string the Text and the hint name. The
  # stub declares only the keys the examples expect, so a reference to any
  # other name does not compile.
  it 'emits string references that compile against the R.string the strings.json gives' do
    emitted = [label('検索'), label('Shared'), label('BOLD'), hint('Search')].join("\n")
    calls = emitted.scan(/stringResource\(R\.string\.\w+\)/).uniq
    expect(calls.size).to eq(3)
    expect(<<~KOTLIN).to compile_as_kotlin
      object R { object string { const val screen_search_hint = 1; const val screen_shared_word = 2; const val screen_bold = 3 } }
      fun stringResource(id: Int): String = id.toString()
      fun probe(): List<String> = listOf(#{calls.join(', ')})
    KOTLIN
  end

  # The per-language pass looks in the layout's own sections only, and not
  # for an empty text: a text no plain string holds stays as written rather
  # than landing in another screen's section (a warning 1.9.7 did not print),
  # and `""` does not match an entry with an empty language.
  it "does not look a per-language value up in a section the layout does not own" do
    expect(label('Elsewhere')).not_to include('stringResource(')
  end

  it 'does not look an empty text up, though an entry has an empty language' do
    expect(label('')).not_to include('stringResource(')
  end
end
