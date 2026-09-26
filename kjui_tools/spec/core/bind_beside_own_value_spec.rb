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
    expect(cases.size).to be >= 12
    said = cases.map do |c|
      validator = KjuiTools::Core::AttributeValidator.new(:compose)
      validator.validate(JSON.parse(JSON.generate(c['node'])))
      # every sentence about `bind` (the "is ignored" one, and a Collection's)
      [c['name'], validator.warnings.grep(/'bind/).map { |w| w[/'bind.*\z/] }]
    end
    expected = cases.map { |c| [c['name'], c['warning'] ? [c['warning']] : []] }
    expect(said).to eq(expected)
  end

  it 'follows the declaration (a section the table does not map says nothing)' do
    validator = KjuiTools::Core::AttributeValidator.new(:compose)
    table = validator.definitions.dig('common', 'bind', 'primaryValue')
    expect(table.keys).to include('Switch', 'CheckBox', 'Slider', 'Segment', 'SelectBox', 'Progress')
    # `bind` is not a Collection's data source (that is `items`)
    expect(table.keys).not_to include('Collection')
    table.each do |section, values|
      values.each { |attr| expect(validator.definitions.dig(section, attr)).to be_a(Hash), "#{section}.#{attr}" }
    end
  end
end
