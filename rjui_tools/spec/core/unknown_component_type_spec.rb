# frozen_string_literal: true

require_relative '../spec_helper'
require 'tmpdir'
require 'core/attribute_validator'
require 'react/react_generator'

# The one sentence for a type a tool cannot draw (JsonUIShared::
# AttributeValidatorCore.unknown_component_type_message; kjui's
# spec/core/unknown_component_type_spec.rb holds the rule): rjui says it, and
# draws nothing for the node — the sentence in a JSX comment, at the root and
# as a child (4f's ruling, jsonui-cli 1.9.0; it drew a plain View, and named
# a child nowhere). A type the validator knows that no converter draws is
# another sentence, drawn as a View. The rjui profile knows the types its
# registry draws — the converter_mappings.rb the generator reads, the
# project's first (Dir.pwd/rjui_tools/...), as the generator finds it.
RSpec.describe 'rjui: unknown component type' do
  def generator
    generator = RjuiTools::React::ReactGenerator.allocate
    generator.instance_variable_set(:@config, { 'use_tailwind' => true })
    generator.instance_variable_set(:@extension_converters, {})
    generator
  end

  it 'says the sentence and draws nothing, at the root and as a child, and the JSX type-checks' do
    said = []
    allow(RjuiTools::Core::Logger).to receive(:warn) { |message| said << message }
    sentence = "Unknown component type 'switch' — did you mean 'Switch'? Type names are case-sensitive."
    kid = { 'type' => 'Label', 'id' => 'kid', 'text' => 'innerText' }
    root = generator.send(:convert_component, { 'type' => 'switch', 'id' => 'x', 'child' => [kid] })
    child = generator.send(:convert_component, { 'type' => 'View', 'id' => 'p', 'child' => [{ 'type' => 'switch', 'id' => 'x', 'child' => [kid] }] })
    [root, child].each do |out|
      expect(out).to include("{/* #{sentence} */}")
      expect(out).not_to include('innerText') # not its children
      expect(out).not_to include('<div id="x"')
    end
    expect(said.count(sentence)).to eq(2)
    # the root as the component file holds it (a fragment around a bare {…}), the child in its parent
    expect("export const Root = (): JSX.Element => (\n<>\n#{root}\n</>\n);\n" \
           "export const Child = (): JSX.Element => (\n#{child}\n);\n").to compile_as_typescript
  end

  # A type the validator knows — here by the project's extension definitions
  # — that no converter draws: its own sentence, and a View with its
  # children in it, at the root and as a child, as sjui and kjui draw it.
  it 'names a type the project declares but no converter draws in its own sentence, and draws it as a View' do
    said = []
    allow(RjuiTools::Core::Logger).to receive(:warn) { |message| said << message }
    Dir.mktmpdir do |dir|
      defs = File.join(dir, 'rjui_tools', 'lib', 'react', 'converters', 'extensions', 'attribute_definitions')
      FileUtils.mkdir_p(defs)
      File.write(File.join(defs, 'ProbeDeclared.json'), JSON.generate('ProbeDeclared' => { 'text' => { 'type' => 'string' } }))
      Dir.chdir(dir) do
        kid = { 'type' => 'Label', 'id' => 'kid', 'text' => 'innerText' }
        root = generator.send(:convert_component, { 'type' => 'ProbeDeclared', 'id' => 'd', 'child' => [kid] })
        child = generator.send(:convert_component, { 'type' => 'View', 'id' => 'p', 'child' => [{ 'type' => 'ProbeDeclared', 'id' => 'd', 'child' => [kid] }] })
        [root, child].each do |out|
          expect(out).to include('<div id="d"')
          expect(out).to include('innerText')
        end
      end
    end
    expect(said).to eq(["'ProbeDeclared' is declared but has no web converter — drawn as a View"] * 2)
  end

  # A project's registered converter with no attribute definition file (a
  # downstream app's HeaderMenu): no type sentence, its attributes as before;
  # its other-case spelling offered.
  it 'knows a project registered type, from the registry the generator reads' do
    Dir.mktmpdir do |project|
      dir = File.join(project, 'rjui_tools', 'lib', 'react', 'converters', 'extensions')
      FileUtils.mkdir_p(dir)
      File.write(File.join(dir, 'converter_mappings.rb'), <<~RUBY)
        module RjuiTools
          module React
            module Converters
              module Extensions
                remove_const(:CONVERTER_MAPPINGS) if const_defined?(:CONVERTER_MAPPINGS, false)
                CONVERTER_MAPPINGS = { 'HeaderMenu' => 'HeaderMenuConverter' }.freeze
              end
            end
          end
        end
      RUBY
      Dir.chdir(project) do
        validator = RjuiTools::Core::AttributeValidator.new(:react)
        validator.validate({ 'type' => 'HeaderMenu', 'menuItems' => [] })
        expect(validator.warnings.grep(/Unknown component type/)).to eq([])
        expect(validator.warnings.grep(/Unknown attribute 'menuItems' for component type 'HeaderMenu'/).size).to eq(1)
        validator.validate({ 'type' => 'headerMenu' })
        expect(validator.warnings.grep(/Unknown component type/).map { |w| w[/Unknown.*\z/] })
          .to eq(["Unknown component type 'headerMenu' — did you mean 'HeaderMenu'? Type names are case-sensitive."])
      end
    end
  ensure
    # the repo's own registry again
    load File.expand_path('../../lib/react/converters/extensions/converter_mappings.rb', __dir__)
  end
end
