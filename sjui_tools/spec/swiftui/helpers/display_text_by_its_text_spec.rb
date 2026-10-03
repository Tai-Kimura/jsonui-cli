# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'fileutils'
require 'core/logger'
require 'core/config_manager'
require 'core/project_finder'
require 'swiftui/helpers/string_manager_helper'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

# Display text written as the text a strings.json key holds resolves to that
# key — a plain string or any language of a per-language value, the layout's
# own sections first — through JsonUIShared::StringManagerCore
# .resolve_string_reference, the one lookup sjui, kjui and rjui make (ticket
# rjui-display-text-is-not-looked-up-by-the-text-a-key-holds, ruling
# 2026-10-03). Through jsonui-cli 1.9.7 the shared lookup matched a plain
# string only, so a per-language entry's text was drawn as written here while
# rjui localized it. The same three arms sit in kjui's and rjui's specs.
RSpec.describe 'sjui: display text by the text a key holds' do
  include EmittedSwift

  let(:dir) { Dir.mktmpdir('sjui_display_text') }

  before(:context) { @kept = ProcessStateGuard.keep(SjuiTools::SwiftUI::Helpers::StringManagerHelper) }
  after(:context) { ProcessStateGuard.put_back(@kept) }

  before do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
    %i[info debug success error warn].each { |m| allow(SjuiTools::Core::Logger).to receive(m) }
    allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return('layouts_directory' => 'Layouts')
    allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(dir)
    resources = File.join(dir, 'Layouts', 'Resources')
    FileUtils.mkdir_p(resources)
    # `other` comes first: file order alone would pick its key.
    File.write(File.join(resources, 'strings.json'), JSON.generate(
      'other' => { 'shared_word' => { 'en' => 'Shared', 'ja' => '共有' } },
      'screen' => { 'tone_bold_short' => { 'en' => 'BOLD', 'ja' => '太字' },
                    'greeting' => 'Hello', 'search_hint' => { 'en' => 'Search', 'ja' => '検索' }, 'bold' => 'BOLD',
                    'shared_word' => { 'en' => 'Shared', 'ja' => '共有' } }
    ))
    SjuiTools::SwiftUI::Helpers::StringManagerHelper.current_namespaces = ['screen']
  end

  after do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
    SjuiTools::SwiftUI::Helpers::StringManagerHelper.current_namespaces = []
    FileUtils.rm_rf(dir)
  end

  def emit(component)
    factory = SjuiTools::SwiftUI::ConverterFactory.new
    factory.create_converter(component, 0, nil, factory).convert.to_s
  end

  def label(text)
    emit('type' => 'Label', 'id' => 'l', 'text' => text)
  end

  def hint(text)
    emit('type' => 'TextField', 'id' => 'f', 'text' => '@{q}', 'hint' => text)
  end

  it 'resolves any language of a per-language value' do
    expect(label('検索')).to include('StringManager.Screen.searchHint()')
    expect(label('Search')).to include('StringManager.Screen.searchHint()')
  end

  it "prefers the layout's own section over one earlier in the file" do
    expect(label('Shared')).to include('StringManager.Screen.sharedWord()')
    expect(label('Shared')).not_to include('StringManager.Other')
  end

  it "resolves a TextField hint written as a per-language value's text (a web app's hints measured in that shape)" do
    expect(hint('Search')).to include('StringManager.Screen.searchHint()')
  end

  it 'control: a plain-string value and a key resolve as before; text no entry holds is written as is' do
    expect(label('Hello')).to include('StringManager.Screen.greeting()')
    expect(label('greeting')).to include('StringManager.Screen.greeting()')
    expect(label('Nope')).to include('"Nope"')
  end

  # 28 texts measured on two apps: a plain string that is the
  # text wins over a per-language entry earlier in the section, so a text
  # that resolved before 1.9.8 resolves to the same key.
  it 'keeps a text a plain string holds on that key, before a per-language entry that holds it too' do
    expect(label('BOLD')).to include('StringManager.Screen.bold()')
    expect(label('BOLD')).not_to include('StringManager.Screen.toneBoldShort')
  end

  # Labels only: a TextField's emit needs the screen's state ($data, its focus
  # state), which a fragment does not carry; its hint writes the same call.
  it 'emits Labels that type-check against the StringManager they name', :swift_compile do
    view = [label('検索'), label('Shared'), label('BOLD')].join("\n")
    stubs = <<~SWIFT
      enum StringManager {
          enum Screen {
              static func searchHint() -> String { "" }
              static func sharedWord() -> String { "" }
              static func bold() -> String { "" }
          }
      }
    SWIFT
    expect(compilable_view("VStack {\n#{view}\n}", stubs: stubs)).to compile_as_swift
  end
end
