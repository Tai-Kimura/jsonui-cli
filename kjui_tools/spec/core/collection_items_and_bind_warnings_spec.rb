# frozen_string_literal: true

require 'core/attribute_validator'

# The shared validator's two Collection sentences (shared/core, mirrored):
# - `items` is a binding only since 2026-09-26: the array form was declared
#   and drawn by no platform, codegen or Dynamic, and used by no face (all
#   116 face Collections bind it). A literal array is named for what it is.
# - `bind` on a Collection (a Table is one) is not its data source.
# Ticket collection-attributes-declared-but-not-drawn-on-some-paths.
RSpec.describe 'shared validator: Collection items and bind' do
  let(:validator) { KjuiTools::Core::AttributeValidator.new(:compose) }

  def said(extra, type: 'Collection')
    node = { 'type' => type, 'id' => 'list', 'width' => 100, 'height' => 100, 'cellIdProperty' => 'id' }.merge(extra)
    validator.validate(node).grep(/'items'|'bind'/)
  end

  it 'names a literal array: a binding is what every platform draws' do
    expect(said({ 'items' => %w[a b] })).to eq(
      ["[id=list] Attribute 'items' in 'Collection' takes a binding (\"@{…}\"), got a literal array: " \
       'no platform draws a literal here — bind it']
    )
  end

  it 'says nothing about a bound items (the control)' do
    expect(said({ 'items' => '@{rows}' })).to eq([])
  end

  it 'says bind is not the data source, on a Collection and on a Table' do
    %w[Collection Table].each do |type|
      expect(said({ 'items' => '@{rows}', 'bind' => '@{rows}' }, type: type)).to eq(
        ["[id=list] 'bind' is not a Collection's data source; use 'items' (e.g. \"items\": \"@{rows}\")"]
      ), type
    end
  end

  it 'says nothing about bind where it is the primary value (the control)' do
    node = { 'type' => 'Switch', 'id' => 'toggle', 'width' => 100, 'height' => 40, 'bind' => '@{isOn}' }
    expect(validator.validate(node).grep(/'bind'/)).to eq([])
  end
end
