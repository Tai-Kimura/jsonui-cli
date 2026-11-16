# frozen_string_literal: true

require 'core/type_converter'
require_relative '../support/emitted_swift'

# A collection a layout's data declares comes out as a Swift type. `[T]` and
# `[K: V]` were already Swift; `List(T)` and `Map(K, V)` came out as written,
# which Swift does not read. The spec's shapes are read by the shared core
# (collection_shape), as kjui and rjui read them (ticket
# kjui-spec-swift-dictionary-type-emits-invalid-kotlin), and a type Swift has
# no spelling for is a build warning.
RSpec.describe 'sjui data types: collections' do
  include EmittedSwift

  SJUI_COLLECTION_CONVERTER = SjuiTools::Core::TypeConverter
  SJUI_COLLECTIONS_MAPPED = {
    '[String]' => '[String]',
    '[[Item]]' => '[[Item]]',
    '[String: String]?' => '[String: String]?',
    '[String: [Item]]' => '[String: [Item]]',
    'Dictionary(String, [Item])' => '[String: [Item]]',
    'Dictionary(String, Map(String, Int))' => '[String: [String: Int]]',
    'Map(String, Item)?' => '[String: Item]?',
    'List(Item)' => '[Item]',
    'Array(Item)?' => '[Item]?'
  }.freeze

  it 'writes each shape as a Swift collection' do
    SJUI_COLLECTIONS_MAPPED.each do |spec_type, swift|
      expect(SJUI_COLLECTION_CONVERTER.to_swift_type(spec_type, 'swiftui')).to eq(swift), spec_type
    end
  end

  it 'warns for a type Swift has no spelling for, and only then' do
    warned = []
    allow(SjuiTools::Core::Logger).to receive(:warn) { |m| warned << m }
    SJUI_COLLECTIONS_MAPPED.each_key { |t| SJUI_COLLECTION_CONVERTER.convert_type(t, 'swiftui') }
    expect(warned).to eq([])
    ['List<Item>', 'Map<String, Item>', 'Item[]'].each { |t| SJUI_COLLECTION_CONVERTER.convert_type(t, 'swiftui') }
    expect(warned.length).to eq(3)
    expect(warned[0]).to include("type 'List<Item>'", 'not a Swift type')
  end

  it 'type-checks with swiftc' do
    # What the converter writes, not the table's expectation.
    props = SJUI_COLLECTIONS_MAPPED.keys.each_with_index.map do |t, i|
      "var p#{i}: #{SJUI_COLLECTION_CONVERTER.to_swift_type(t, 'swiftui')}? = nil"
    end
    expect(compilable_data(props.join("\n"), stubs: 'struct Item {}')).to compile_as_swift
  end
end
