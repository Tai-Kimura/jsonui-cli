# frozen_string_literal: true

require_relative '../../lib/core/type_converter'
require_relative '../support/kotlin_compiler'

# A collection a layout's data declares comes out as a Kotlin type: `[K: V]`
# went down the `[T]` rule and came out `List<K: V>`, which Gradle refused
# while the build said nothing (ticket
# kjui-spec-swift-dictionary-type-emits-invalid-kotlin); `List(T)` and
# `Map(K, V)` came out as written. The spec's shapes — `[T]`, `[K: V]`,
# `Array(T)`, `List(T)`, `Dictionary(K, V)`, `Map(K, V)`, optional, nested —
# are read by the shared core (collection_shape), and a type Kotlin has no
# spelling for is a build warning.
RSpec.describe 'kjui data types: collections' do
  KJUI_COLLECTION_CONVERTER = KjuiTools::Core::TypeConverter

  KJUI_COLLECTIONS_MAPPED = {
    '[String]' => 'List<String>',
    '[[Item]]' => 'List<List<Item>>',
    '[String: String]' => 'Map<String, String>',
    '[String: String]?' => 'Map<String, String>?',
    '[String: Item?]' => 'Map<String, Item?>',
    '[String: [Item]]' => 'Map<String, List<Item>>',
    '[[String: Int]]' => 'List<Map<String, Int>>',
    'Dictionary(String, [Item])' => 'Map<String, List<Item>>',
    'Dictionary(String, Map(String, Int))' => 'Map<String, Map<String, Int>>',
    'Map(String, Item)?' => 'Map<String, Item>?',
    'List(Item)' => 'List<Item>',
    'Array(Item)?' => 'List<Item>?',
    '[(String) -> Void]' => 'List<((String) -> Unit)?>'
  }.freeze

  it 'writes each shape as a Kotlin collection' do
    KJUI_COLLECTIONS_MAPPED.each { |spec_type, kotlin| expect(KJUI_COLLECTION_CONVERTER.to_kotlin_type(spec_type, 'compose')).to eq(kotlin), spec_type }
  end

  it 'warns for a type Kotlin has no spelling for, and only then' do
    warned = []
    allow(KjuiTools::Core::Logger).to receive(:warn) { |m| warned << m }
    KJUI_COLLECTIONS_MAPPED.each_key { |t| KJUI_COLLECTION_CONVERTER.convert_type(t, 'compose') }
    expect(warned).to eq([])
    %w[Item[] Record<string,Item>].each { |t| KJUI_COLLECTION_CONVERTER.convert_type(t, 'compose') }
    expect(warned.length).to eq(2)
    expect(warned[0]).to include("type 'Item[]'", 'not a Kotlin type')
  end

  it 'type-checks with kotlinc' do
    skip("kotlinc: #{KotlinCompiler.unavailable_reason}") if KotlinCompiler.unavailable_reason && ENV['KJUI_REQUIRE_KOTLINC'] != '1'
    # What the converter writes, not the table's expectation.
    props = KJUI_COLLECTIONS_MAPPED.keys.each_with_index.map do |t, i|
      "    val p#{i}: #{KJUI_COLLECTION_CONVERTER.to_kotlin_type(t, 'compose')}"
    end
    source = "data class Item(val id: String)\n\ninterface Holder {\n#{props.join("\n")}\n}\n"
    expect(KotlinCompiler.compile(source).errors).to eq([])
    # The control: what the converter wrote before does not.
    expect(KotlinCompiler.compile("interface H {\n    val p: List<String: String>?\n}\n").errors).not_to eq([])
  end
end
