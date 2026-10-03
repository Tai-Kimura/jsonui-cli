# frozen_string_literal: true

require 'json'
require 'set'
require 'compose/compose_builder'
require 'core/type_synonyms'

# App components standing in for ones in a project's components/extensions
# directory.
module ParentScopeProbes
  # The `kjui g converter` scaffold's kind: its own size, padding and margins,
  # no weight and no alignment in the parent (it builds its modifiers with
  # build_size(json, nil) and never calls build_weight / build_alignment).
  class Bare
    def self.generate(_json, _depth, _imports, _parent)
      'ProbeBar(modifier = Modifier.requiredHeight(12.dp).padding(start = 8.dp))'
    end
  end

  # Weights and aligns itself.
  class Owns
    def self.generate(_json, _depth, _imports, _parent)
      'ProbeOwns(modifier = Modifier.weight(1f).align(Alignment.Top))'
    end
  end
end

# kjui-custom-component-converter-drops-weight: an app's component given
# `weight` in a Row / Column got no `.weight(...)` — the scaffold never
# applied it — so it was measured at its own minimum (a Canvas bar ~0 wide)
# where iOS (sjui's scaffold calls apply_modifiers) filled the slot. Its
# alignment in the parent (alignTop / centerVertical in a Row, alignLeft /
# centerHorizontal in a Column, the Box ones) was dropped the same way: the
# census of the SSoT's common attributes on a built-in View and on a
# scaffolded component (2026-10-03) found exactly these two families missing.
#
# Both are the parent's scope, so kjui applies them around the component, in
# the Box its common stages already use; with a weight the Box hands its slot
# to the component as its minimum (propagateMinConstraints), so a converter an
# app keeps from before fills it without being re-scaffolded.
RSpec.describe 'kjui codegen: an app component\'s weight and alignment in its parent' do
  probes = { 'ProbeBar' => ParentScopeProbes::Bare, 'ProbeOwns' => ParentScopeProbes::Owns }

  before do
    allow(KjuiTools::Compose::ComposeBuilder).to receive(:custom_component_class) { |t| probes[t] }
    allow(KjuiTools::Compose::ComposeBuilder).to receive(:custom_component_types).and_return(probes.keys)
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    JsonUIShared::TypeSynonyms.app_types = probes.keys
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  after do
    JsonUIShared::TypeSynonyms.app_types = []
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  def emit(node)
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@required_imports, Set.new)
    builder.instance_variable_set(:@responsive_counter, 0)
    builder.instance_variable_set(:@responsive_functions, [])
    builder.send(:generate_component, JSON.parse(JSON.generate(node)), 0).to_s
  end

  def row(child, orientation = 'horizontal')
    parent = { 'type' => 'View', 'child' => [child] }
    parent['orientation'] = orientation if orientation
    parent
  end

  it 'weights the ticket\'s bar: a Box with the weight hands the slot to the component as its minimum' do
    code = emit(row({ 'type' => 'ProbeBar', 'id' => 'bar', 'weight' => 1, 'height' => 12, 'leftMargin' => 8 }))
    box = code[/Box\(\n\s*modifier = Modifier\.weight\(1f\),\n\s*propagateMinConstraints = true\n\s*\) \{\n\s*ProbeBar\(/]
    expect(box).not_to be_nil, code
  end

  it 'weights by heightWeight in a Column' do
    code = emit(row({ 'type' => 'ProbeBar', 'heightWeight' => 2 }, 'vertical'))
    expect(code).to include('.weight(2f)').and include('propagateMinConstraints = true')
  end

  it 'aligns it in its parent, without handing it the slot when it has no weight' do
    code = emit(row({ 'type' => 'ProbeBar', 'alignTop' => true }))
    expect(code).to include('.align(Alignment.Top)')
    expect(code).not_to include('propagateMinConstraints')
  end

  it 'leaves a weight and an alignment the component applies itself to it' do
    code = emit(row({ 'type' => 'ProbeOwns', 'weight' => 1, 'alignTop' => true }))
    expect(code.scan('.weight(').size).to eq(1)
    expect(code.scan('.align(').size).to eq(1)
    expect(code).not_to include('Box(')
  end

  it 'adds nothing outside a Row / Column / Box (no parent scope to weight in)' do
    expect(emit({ 'type' => 'ProbeBar', 'weight' => 1 })).not_to include('.weight(')
  end

  # BoxScope has no weight: a weight there did not compile. A built-in View
  # in a Box gets none either (the census's control below).
  it 'gives no weight in a Box, and still aligns there' do
    code = emit(row({ 'type' => 'ProbeBar', 'weight' => 1, 'alignBottom' => true }, nil))
    expect(code).not_to include('.weight(')
    expect(code).not_to include('propagateMinConstraints')
    expect(code).to include('.align(')
  end

  # The census, kept: for every SSoT common attribute, an app's component gets
  # the parent-scope modifiers (`.weight(` / `.align(`) a built-in leaf gets in
  # a Row, a Column or a Box — no fewer, and no more (a weight in a Box does
  # not compile). The attribute list is read from the SSoT,
  # so one added there is counted without editing this.
  definitions = JSON.parse(File.read(File.expand_path('../../../shared/core/attribute_definitions.json', __dir__)))
  sample = lambda do |name, spec|
    types = Array(spec['type'])
    next 1 if name =~ /weight/i
    next true if types.include?('boolean')
    next 4 if types.include?('number')

    nil
  end
  scoped = ->(code) { code.lines.map(&:strip).select { |l| l.start_with?('.weight(', '.align(', 'modifier = Modifier.weight(', 'modifier = Modifier.align(') } }

  { 'Row' => 'horizontal', 'Column' => 'vertical', 'Box' => nil }.each do |parent, orientation|
    it "gives an app component every parent-scope modifier a built-in View gets in a #{parent}" do
      checked = 0
      missing = definitions['common'].filter_map do |name, spec|
        next unless spec.is_a?(Hash)

        value = sample.call(name, spec)
        next if value.nil?

        built_in = scoped.call(emit(row({ 'type' => 'View', 'id' => 'n', name => value }, orientation)))
        checked += 1 unless built_in.empty?
        app = scoped.call(emit(row({ 'type' => 'ProbeBar', 'id' => 'n', name => value }, orientation)))
        want = built_in.map { |l| l.sub(/\Amodifier = Modifier/, '').chomp(',') }
        have = app.map { |l| l.sub(/\Amodifier = Modifier/, '').chomp(',') }
        "#{name}: built-in #{want} / app #{have}" unless want.sort == have.sort
      end
      expect(checked).to be > 0 # the census reached attributes at all (control)
      expect(missing).to eq([])
    end
  end
end
