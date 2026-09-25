# frozen_string_literal: true

require 'tmpdir'
require 'json'
require 'fileutils'
require 'core/attribute_validator'
require 'core/layout_validator'
require 'core/converter_generator_core'

# Whether an extension component takes children, from the definition file
# `g converter` writes to the build's refusal of a leaf given children.
# Ticket sjui-leaf-custom-component-cannot-reject-children; the build path is
# spec/cli/leaf_children_build_spec.rb.
RSpec.describe 'a leaf declared in its extension definition' do
  # Methods, not constants: a constant in a describe block is top-level, and
  # another spec file naming it differently would redefine it.
  def defs_path
    %w[rjui_tools lib react converters extensions attribute_definitions]
  end

  def mode
    :react
  end

  def validator
    RjuiTools::Core::AttributeValidator.new(mode)
  end

  # The definition writer is the shared core's (generate_attribute_definition_file);
  # this is the smallest profile it needs. The tool's own generator writes the
  # same file through the same method — the build path spec runs that one
  # (`g converter` end to end).
  def definition_writer(dir, said = [])
    Class.new(JsonUIShared::ConverterGeneratorCore) do
      define_method(:initialize) do |name, options|
        @name = name
        @options = options
        @logger = Object.new.tap do |l|
          l.define_singleton_method(:info) { |m| said << [:info, m] }
          l.define_singleton_method(:warn) { |m| said << [:warn, m] }
        end
      end
      define_method(:attr_defs_dir) { dir }
      define_method(:command_string) { "g converter #{@name}" }
      define_method(:json_marker) { |source:, generator:| { 'source' => source, 'generator' => generator } }
    end
  end

  around do |example|
    Dir.mktmpdir('leaf_defs') do |dir|
      @defs_dir = File.join(dir, *defs_path)
      FileUtils.mkdir_p(@defs_dir)
      Dir.chdir(dir) { example.run }
    end
  end

  # Writes the definition the way `g converter` does, into this project.
  def scaffold(name, mode, attributes = { 'title' => 'String' })
    definition_writer(@defs_dir).new(name, { is_container: mode, attributes: attributes })
                                .send(:generate_attribute_definition_file)
    JSON.parse(File.read(File.join(@defs_dir, "#{name}.json")))[name]
  end

  def refusals(layout)
    JsonUIShared::LayoutValidator.validate_layout(
      layout, source_path: 'probe.json',
      extension_definitions: RjuiTools::Core::AttributeValidator.extension_definitions(mode)
    ).select { |w| w[:level] == :error }
  end

  def kid(id = 'kid')
    { 'type' => 'Label', 'id' => id, 'text' => id }
  end

  describe 'the definition file' do
    it 'declares a leaf for --no-container, with attributes or without' do
      expect(scaffold('Leaf', false)).to include('_children' => 'none').and include('title')
      expect(scaffold('Leaf', false)).not_to include('child', 'children')
      expect(scaffold('BareLeaf', false, {})).to eq('_children' => 'none')
    end

    it 'declares child / children for --container and for the default, with attributes or without' do
      [true, nil].each do |mode|
        expect(scaffold('Box1', mode).keys).to include('child', 'children', 'title')
        expect(scaffold('Box2', mode, {}).keys).to contain_exactly('child', 'children')
      end
    end
  end

  # `g converter` with neither --container nor --no-container — what
  # `jui g converter --all` runs, with or without --skip-existing, for a
  # component spec without slots — keeps what the definition declares; only a
  # flag changes it. Until 1.8.121 such a run wrote the default back over a
  # leaf, and the build stopped refusing its children while the leaf's
  # scaffold went on dropping them, with no warning (measured 2026-09-26).
  describe 'a run with neither --container nor --no-container' do
    # What `g converter` runs: keep the declaration first, then write. Returns
    # the definition written and the mode the rest of the run (the converter,
    # the scaffolds) was given.
    def rerun(name, mode, said = [])
      writer = definition_writer(@defs_dir, said).new(name, { is_container: mode, attributes: { 'title' => 'String' } })
      writer.send(:keep_children_declaration)
      writer.send(:generate_attribute_definition_file)
      [JSON.parse(File.read(File.join(@defs_dir, "#{name}.json")))[name], writer.instance_variable_get(:@options)[:is_container]]
    end

    it 'keeps a leaf a leaf, says so, and the build still refuses its children' do
      scaffold('Leaf', false)
      said = []
      definition, mode = rerun('Leaf', nil, said)
      expect(definition).to include('_children' => 'none').and include('title')
      expect(mode).to be(false)
      expect(said).to include([:info, include('Leaf is declared a leaf in attribute_definitions/Leaf.json — kept')])
      expect(refusals('type' => 'Leaf', 'id' => 'map', 'child' => [kid]).size).to eq(1)
    end

    it 'changes it when asked: --container makes the leaf take children (the control)' do
      scaffold('Leaf', false)
      definition, mode = rerun('Leaf', true)
      expect(definition.keys).to include('child', 'children')
      expect(definition).not_to include('_children')
      expect(mode).to be(true)
      expect(refusals('type' => 'Leaf', 'id' => 'map', 'child' => [kid])).to be_empty
    end

    it 'keeps a container a container, and writes the default where nothing was declared' do
      scaffold('Box', true)
      definition, mode = rerun('Box', nil)
      expect(definition.keys).to include('child', 'children')
      expect(mode).to be_nil
      definition, mode = rerun('New', nil)
      expect(definition.keys).to include('child', 'children')
      expect(mode).to be_nil
    end

    it 'names a definition it cannot read, and writes the default' do
      File.write(File.join(@defs_dir, 'Torn.json'), '{"Torn": {"_children": "none",')
      said = []
      definition, mode = rerun('Torn', nil, said)
      expect(said).to include([:warn, include('attribute_definitions/Torn.json is not JSON').and(include('--no-container'))])
      expect(definition.keys).to include('child', 'children')
      expect(mode).to be_nil
    end
  end

  describe 'the build refusal (LayoutValidator)' do
    before do
      scaffold('Leaf', false)
      scaffold('Box', nil)
    end

    it 'refuses a leaf given children, naming the component, the node and each child' do
      errors = refusals('type' => 'View', 'child' => [
                          { 'type' => 'Leaf', 'id' => 'map', 'child' => [kid('pin'), { 'include' => 'badge' }] }
                        ])
      expect(errors.size).to eq(1)
      expect(errors.first[:message]).to include("'Leaf' (id=map) takes no children")
        .and include('child[0] (id=pin), child[1] would be dropped').and include('--container')
    end

    it 'names an id-less leaf by where it sits' do
      errors = refusals('type' => 'View', 'child' => [kid('a'), { 'type' => 'Leaf', 'child' => [kid] }])
      expect(errors.map { |e| e[:message] }).to contain_exactly(include("'Leaf' (child[1]) takes no children"))
    end

    it 'reads `children` and the single-node shorthand too' do
      expect(refusals('type' => 'Leaf', 'id' => 'a', 'children' => [kid]).size).to eq(1)
      expect(refusals('type' => 'Leaf', 'id' => 'b', 'child' => kid).first[:message]).to include('child (id=kid)')
    end

    it 'says nothing for a leaf with no children, an empty list, or only data definitions' do
      expect(refusals('type' => 'Leaf', 'id' => 'a')).to be_empty
      expect(refusals('type' => 'Leaf', 'id' => 'a', 'child' => [])).to be_empty
      expect(refusals('type' => 'Leaf', 'id' => 'a', 'child' => [{ 'data' => [{ 'name' => 'x' }] }])).to be_empty
    end

    it 'says nothing for a container given children (the control)' do
      expect(refusals('type' => 'Box', 'id' => 'a', 'child' => [kid])).to be_empty
    end

    it 'does not refuse without the project definitions — the check is the declaration, not the name' do
      layout = { 'type' => 'Leaf', 'id' => 'a', 'child' => [kid] }
      expect(JsonUIShared::LayoutValidator.validate_layout(layout, source_path: 'p.json')).to be_empty
    end
  end

  describe 'the attribute validator' do
    it "does not add \"Unknown attribute 'child'\" to the refusal of a declared leaf" do
      scaffold('Leaf', false)
      warnings = validator.validate({ 'type' => 'Leaf', 'id' => 'a', 'title' => 'x', 'child' => [kid] })
      expect(warnings.grep(/Unknown attribute 'child'/)).to be_empty
    end

    it "keeps \"Unknown attribute 'child'\" where nothing is declared — a definition from before 1.8.121" do
      File.write(File.join(@defs_dir, 'Legacy.json'), JSON.generate('Legacy' => { 'title' => { 'type' => 'string' } }))
      layout = { 'type' => 'Legacy', 'id' => 'a', 'title' => 'x', 'child' => [kid] }
      expect(validator.validate(layout).grep(/Unknown attribute 'child' for component type 'Legacy'/).size).to eq(1)
      expect(refusals(layout)).to be_empty
    end

    it 'counts required attributes the same with the declaration present — it is not an attribute' do
      declared = { 'title' => { 'type' => 'string', 'required' => true }, '_children' => 'none' }
      File.write(File.join(@defs_dir, 'WithDecl.json'), JSON.generate('WithDecl' => declared))
      File.write(File.join(@defs_dir, 'NoDecl.json'), JSON.generate('NoDecl' => declared.reject { |k, _| k == '_children' }))
      required = lambda do |type|
        validator.validate({ 'type' => type, 'id' => 'a' }).grep(/Required attribute/).map { |w| w.sub(type, 'T') }
      end
      expect(required.call('WithDecl')).to eq(required.call('NoDecl'))
      expect(required.call('WithDecl')).to include(include("Required attribute 'title' is missing"))
    end

    # The string is ignored even by a validator that reads every entry as a
    # Hash (String#[] answers nil), so it cannot tell the entries apart. A
    # `false` can: validators before 1.8.121 raised on it for every node.
    # This one counts declarations only.
    it 'counts required attributes over declarations only — a `false` entry neither raises nor counts' do
      title = { 'title' => { 'type' => 'string', 'required' => true } }
      File.write(File.join(@defs_dir, 'WithFalse.json'), JSON.generate('WithFalse' => title.merge('_container' => false)))
      File.write(File.join(@defs_dir, 'Plain.json'), JSON.generate('Plain' => title))
      required = lambda do |type|
        validator.validate({ 'type' => type, 'id' => 'a' }).grep(/Required attribute/).map { |w| w.sub(type, 'T') }
      end
      expect(required.call('WithFalse')).to eq(required.call('Plain'))
      expect(required.call('WithFalse')).to include(include("Required attribute 'title' is missing"))
    end

    it 'reads the project definitions from where the build reads them' do
      scaffold('Leaf', false)
      expect(RjuiTools::Core::AttributeValidator.extension_definitions(mode)['Leaf']).to include('_children' => 'none')
    end
  end
end
