# frozen_string_literal: true

require_relative '../spec_helper'
require 'tmpdir'
require 'core/attribute_validator'
require 'react/react_generator'

# The one sentence for a type a tool cannot draw (JsonUIShared::
# AttributeValidatorCore.unknown_component_type_message; kjui's
# spec/core/unknown_component_type_spec.rb holds the rule): rjui says it where
# it draws a plain View for the node. The rjui profile knows the types its
# registry draws — the converter_mappings.rb the generator reads, the
# project's first (Dir.pwd/rjui_tools/...), as the generator finds it.
RSpec.describe 'rjui: unknown component type' do
  it 'says the sentence where it draws a plain View' do
    said = []
    allow(RjuiTools::Core::Logger).to receive(:warn) { |message| said << message }
    generator = RjuiTools::React::ReactGenerator.allocate
    generator.instance_variable_set(:@config, { 'use_tailwind' => true })
    generator.instance_variable_set(:@extension_converters, {})
    generator.send(:convert_component, { 'type' => 'switch', 'id' => 'x' })
    expect(said).to include("Unknown component type 'switch' — did you mean 'Switch'? Type names are case-sensitive.")
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
