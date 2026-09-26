# frozen_string_literal: true

require 'core/attribute_validator'
require 'json'

# `bind` beside a component's own value attribute: the own attribute "takes
# precedence when both are set" (SSoT common.bind, `primaryValue`). The layout
# normalizer drops such a `bind` with a named warning; the shared validator
# (attribute_validator_core.rb, byte-identical in the three tools) says the
# same sentence for a layout the normalizer did not fold. Both run
# shared/core/bind_fold_vectors.json.
RSpec.describe 'shared validator: bind beside the own value attribute' do
  vectors = File.expand_path('../../../shared/core/bind_fold_vectors.json', __dir__)

  it 'says what every case of the shared table says, and nothing where it says nothing' do
    skip 'shared/core/bind_fold_vectors.json not present in this layout' unless File.exist?(vectors)

    cases = JSON.parse(File.read(vectors))['cases']
    expect(cases.size).to be >= 18
    said = cases.map do |c|
      validator = KjuiTools::Core::AttributeValidator.new(:compose)
      validator.validate(JSON.parse(JSON.generate(c['node'])))
      # every sentence about `bind` (the "is ignored" one, and a Collection's)
      # and about a value attribute of another kind (a Date SelectBox's)
      [c['name'], validator.warnings.grep(/'bind|has no effect on a /).map { |w| w[/'(bind|[a-zA-Z]+' has no effect).*\z/] }]
    end
    expected = cases.map { |c| [c['name'], c['warning'] ? [c['warning']] : []] }
    expect(said).to eq(expected)
  end

  # The fold every renderer applies on the node it draws (shared/core/bind_fold.rb,
  # mirrored into each tool's lib/core): the table's cases, and the style cases
  # — the node's style merged first (the node's own attributes win).
  it 'folds every case, and every style case after the merge (JsonUIShared::BindFold)' do
    skip 'shared/core/bind_fold_vectors.json not present in this layout' unless File.exist?(vectors)

    require 'core/bind_fold'
    table = JSON.parse(File.read(vectors))
    expect(table['cases'].size).to be >= 18
    got = table['cases'].map { |c| [c['name'], JsonUIShared::BindFold.fold(JSON.parse(JSON.generate(c['node'])))] }
    expect(got).to eq(table['cases'].map { |c| [c['name'], c['expect']] })
    expect(table['style_cases'].size).to be >= 2
    drawn = table['style_cases'].map do |c|
      node = JSON.parse(JSON.generate(c['node']))
      merged = c['styles'].fetch(node['style']).merge(node).reject { |k, _| k == 'style' }
      [c['name'], JsonUIShared::BindFold.fold(merged)]
    end
    expect(drawn).to eq(table['style_cases'].map { |c| [c['name'], c['drawn']] })
    got_for = table['attributes_for_cases'].map { |c| [c['name'], JsonUIShared::BindFold.attributes_for(c['type'], c['node'])] }
    expect(got_for).to eq(table['attributes_for_cases'].map { |c| [c['name'], c['expect']] })
  end

  # The one function every reader of primaryValue answers the same (the
  # generated JsonUIBindPrimaryValue on Kotlin / Swift, the jui normalizer):
  # here, the shared validator's bind_value_attributes, on the section the
  # validator maps the type to.
  it 'answers every attributes_for case of the shared table' do
    skip 'shared/core/bind_fold_vectors.json not present in this layout' unless File.exist?(vectors)

    cases = JSON.parse(File.read(vectors))['attributes_for_cases']
    expect(cases.size).to be >= 9
    validator = KjuiTools::Core::AttributeValidator.new(:compose)
    got = cases.map do |c|
      section = validator.send(:map_type_to_definition, c['type'])
      [c['name'], validator.send(:bind_value_attributes, section, c['node']) || []]
    end
    expect(got).to eq(cases.map { |c| [c['name'], c['expect']] })
  end

  # A Date SelectBox's value is selectedDate (primaryValue by selectItemType):
  # its selectedValue / selectedItem / selectedIndex are read by no path, and
  # each is named. A list box says nothing about them, and nothing about a
  # selectedDate (the ruling names the Date direction only); a kind the table
  # does not name ("date") is the whenAbsent one, as the codegens compare it.
  it 'names each value attribute a Date SelectBox has no use for, and nothing else' do
    said = lambda do |node|
      validator = KjuiTools::Core::AttributeValidator.new(:compose)
      validator.validate(node)
      validator.warnings.grep(/has no effect on a /).map { |w| w[/'[a-zA-Z]+' has no effect.*\z/] }
    end
    date = { 'type' => 'SelectBox', 'selectItemType' => 'Date', 'selectedDate' => '@{day}' }
    expect(said.call(date.merge('selectedValue' => 'a', 'selectedItem' => '@{i}', 'selectedIndex' => 1))).to eq(
      ["'selectedValue' has no effect on a Date SelectBox — its value is selectedDate",
       "'selectedItem' has no effect on a Date SelectBox — its value is selectedDate",
       "'selectedIndex' has no effect on a Date SelectBox — its value is selectedDate"]
    )
    expect(said.call(date)).to eq([])
    expect(said.call({ 'type' => 'SelectBox', 'items' => %w[a], 'selectedValue' => 'a', 'selectedDate' => 'x' })).to eq([])
    expect(said.call({ 'type' => 'SelectBox', 'selectItemType' => 'Normal', 'selectedIndex' => 0 })).to eq([])
    expect(said.call({ 'type' => 'SelectBox', 'selectItemType' => 'date', 'selectedValue' => 'a' })).to eq([])
  end

  it 'follows the declaration (a section the table does not map says nothing)' do
    validator = KjuiTools::Core::AttributeValidator.new(:compose)
    table = validator.definitions.dig('common', 'bind', 'primaryValue')
    expect(table.keys).to include('Switch', 'CheckBox', 'Slider', 'Segment', 'SelectBox', 'Progress')
    # `bind` is not a Collection's data source (that is `items`)
    expect(table.keys).not_to include('Collection')
    table.each do |section, entry|
      # a list, or (SelectBox) an object: a list per value of the attribute it is by
      lists = entry.is_a?(Hash) ? entry['lists'].values : [entry]
      if entry.is_a?(Hash)
        expect(validator.definitions.dig(section, entry['by'], 'enum')).to match_array(entry['lists'].keys)
        expect(entry['lists'].keys).to include(entry['whenAbsent'])
      end
      lists.flatten.each { |attr| expect(validator.definitions.dig(section, attr)).to be_a(Hash), "#{section}.#{attr}" }
    end
  end
end
