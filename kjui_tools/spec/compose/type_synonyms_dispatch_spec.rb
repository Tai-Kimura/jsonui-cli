# frozen_string_literal: true

require 'json'
require 'set'
require 'compose/compose_builder'
require 'core/type_synonyms'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# An app's component registered under a synonym's name (HStack), standing in
# for one in the project's components/extensions directory.
class ProbeHStackKjuiComponent
  def self.generate(json_data, _depth, _imports, _parent_type)
    "ProbeHStack(#{json_data['type']}, orientation: #{json_data['orientation'].inspect})"
  end
end

# kjui's codegen dispatch: an app's component registered under the spelling
# as written first; else the node as it is drawn — a type synonym's target
# with the attributes it means (shared/core/type_synonyms.json), then a
# declared alias section's canonical one. The dispatch's cases are canonical
# types only. (That every spelling builds what its canonical spelling builds
# is spec/cli/spelling_invariance_spec.rb's.)
RSpec.describe 'kjui codegen: the type-synonym dispatch' do
  def builder
    b = KjuiTools::Compose::ComposeBuilder.allocate
    b.instance_variable_set(:@required_imports, Set.new)
    b
  end

  def emit(node)
    builder.send(:generate_component, JSON.parse(JSON.generate(node)), 1)
  end

  after { JsonUIShared::TypeSynonyms.app_types = [] }

  describe 'an app component registered under a synonym name' do
    before do
      allow(KjuiTools::Compose::ComposeBuilder).to receive(:custom_component_class) { |t| t == 'HStack' ? ProbeHStackKjuiComponent : nil }
      allow(KjuiTools::Compose::ComposeBuilder).to receive(:custom_component_types).and_return(['HStack'])
      JsonUIShared::TypeSynonyms.app_types = ['HStack']
    end

    it 'is given the node as written, before any synonym is resolved — at the root and as a child' do
      expect(emit({ 'type' => 'HStack', 'child' => [] })).to include('ProbeHStack(HStack, orientation: nil)')
      nested = emit({ 'type' => 'View', 'child' => [{ 'type' => 'HStack', 'child' => [] }] })
      expect(nested).to include('ProbeHStack(HStack, orientation: nil)')
    end

    it 'leaves the other spellings of the same type to the table (control)' do
      expect(emit({ 'type' => 'Row', 'child' => [] })).not_to include('ProbeHStack')
    end
  end

  # TableView, RecyclerView, List and ListView: kjui has no case of its own
  # for them — each is drawn as Collection because the table says so.
  describe 'the list spellings come from the table' do
    source = File.read(File.expand_path('../../lib/compose/compose_builder.rb', __dir__))
    cases = source.scan(/^\s*when ((?:'[^']+'(?:,\s*)?)+)$/).flat_map { |(line)| line.scan(/'([^']+)'/).flatten }

    %w[TableView RecyclerView List ListView].each do |spelling|
      it "draws #{spelling} as the table's Collection, with no case of its own" do
        expect(cases).to include('Collection') # the scan reads the cases (control)
        expect(cases).not_to include(spelling)
        expect(JsonUIShared::TypeSynonyms.entries[spelling]).to include('canonical' => 'Collection')
        node = { 'id' => 'n', 'items' => [] }
        expect(emit(node.merge('type' => spelling))).to eq(emit(node.merge('type' => 'Collection')))
      end
    end

    it 'follows the table: without its entry, a spelling is an undeclared type' do
      table = JsonUIShared::TypeSynonyms.entries.reject { |spelling, _| spelling == 'TableView' }
      allow(JsonUIShared::TypeSynonyms).to receive(:entries).and_return(table)
      expect(emit({ 'type' => 'TableView', 'id' => 'n', 'items' => [] })).to include('// TODO: Implement component type: TableView')
    end
  end

  # What the table draws is Kotlin that compiles: the list spellings as a
  # Collection, an HStack as a View (a Row), an EditText as a TextField.
  it 'compiles what the table and the alias sections draw' do
    nodes = {
      'TableView' => { 'items' => [] }, 'RecyclerView' => { 'items' => [] }, 'List' => { 'items' => [] },
      'ListView' => { 'items' => [] }, 'HStack' => { 'child' => [{ 'type' => 'Label', 'text' => 'a' }] },
      'EditText' => { 'text' => '@{t}' }
    }
    functions = nodes.each_with_index.map do |(type, extra), i|
      "// #{type}\nfun emitted#{i}(data: Data, viewModel: ViewModel) {\n#{emit({ 'type' => type, 'id' => 'n' }.merge(extra))}\n}"
    end
    emitted = functions.join("\n\n")
    expect(emitted).to include('Row(') # the HStack drew a Row (control)
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(emitted)}
      class Data(val t: String = "", val nIsFocused: Boolean = false)
      class ViewModel { fun updateData(values: Map<String, Any?>) {} }
      #{emitted}
    KOTLIN
  end

  it 'draws neither declared nor synonym types as undeclared: Spacer (it drew a fixed 8dp Spacer until 1.9.0)' do
    expect(emit({ 'type' => 'Spacer', 'height' => 8 })).to include('// TODO: Implement component type: Spacer')
  end
end
