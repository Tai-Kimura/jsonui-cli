# frozen_string_literal: true

require_relative '../../lib/core/type_converter'
require_relative '../support/typescript_compiler'

# A collection a layout's data declares comes out as a TypeScript type.
# `List(T)` and `Map(K, V)` came out as written, which TypeScript does not
# read. The spec's shapes are read by the shared core (collection_shape), as
# kjui and sjui read them (ticket
# kjui-spec-swift-dictionary-type-emits-invalid-kotlin), and a type
# TypeScript has no spelling for is a build warning.
RSpec.describe 'rjui data types: collections' do
  RJUI_COLLECTION_CONVERTER = RjuiTools::Core::TypeConverter
  RJUI_COLLECTIONS_MAPPED = {
    '[String]' => 'string[]',
    '[[Item]]' => 'Item[][]',
    '[String: String]?' => 'Record<string, string> | undefined',
    '[String: [Item]]' => 'Record<string, Item[]>',
    '[[String: Int]]' => 'Record<string, number>[]',
    'Dictionary(String, Map(String, Int))' => 'Record<string, Record<string, number>>',
    'Map(String, Item)?' => 'Record<string, Item> | undefined',
    'List(Item)' => 'Item[]',
    'Array(Item)?' => 'Item[] | undefined'
  }.freeze

  it 'writes each shape as a TypeScript collection' do
    RJUI_COLLECTIONS_MAPPED.each do |spec_type, ts|
      expect(RJUI_COLLECTION_CONVERTER.to_typescript_type(spec_type)).to eq(ts), spec_type
    end
  end

  it 'warns for a type TypeScript has no spelling for, and only then' do
    warned = []
    allow(RjuiTools::Core::Logger).to receive(:warn) { |m| warned << m }
    RJUI_COLLECTIONS_MAPPED.each_key { |t| RJUI_COLLECTION_CONVERTER.convert_type(t) }
    expect(warned).to eq([])
    RJUI_COLLECTION_CONVERTER.convert_type('Dictionary(String)')
    expect(warned.length).to eq(1)
    expect(warned[0]).to include("type 'Dictionary(String)'", 'not a TypeScript type')
  end

  it 'type-checks with tsc' do
    # What the converter writes, not the table's expectation.
    props = RJUI_COLLECTIONS_MAPPED.keys.each_with_index.map do |t, i|
      "  p#{i}: #{RJUI_COLLECTION_CONVERTER.to_typescript_type(t)};"
    end
    source = "export interface Item { id: string }\nexport interface Holder {\n#{props.join("\n")}\n}\n"
    expect(source).to compile_as_typescript
  end
end
