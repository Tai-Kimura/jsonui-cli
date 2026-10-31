# frozen_string_literal: true

require_relative '../../lib/core/type_converter'
require_relative '../support/kotlin_compiler'

# A collection or a function inside a function type — a parameter or the
# return — comes out as one outside it does. The members went through a
# converter of their own that read only the type-name table, so
# `(([File]) -> Void)?` was written `(([File]) -> Unit)?`, and a nested
# `(Int) -> Void` kept its `Void`, and a Swift label (`_ id: Int`) stood as
# written: none is Kotlin, and only `Array(T)`
# and `Dictionary(K, V)` drew a warning (ticket
# rjui-closure-param-array-type-becomes-tuple, where the same converter of
# members was found in all three tools).
RSpec.describe 'kjui data types: collections and functions inside a function type' do
  KJUI_FN_CONVERTER = KjuiTools::Core::TypeConverter
  KJUI_FN_MEMBERS = {
    '(([Photo]) -> Void)?' => '((List<Photo>) -> Unit)?',
    '(([Photo]?) -> Void)?' => '((List<Photo>?) -> Unit)?',
    '(([String: Int]) -> Void)?' => '((Map<String, Int>) -> Unit)?',
    '((Array(Int)) -> Void)?' => '((List<Int>) -> Unit)?',
    '((Dictionary(String, Int)) -> Void)?' => '((Map<String, Int>) -> Unit)?',
    '(([[Double?]]) -> Void)?' => '((List<List<Double?>>) -> Unit)?',
    '((Int, [String]) -> Void)?' => '((Int, List<String>) -> Unit)?',
    '(((Int) -> Void) -> Void)?' => '(((Int) -> Unit) -> Unit)?',
    '((((Bool) -> Void)?) -> Void)?' => '((((Boolean) -> Unit)?) -> Unit)?',
    '(() -> [String])' => '(() -> List<String>)?',
    '(() -> [String: Int]?)?' => '(() -> Map<String, Int>?)?',
    '(() -> (Int) -> Bool)?' => '(() -> (Int) -> Boolean)?',
    '((Int) -> Bool?)?' => '((Int) -> Boolean?)?',
    '((_ id: Int, _ tags: [String: Any]) -> Void)?' => '((id: Int, tags: Map<String, Any>) -> Unit)?',
    '((name: String, Int) -> Void)?' => '((name: String, Int) -> Unit)?'
  }.freeze

  it 'writes each member as Kotlin' do
    KJUI_FN_MEMBERS.each { |spec_type, kotlin| expect(KJUI_FN_CONVERTER.to_kotlin_type(spec_type, 'compose')).to eq(kotlin), spec_type }
  end

  it 'warns for none of them' do
    warned = []
    allow(KjuiTools::Core::Logger).to receive(:warn) { |m| warned << m }
    KJUI_FN_MEMBERS.each_key { |t| KJUI_FN_CONVERTER.convert_type(t, 'compose') }
    expect(warned).to eq([])
  end

  it 'type-checks with kotlinc' do
    skip("kotlinc: #{KotlinCompiler.unavailable_reason}") if KotlinCompiler.unavailable_reason && ENV['KJUI_REQUIRE_KOTLINC'] != '1'
    # What the converter writes, not the table's expectation.
    props = KJUI_FN_MEMBERS.keys.each_with_index.map do |t, i|
      "    val p#{i}: #{KJUI_FN_CONVERTER.to_kotlin_type(t, 'compose')}"
    end
    source = "class Photo\n\ninterface Holder {\n#{props.join("\n")}\n}\n"
    expect(KotlinCompiler.compile(source).errors).to eq([])
    # The control: what the converter wrote before does not.
    expect(KotlinCompiler.compile("interface H {\n    val p: (([String]) -> Unit)?\n}\n").errors).not_to eq([])
  end
end
