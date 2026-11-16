# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'fileutils'
require 'core/logger'
require 'core/config_manager'
require 'core/project_finder'
require 'core/string_manager_core'
require 'swiftui/helpers/string_manager_helper'
require 'swiftui/generators/converter_generator'
require_relative '../../support/swift_compiler'

# kjui-custom-component-string-literal-prop-is-read-as-a-string-key (ruling
# 2026-10-03), the iOS face: a custom component's literal String prop whose
# NAME is display text (StringManagerCore.localized_prop? — the list jui
# lint-strings checks, with accessibilityLabel) is the project's localized
# string when strings.json declares the key; any other String prop is the
# literal. Through jsonui-cli 1.9.5 the sjui scaffold wrote every literal, so
# a `label: "peaty"` the Android face showed translated was the raw key here.
RSpec.describe 'sjui g converter: a literal String prop and the strings.json' do
  STRING_PROP_SJUI_EXTENSIONS = File.expand_path('../../../lib/swiftui/views/extensions', __dir__)

  let(:dir) { Dir.mktmpdir('sjui_string_props') }

  before(:context) { @kept = ProcessStateGuard.keep(SjuiTools::SwiftUI::Helpers::StringManagerHelper) }
  after(:context) { ProcessStateGuard.put_back(@kept) }

  before do
    %i[info debug success error warn].each { |m| allow(SjuiTools::Core::Logger).to receive(m) }
    allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return('layouts_directory' => 'Layouts')
    allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(dir)
    resources = File.join(dir, 'Layouts', 'Resources')
    FileUtils.mkdir_p(resources)
    File.write(File.join(resources, 'strings.json'), JSON.generate(
      'screen' => { 'greeting' => 'Hello', 'bar' => 'Bar (screen)' }
    ))
    SjuiTools::SwiftUI::Helpers::StringManagerHelper.current_namespaces = ['screen']
  end

  after do
    SjuiTools::SwiftUI::Helpers::StringManagerHelper.current_namespaces = []
    FileUtils.rm_rf(dir)
  end

  def converter_for(name, attributes)
    code = SjuiTools::SwiftUI::Generators::ConverterGenerator.new(name, attributes: attributes).send(:converter_template)
    code = code.gsub(/require_relative '([^']+)'/) { "require '#{File.expand_path(Regexp.last_match(1), STRING_PROP_SJUI_EXTENSIONS)}'" }
    eval(code, TOPLEVEL_BINDING, "#{name}_converter.rb") # rubocop:disable Security/Eval
    SjuiTools::SwiftUI::Views::Extensions.const_get("#{name}Converter")
  end

  def emit(node)
    converter_for('StringProbe', { 'label' => 'String', 'accessibilityLabel' => 'String', 'variant' => 'String' })
      .new({ 'type' => 'StringProbe' }.merge(node), 0, nil, nil, nil, nil).convert
  end

  it 'resolves a display-text prop the screen declares, and writes any other String prop as its literal' do
    code = emit('label' => 'greeting', 'accessibilityLabel' => 'greeting', 'variant' => 'bar')
    # Through 1.9.5: label: "greeting", accessibilityLabel: "greeting".
    expect(code).to include('label: StringManager.Screen.greeting()')
    expect(code).to include('accessibilityLabel: StringManager.Screen.greeting()')
    expect(code).to include('variant: "bar"')
  end

  it 'resolves the text a key holds, as a Label does (the consumer\'s "PEATY" shape)' do
    code = emit('label' => 'Hello', 'variant' => 'Hello')
    expect(code).to include('label: StringManager.Screen.greeting()')
    expect(code).to include('variant: "Hello"')
  end

  it 'emits a call that typechecks against the component and the StringManager it names' do
    code = emit('label' => 'greeting', 'accessibilityLabel' => 'Hello', 'variant' => 'bar')
    expect(<<~SWIFT).to compile_as_swift
      struct StringProbe { init(label: String = "", accessibilityLabel: String = "", variant: String = "") {} }
      enum StringManager { enum Screen { static func greeting() -> String { "Hello" } } }
      func host() {
          _ = #{code}
      }
    SWIFT
  end

  it 'writes the literal when the project declares no such key (control)' do
    code = emit('label' => 'Not a key')
    expect(code).to include('label: "Not a key"')
  end
end
