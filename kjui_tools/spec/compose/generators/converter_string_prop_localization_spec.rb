# frozen_string_literal: true

require 'json'
require 'set'
require 'tmpdir'
require 'fileutils'
require 'core/logger'
require 'core/config_manager'
require 'core/project_finder'
require 'core/string_manager_core'
require 'compose/helpers/resource_resolver'
require 'compose/generators/converter_generator'
require_relative '../../support/kotlin_compiler'

# kjui-custom-component-string-literal-prop-is-read-as-a-string-key (ruling
# 2026-10-03): a custom component's literal String prop is looked up as a
# strings.json key only when its NAME is display text —
# StringManagerCore.localized_prop?, the list jui lint-strings checks
# (STRING_PROPERTIES, which gains accessibilityLabel) — on iOS and Android
# alike. Any other String prop is the literal. Through jsonui-cli 1.9.5 the
# kjui scaffold looked every String literal up: `variant: "bar"` became
# stringResource(...) when the screen declared `bar`, and warned "Bare key
# … foreign section" when another section did; sjui wrote every literal.
RSpec.describe 'kjui g converter: a literal String prop and the strings.json' do
  STRING_PROP_EXTENSIONS = File.expand_path('../../../lib/compose/components/extensions', __dir__)
  STRING_PROP_RESOLVER = KjuiTools::Compose::Helpers::ResourceResolver

  let(:dir) { Dir.mktmpdir('kjui_string_props') }

  before do
    %i[info debug success error].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    allow(KjuiTools::Core::Logger).to receive(:warn) { |msg| warned << msg }
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config)
      .and_return('source_directory' => 'src/main', 'layouts_directory' => 'assets/Layouts', 'package_name' => 'probe')
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(dir)
    resources = File.join(dir, 'src/main/assets/Layouts/Resources')
    FileUtils.mkdir_p(resources)
    File.write(File.join(resources, 'strings.json'), JSON.generate(
      'screen' => { 'greeting' => 'Hello', 'bar' => 'Bar (screen)' },
      'other' => { 'dumbbell' => 'Dumbbell (other)' }
    ))
    STRING_PROP_RESOLVER.current_namespaces = ['screen']
  end

  after do
    STRING_PROP_RESOLVER.current_namespaces = []
    FileUtils.rm_rf(dir)
  end

  let(:warned) { [] }

  def converter_for(name, attributes)
    code = KjuiTools::Compose::Generators::ConverterGenerator.new(name, { attributes: attributes }).send(:converter_template)
    code = code.gsub(/require_relative '([^']+)'/) { "require '#{File.expand_path(Regexp.last_match(1), STRING_PROP_EXTENSIONS)}'" }
    eval(code, TOPLEVEL_BINDING, "#{name}_component.rb") # rubocop:disable Security/Eval
    KjuiTools::Compose::Components::Extensions.const_get("#{name}Component")
  end

  def emit(node)
    Dir.chdir(dir) do
      converter_for('StringProbe', { 'label' => 'String', 'accessibilityLabel' => 'String', 'variant' => 'String' })
        .generate({ 'type' => 'StringProbe' }.merge(node), 0, Set.new)
    end
  end

  it 'reads the vocabulary from the one list' do
    expect(JsonUIShared::StringManagerCore::STRING_PROPERTIES).to include('label', 'accessibilityLabel')
    expect(JsonUIShared::StringManagerCore.localized_prop?('label')).to be(true)
    expect(JsonUIShared::StringManagerCore.localized_prop?('variant')).to be(false)
  end

  it 'resolves a display-text prop the screen declares, and writes any other String prop as its literal' do
    code = emit('label' => 'greeting', 'accessibilityLabel' => 'greeting', 'variant' => 'bar')
    expect(code).to include('label = stringResource(R.string.screen_greeting)')
    expect(code).to include('accessibilityLabel = stringResource(R.string.screen_greeting)')
    # Through 1.9.5: variant = stringResource(R.string.screen_bar).
    expect(code).to include('variant = "bar"')
  end

  it 'emits a call that compiles against the composable and the resources it names' do
    code = emit('label' => 'greeting', 'accessibilityLabel' => 'greeting', 'variant' => 'bar')
    call = code[/StringProbe\(.*?\n\s*\)/m] or raise "no StringProbe call in:\n#{code}"
    expect(<<~KT).to compile_as_kotlin
      annotation class Composable
      object R { object string { const val screen_greeting = 1 } }
      @Composable fun stringResource(id: Int): String = ""
      open class Modifier { companion object : Modifier() }
      @Composable fun StringProbe(label: String = "", accessibilityLabel: String = "", variant: String = "", modifier: Modifier = Modifier) {}
      @Composable fun host() {
      #{call}
      }
    KT
  end

  it 'says nothing for an enum-like value another section happens to declare (the reporter case)' do
    code = emit('variant' => 'dumbbell')
    expect(code).to include('variant = "dumbbell"')
    # Through 1.9.5: "Bare key \"dumbbell\" is declared only in foreign strings.json section(s) other …"
    expect(warned.grep(/Bare key/)).to eq([])
  end

  it 'still names a display-text prop whose bare key only another section declares (control)' do
    emit('label' => 'dumbbell')
    expect(warned.grep(/Bare key "dumbbell"/).size).to eq(1)
  end
end
