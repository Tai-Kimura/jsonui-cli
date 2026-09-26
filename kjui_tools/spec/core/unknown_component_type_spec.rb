# frozen_string_literal: true

require 'core/attribute_validator'
require 'compose/compose_builder'
require 'tmpdir'
require_relative '../support/kotlin_compiler'
require 'json'

# A node whose type the tool cannot draw is named by its type, in one sentence
# (4f's ruling, jsonui-cli 1.9.0): the shared validator (4 byte-identical
# copies), the kjui / sjui / rjui codegen where they draw nothing, and
# KotlinJsonUI Dynamic (its own constant, held to this text by its arm). Type
# names are matched as written. The types a tool draws are the SSoT's
# sections, the project's extension definitions, the type-synonym spellings
# and the extension components its own registry draws — a registered type
# with no attribute definition file is known, and its attributes are checked
# against the common ones as they were (each other attribute named "Unknown
# attribute").
RSpec.describe 'unknown component type' do
  let(:core) { JsonUIShared::AttributeValidatorCore }

  def warnings(node, registered: [])
    validator = KjuiTools::Core::AttributeValidator.new(:compose)
    allow(validator).to receive(:registered_component_types).and_return(registered)
    validator.validate(node)
    validator.warnings
  end

  def type_warnings(node, **opts)
    warnings(node, **opts).grep(/Unknown component type/).map { |w| w[/Unknown component type.*\z/] }
  end

  it 'is the one sentence the ruling fixed' do
    expect(core.unknown_component_type_message('switch', %w[Label Switch]))
      .to eq("Unknown component type 'switch' — did you mean 'Switch'? Type names are case-sensitive.")
    expect(core.unknown_component_type_message('Nope', %w[Label Switch])).to eq("Unknown component type 'Nope'")
  end

  # The shared table KotlinJsonUI's Dynamic constant is held to (a
  # byte-identical copy in its test resources, compared by its CI).
  it 'answers every case of shared/core/unknown_component_type_vectors.json' do
    vectors = File.expand_path('../../../shared/core/unknown_component_type_vectors.json', __dir__)
    skip 'shared vectors not present in this layout' unless File.exist?(vectors)

    cases = JSON.parse(File.read(vectors))['cases']
    expect(cases.size).to be >= 5
    got = cases.map { |c| [c['name'], core.unknown_component_type_message(c['written'], c['known'])] }
    expect(got).to eq(cases.map { |c| [c['name'], c['expect']] })
  end

  it 'names a type in another case with the declared one, and a type no path draws alone' do
    expect(type_warnings({ 'type' => 'switch' })).to eq(["Unknown component type 'switch' — did you mean 'Switch'? Type names are case-sensitive."])
    expect(type_warnings({ 'type' => 'SELECTBOX' })).to eq(["Unknown component type 'SELECTBOX' — did you mean 'SelectBox'? Type names are case-sensitive."])
    expect(type_warnings({ 'type' => 'Nope' })).to eq(["Unknown component type 'Nope'"])
  end

  it 'says nothing of a declared section, an alias section or a type-synonym' do
    %w[Switch Toggle Check EditText Text Picker HStack].each do |type|
      expect(type_warnings({ 'type' => type })).to eq([]), type
    end
  end

  # A registered type (a converter, no definition file): no type sentence, and
  # its attributes named as before this check existed.
  it 'says nothing of a registered type, and names its attributes as before' do
    node = { 'type' => 'HeaderMenu', 'menuItems' => [] }
    registered = warnings(node, registered: ['HeaderMenu'])
    expect(registered.grep(/Unknown component type/)).to eq([])
    expect(registered.grep(/Unknown attribute 'menuItems' for component type 'HeaderMenu'/).size).to eq(1)
    # the same node unregistered: the attribute sentence, and the type named
    unregistered = warnings(node)
    expect(unregistered - registered).to eq(["[HeaderMenu] Unknown component type 'HeaderMenu'"])
  end

  it 'offers a registered type for its other-case spelling' do
    expect(type_warnings({ 'type' => 'headerMenu' }, registered: ['HeaderMenu']))
      .to eq(["Unknown component type 'headerMenu' — did you mean 'HeaderMenu'? Type names are case-sensitive."])
  end

  # The kjui profile reads the registry the compose dispatch reads
  # (components/extensions/component_mappings.rb, COMPONENT_MAPPINGS).
  it 'is told the registered types by the kjui profile, from the compose registry' do
    source = File.read(File.expand_path('../../lib/core/attribute_validator.rb', __dir__))
    builder = File.read(File.expand_path('../../lib/compose/compose_builder.rb', __dir__))
    expect(source).to include("'../compose/components/extensions/component_mappings.rb'")
    expect(builder).to include("'components', 'extensions', 'component_mappings.rb'")

    Dir.mktmpdir do |dir|
      registry = File.join(dir, 'component_mappings.rb')
      File.write(registry, "# a registry\n")
      stub_const('KjuiTools::Compose::Components::Extensions::COMPONENT_MAPPINGS', { 'HeaderMenu' => Object })
      validator = KjuiTools::Core::AttributeValidator.new(:compose)
      allow(validator).to receive(:component_registry_path).and_return(registry)
      expect(validator.send(:registered_component_types)).to eq(['HeaderMenu'])
      validator.validate({ 'type' => 'HeaderMenu' })
      expect(validator.warnings.grep(/Unknown component type/)).to eq([])
    end
  end

  # The kjui codegen, where it draws nothing: the build says the sentence, and
  # so does the emitted comment. It was `// TODO: Implement component type: …`.
  it 'is said by the kjui codegen where it draws nothing' do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@responsive_counter, 0)
    builder.instance_variable_set(:@responsive_functions, [])
    said = []
    allow(KjuiTools::Core::Logger).to receive(:warn) { |message| said << message }
    code = builder.send(:generate_component, { 'type' => 'switch' }, 0).to_s
    sentence = "Unknown component type 'switch' — did you mean 'Switch'? Type names are case-sensitive."
    expect(code).to include("// #{sentence}")
    expect(code).not_to include('TODO')
    expect(said).to include(sentence)
    # a comment where the node would be: the enclosing function still compiles
    expect("fun screen() {\n#{code}\n}\n").to compile_as_kotlin
  end
end
