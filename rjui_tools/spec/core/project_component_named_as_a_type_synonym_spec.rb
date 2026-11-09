# frozen_string_literal: true

require 'core/attribute_validator'
require 'core/layout_validator'
require 'core/binding_validator'
require 'tmpdir'
require 'fileutils'
require 'json'

# A project component whose name is a type-synonym spelling (ProgressBar,
# HStack, Table, …) or an alias section (EditText, Check, …) is the
# project's: its converter draws it as written, so what reads its attributes
# reads its own definition — never the synonym's or the alias's section.
# Through 2.5.20 the validator looked the synonym up first: an extension
# ProgressBar's own prop was "Unknown attribute … for component type
# 'ProgressBar'" (checked against Progress), the layout validator judged an
# extension's bindings by the canonical's declarations (an error, 31 of the
# 54 spellings), and an extension HStack was told it meant horizontal —
# while the codegen drew the extension (ticket
# jui-extension-component-named-as-type-synonym-validated-against-canonical).
# Each spelling is compared with a control: the same definition under a
# name that is nothing else.
RSpec.describe 'a project component named as a type synonym or an alias section' do
  synonyms = JsonUIShared::TypeSynonyms
  extension_dir = 'rjui_tools/lib/react/converters/extensions/attribute_definitions'
  mode = :react
  validator_class = RjuiTools::Core::AttributeValidator
  binding_class = RjuiTools::Core::BindingValidator
  control = 'ZzProjectControl'
  spellings = synonyms.entries.keys + JsonUIShared::ComponentAliases.table.keys
  definitions = JSON.parse(File.read(File.expand_path('../../lib/core/attribute_definitions.json', __dir__)))

  after { synonyms.app_types = [] }

  # every attribute the spelling's section declares, bound — what a project
  # component may well name its own props
  section_attrs = lambda do |spelling|
    section = synonyms.section(spelling)
    (definitions[section] || {}).select { |k, v| v.is_a?(Hash) && !%w[child children].include?(k) }.keys
  end

  node_for = lambda do |type, attrs|
    node = { 'type' => type, 'id' => 'x', 'width' => 10, 'height' => 10, 'extProp' => '@{a}', 'orientation' => 'vertical' }
    attrs.each { |k| node[k] = '@{a}' }
    node
  end

  def in_project(types_to_attrs)
    Dir.mktmpdir do |dir|
      FileUtils.mkdir_p(File.join(dir, self.class.metadata[:extension_dir]))
      types_to_attrs.each do |type, attrs|
        body = (attrs + %w[extProp orientation]).to_h { |k| [k, { 'type' => 'string' }] }
        File.write(File.join(dir, self.class.metadata[:extension_dir], "#{type}.json"), JSON.generate(type => body))
      end
      Dir.chdir(dir) { yield }
    end
  end

  metadata[:extension_dir] = extension_dir

  [true, false].each do |registered|
    context(registered ? 'registered by the build (app_types)' : 'only declared by its extension definition') do
      it 'is validated against its own definition, as the control is' do
        attrs = spellings.to_h { |s| [s, section_attrs.call(s)] }
        in_project(attrs.merge(attrs.to_h { |s, a| ["#{control}#{s}", a] })) do
          synonyms.app_types = registered ? attrs.keys.flat_map { |s| [s, "#{control}#{s}"] } : []
          validator = validator_class.new(mode)
          said = lambda do |type, written|
            validator.validate(node_for.call(type, attrs[written])).map { |w| w.gsub(type, 'TYPE') }.sort
          end
          differ = spellings.reject { |s| said.call(s, s) == said.call("#{control}#{s}", s) }
          expect(differ).to eq([])
          expect(said.call('ProgressBar', 'ProgressBar').grep(/Unknown attribute/)).to eq([])
        end
      end

      it 'has its bindings judged by the layout validator as the control has' do
        attrs = spellings.to_h { |s| [s, section_attrs.call(s)] }
        in_project(attrs.merge(attrs.to_h { |s, a| ["#{control}#{s}", a] })) do
          synonyms.app_types = registered ? attrs.keys.flat_map { |s| [s, "#{control}#{s}"] } : []
          extensions = validator_class.extension_definitions(mode)
          judged = lambda do |type, written|
            layout = { 'type' => 'View', 'width' => 1, 'height' => 1, 'child' => [node_for.call(type, attrs[written])] }
            JsonUIShared::LayoutValidator.validate_layout(layout, source_path: 'p.json', extension_definitions: extensions)
                                         .map { |w| w[:message].gsub(type, 'TYPE') }.sort
          end
          differ = spellings.reject { |s| judged.call(s, s) == judged.call("#{control}#{s}", s) }
          expect(differ).to eq([])
        end
      end
    end
  end

  it 'has its bindings resolved to its own section by the binding validator when registered' do
    synonyms.app_types = spellings
    validator = binding_class.new
    expect(spellings.reject { |s| validator.send(:resolve_component_alias, s) == s }).to eq([])
  end

  # The control: a spelling no project registers is its synonym's, as before.
  it 'leaves a synonym spelling no project registers validated as its canonical section' do
    in_project({}) do
      validator = validator_class.new(mode)
      said = validator.validate({ 'type' => 'ProgressBar', 'id' => 'p', 'progress' => 0.5, 'extProp' => 1 })
      expect(said.grep(/Unknown attribute 'extProp' for component type 'ProgressBar'/).size).to eq(1)
      expect(said.grep(/'progress'/)).to eq([])
      expect(validator.validate({ 'type' => 'HStack', 'orientation' => 'vertical' }).grep(/HStack means orientation horizontal/).size).to eq(1)
      expect(synonyms.section('ProgressBar')).to eq('Progress')
      expect(synonyms.section('EditText')).to eq('TextField')
      expect(binding_class.new.send(:resolve_component_alias, 'Table')).to eq('Collection')
    end
  end
end
