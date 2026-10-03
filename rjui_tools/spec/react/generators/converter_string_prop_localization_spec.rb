# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'fileutils'
require 'core/logger'
require 'core/config_manager'
require 'react/generators/converter_generator'
require_relative '../../support/typescript_compiler'

# rjui-custom-component-string-literal-prop-is-read-as-a-string-key (ruling
# 2026-10-03), the web face: a custom component's literal String prop whose
# NAME is display text (StringManagerCore.localized_prop? — the list jui
# lint-strings checks, with accessibilityLabel) is the project's localized
# string when strings.json declares the key; any other String prop is the
# literal. The iOS and Android scaffolds ask the same question from 1.9.6
# (29992638); through 1.9.7 the rjui scaffold looked every String literal up,
# so an enum-like `variant: "bar"` resolved to a string the layout's section
# declares, and warned "Bare key … foreign section" when another section did.
RSpec.describe 'rjui g converter: a literal String prop and the strings.json' do
  EXT_STRING_PROPS = File.expand_path('../../../lib/react/converters/extensions', __dir__)

  let(:dir) { Dir.mktmpdir('rjui_string_props') }
  let(:warnings) { [] }

  before do
    %i[info debug success error].each { |m| allow(RjuiTools::Core::Logger).to receive(m) }
    allow(RjuiTools::Core::Logger).to receive(:warn) { |message| warnings << message }
    resources = File.join(dir, 'Layouts', 'Resources')
    FileUtils.mkdir_p(resources)
    File.write(File.join(resources, 'strings.json'), JSON.generate(
      'screen' => { 'greeting' => 'Hello', 'bar' => 'Bar (screen)' },
      'other' => { 'compact' => 'Compact (other)' }
    ))
    allow(RjuiTools::Core::ConfigManager).to receive(:load_config)
      .and_return('layouts_directory' => File.join(dir, 'Layouts'))
  end

  after { FileUtils.rm_rf(dir) }

  # Built once per name: the generated converters are classes.
  def converter
    @converter ||= begin
      code = RjuiTools::React::Generators::ConverterGenerator
             .new('StringPropProbe', { attributes: { 'label' => 'String', 'accessibilityLabel' => 'String',
                                                      'variant' => 'String' }, is_container: false }, {}, 'spec')
             .send(:converter_template)
      code = code.gsub(/require_relative '([^']+)'/) { "require '#{File.expand_path(Regexp.last_match(1), EXT_STRING_PROPS)}'" }
      eval(code, TOPLEVEL_BINDING, 'string_prop_probe_converter.rb') # rubocop:disable Security/Eval
      RjuiTools::React::Converters::Extensions.const_get('StringPropProbeConverter')
    end
  end

  def emit(node)
    converter.new({ 'type' => 'StringPropProbe' }.merge(node), { '_current_namespaces' => ['screen'] }).convert
  end

  it 'resolves a display-text prop the screen declares, and writes any other String prop as its literal' do
    jsx = emit('label' => 'greeting', 'accessibilityLabel' => 'greeting', 'variant' => 'bar')
    expect(jsx).to include('label={StringManager.', 'accessibilityLabel={StringManager.')
    # Through 1.9.7: variant={StringManager.currentLanguage.screenBar}.
    expect(jsx).to include('variant={`bar`}')
  end

  it 'says nothing for a non-display prop whose value another section declares' do
    jsx = emit('variant' => 'compact')
    expect(jsx).to include('variant={`compact`}')
    # Through 1.9.7: "Bare key \"compact\" is declared only in foreign strings.json section(s) other".
    expect(warnings.grep(/Bare key/)).to eq([])
  end

  it 'still warns for a display-text prop whose key only another section declares (control)' do
    emit('label' => 'compact')
    expect(warnings.grep(/Bare key "compact"/).size).to eq(1)
  end

  it 'writes the literal when the project declares no such key (control)' do
    expect(emit('label' => 'Not a key')).to include('label={`Not a key`}')
  end

  it 'emits JSX that type-checks against the component and the StringManager it names', :aggregate_failures do
    jsx = emit('label' => 'greeting', 'accessibilityLabel' => 'Hello there', 'variant' => 'bar')
    ambient = <<~TS
      declare const StringManager: { currentLanguage: { [key: string]: string } };
      declare function StringPropProbe(props: { className?: string; label?: string; accessibilityLabel?: string; variant?: string }): any;
    TS
    expect(TypeScriptCompiler.component(jsx)).to compile_as_typescript.with_ambient(ambient)
  end
end
