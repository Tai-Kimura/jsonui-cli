# frozen_string_literal: true

require 'tmpdir'
require 'swiftui/converter_factory'
require_relative '../support/emitted_swift'

# The one sentence for a type a tool cannot draw (JsonUIShared::
# AttributeValidatorCore.unknown_component_type_message; kjui's
# spec/core/unknown_component_type_spec.rb holds the rule): sjui says it in
# the build and writes it in a comment where the node would be, drawing
# nothing — not the node, not its children (4f's ruling, jsonui-cli 1.9.0: a
# red Text holding it put a build's words on a release screen). A type the
# validator knows that no converter draws is another sentence, drawn as a View.
RSpec.describe 'sjui: unknown component type' do
  include EmittedSwift
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  it 'says the sentence and draws nothing, at the root and as a child, and the Swift compiles' do
    said = []
    allow(SjuiTools::Core::Logger).to receive(:warn) { |message| said << message }
    sentence = "Unknown component type 'switch' — did you mean 'Switch'? Type names are case-sensitive."
    kid = { 'type' => 'Label', 'id' => 'kid', 'text' => 'innerText' }
    root = SjuiTools::SwiftUI::ConverterFactory.new.create_converter({ 'type' => 'switch', 'id' => 'x', 'child' => [kid] }).convert
    expect(root).to include("// #{sentence}")
    expect(root).not_to include('innerText') # not its children
    expect(root).not_to include('Text(')
    expect(root).not_to include('Unsupported component')
    factory = SjuiTools::SwiftUI::ConverterFactory.new
    child = factory.create_converter({ 'type' => 'View', 'id' => 'p', 'child' => [{ 'type' => 'switch', 'id' => 'x', 'child' => [kid] }] },
                                     0, nil, factory).convert
    expect(child).to include("// #{sentence}")
    expect(child).not_to include('innerText')
    expect(said.count(sentence)).to eq(2)
    expect(compilable_view(root)).to compile_as_swift
    expect(compilable_view(child)).to compile_as_swift
  end

  # A type the validator knows — here by the project's extension definitions
  # — that no converter draws: its own sentence, and a View with its
  # children in it, as rjui and kjui draw it.
  it 'names a type the project declares but no converter draws in its own sentence, and draws it as a View' do
    said = []
    allow(SjuiTools::Core::Logger).to receive(:warn) { |message| said << message }
    Dir.mktmpdir do |dir|
      defs = File.join(dir, 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'attribute_definitions')
      FileUtils.mkdir_p(defs)
      File.write(File.join(defs, 'ProbeDeclared.json'), JSON.generate('ProbeDeclared' => { 'text' => { 'type' => 'string' } }))
      Dir.chdir(dir) do
        factory = SjuiTools::SwiftUI::ConverterFactory.new
        node = { 'type' => 'ProbeDeclared', 'id' => 'd', 'child' => [{ 'type' => 'Label', 'id' => 'kid', 'text' => 'innerText' }] }
        converter = factory.create_converter(node, 0, nil, factory)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::ViewConverter)
        expect(converter.convert).to include('innerText')
      end
    end
    expect(said).to eq(["'ProbeDeclared' is declared but has no SwiftUI converter — drawn as a View"])
    expect(said.grep(/Unknown component type/)).to eq([]) # the control: the other sentence is not said
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
