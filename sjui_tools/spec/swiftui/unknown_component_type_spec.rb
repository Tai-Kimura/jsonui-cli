# frozen_string_literal: true

require 'tmpdir'
require 'swiftui/converter_factory'
require_relative '../support/emitted_swift'

# The one sentence for a type a tool cannot draw (JsonUIShared::
# AttributeValidatorCore.unknown_component_type_message; kjui's
# spec/core/unknown_component_type_spec.rb holds the rule): sjui draws its red
# placeholder with it and says it in the build. The placeholder said
# "Unsupported component: <type>".
RSpec.describe 'sjui: unknown component type' do
  include EmittedSwift
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  it 'draws and says the sentence' do
    said = []
    allow(SjuiTools::Core::Logger).to receive(:warn) { |message| said << message }
    code = SjuiTools::SwiftUI::ConverterFactory.new.create_converter({ 'type' => 'switch', 'id' => 'x' }).convert
    sentence = "Unknown component type 'switch' — did you mean 'Switch'? Type names are case-sensitive."
    expect(code).to include("Text(#{sentence.to_json})")
    expect(code).not_to include('Unsupported component')
    expect(said).to include(sentence)
    # the sentence is written into the Swift as a string literal a compiler reads
    expect(compilable_view(code)).to compile_as_swift
  end

  # The profile reads the registry the SwiftUI dispatch reads
  # (views/extensions/converter_mappings.rb, CONVERTER_MAPPINGS).
  it 'is told the registered types by the sjui profile, from the dispatch registry' do
    source = File.read(File.expand_path('../../lib/core/attribute_validator.rb', __dir__))
    factory = File.read(File.expand_path('../../lib/swiftui/converter_factory.rb', __dir__))
    expect(source).to include("'../swiftui/views/extensions/converter_mappings.rb'")
    expect(factory).to include("File.join(__dir__, 'views', 'extensions', 'converter_mappings.rb')")

    Dir.mktmpdir do |dir|
      registry = File.join(dir, 'converter_mappings.rb')
      File.write(registry, "# a registry\n")
      stub_const('SjuiTools::SwiftUI::Views::Extensions::CONVERTER_MAPPINGS', { 'HeaderMenu' => 'HeaderMenuConverter' })
      validator = SjuiTools::Core::AttributeValidator.new(:swiftui)
      allow(validator).to receive(:component_registry_path).and_return(registry)
      expect(validator.send(:registered_component_types)).to eq(['HeaderMenu'])
      validator.validate({ 'type' => 'HeaderMenu' })
      expect(validator.warnings.grep(/Unknown component type/)).to eq([])
      validator.validate({ 'type' => 'headerMenu' })
      expect(validator.warnings.grep(/Unknown component type/).map { |w| w[/Unknown.*\z/] })
        .to eq(["Unknown component type 'headerMenu' — did you mean 'HeaderMenu'? Type names are case-sensitive."])
    end
  end
end
