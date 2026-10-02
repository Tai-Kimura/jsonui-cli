# frozen_string_literal: true

require 'json'
require 'core/attribute_alias_fold'

# A layout `jui build` did not canonicalize (kjui build run directly, or
# normalizeLayouts: false) keeps the attribute aliases the SSoT declares, and
# a converter reading the canonical name alone never read them: SelectBox
# `onValueChanged` built with no warning and its handler was never called
# (runtime handler census, conf_ci, 2026-10-03; through `jui build` it was
# called). kjui now folds every declared alias, as the L1 canonicalizer does.
RSpec.describe KjuiTools::Core::AttributeAliasFold do
  definitions = JSON.parse(File.read(described_class::DEFINITIONS))
  declared = definitions.flat_map do |section, attrs|
    next [] unless attrs.is_a?(Hash) && !section.start_with?('_')

    attrs.flat_map do |name, spec|
      spec.is_a?(Hash) && spec['aliases'].is_a?(Array) ? spec['aliases'].map { |a| [section, name, a] } : []
    end
  end

  after do
    described_class.instance_variable_set(:@definitions, nil)
    described_class.instance_variable_set(:@by_section, nil)
  end

  it 'folds every alias the SSoT declares into its canonical name' do
    expect(declared.size).to be > 0
    missed = declared.reject do |section, canonical, alias_name|
      type = section == 'common' ? 'View' : section
      node = { 'type' => type, alias_name => 'v' }
      described_class.fold!(node)
      node[canonical] == 'v' && !node.key?(alias_name)
    end
    expect(missed).to eq([])
  end

  it 'folds SelectBox onValueChanged, the census case' do
    node = { 'type' => 'SelectBox', 'items' => %w[a b], 'onValueChanged' => '@{h}' }
    described_class.fold!(node)
    expect(node).to eq('type' => 'SelectBox', 'items' => %w[a b], 'onValueChange' => '@{h}')
  end

  it 'keeps the canonical name where both are set, and names the alias it drops' do
    node = { 'type' => 'SelectBox', 'id' => 's', 'onValueChange' => '@{a}', 'onValueChanged' => '@{b}' }
    warnings = described_class.fold!(node, source: 'x.json')
    expect(node['onValueChange']).to eq('@{a}')
    expect(node).not_to have_key('onValueChanged')
    expect(warnings).to eq(["[x.json] [id=s] 'onValueChanged' is an alias of 'onValueChange' and both are set — keeping 'onValueChange', dropping 'onValueChanged'"])
  end

  it 'reads a type synonym by its section, and walks child, children and section nodes' do
    tree = {
      'type' => 'View',
      'child' => [{ 'type' => 'EditText', 'value' => '@{t}' }],
      'children' => { 'type' => 'Slider', 'minimumValue' => 1 },
      'sections' => [{ 'header' => { 'type' => 'Switch', 'onToggle' => '@{h}' }, 'cell' => { 'type' => 'View', 'alpha' => 0.5 } }]
    }
    described_class.fold!(tree)
    expect(tree['child'][0]).to eq('type' => 'EditText', 'text' => '@{t}')
    expect(tree['children']).to eq('type' => 'Slider', 'minimum' => 1)
    expect(tree['sections'][0]['header']).to eq('type' => 'Switch', 'onValueChange' => '@{h}')
    expect(tree['sections'][0]['cell']).to eq('type' => 'View', 'opacity' => 0.5)
  end

  it 'leaves a canonicalized tree and an undeclared key as they are (idempotent)' do
    node = { 'type' => 'SelectBox', 'onValueChange' => '@{h}', 'myOwnKey' => 1 }
    before = JSON.parse(JSON.generate(node))
    2.times { expect(described_class.fold!(node)).to eq([]) }
    expect(node).to eq(before)
  end

  it 'follows the declaration when it changes' do
    swapped = JSON.parse(JSON.generate(definitions))
    swapped['Label']['text'] = (swapped['Label']['text'] || {}).merge('aliases' => ['caption'])
    described_class.instance_variable_set(:@definitions, swapped)
    described_class.instance_variable_set(:@by_section, nil)
    node = { 'type' => 'Label', 'caption' => 'hi' }
    described_class.fold!(node)
    expect(node).to eq('type' => 'Label', 'text' => 'hi')
  end
end
