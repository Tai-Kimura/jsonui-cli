# frozen_string_literal: true

require 'core/type_converter'
require_relative '../support/emitted_swift'

# A collection or a function inside a function type — a parameter or the
# return — comes out as one outside it does. `[T]` and `[K: V]` were
# already Swift there; `Array(T)` and `Dictionary(K, V)` came out as
# written, which Swift does not read, and so did a label other than `_`,
# which a function type refuses (ticket
# rjui-closure-param-array-type-becomes-tuple, where the same converter of
# members was found in all three tools).
RSpec.describe 'sjui data types: collections and functions inside a function type' do
  include EmittedSwift

  SJUI_FN_CONVERTER = SjuiTools::Core::TypeConverter
  SJUI_FN_MEMBERS = {
    '(([Photo]) -> Void)?' => '(([Photo]) -> Void)?',
    '(([String: Int]) -> Void)?' => '(([String: Int]) -> Void)?',
    '((Array(Int)) -> Void)?' => '(([Int]) -> Void)?',
    '((Dictionary(String, Int)) -> Void)?' => '(([String: Int]) -> Void)?',
    '(([[Double?]]) -> Void)?' => '(([[Double?]]) -> Void)?',
    '(((Int) -> Void) -> Void)?' => '(((Int) -> Void) -> Void)?',
    '((((Int) -> Void)?) -> Void)?' => '((((Int) -> Void)?) -> Void)?',
    '(() -> Array(String))?' => '(() -> [String])?',
    '(() -> Dictionary(String, Int)?)?' => '(() -> [String: Int]?)?',
    '(() -> (Int) -> Bool)?' => '(() -> (Int) -> Bool)?',
    '((Int) -> Bool?)?' => '((Int) -> Bool?)?',
    '((_ id: Int, _ tags: [String: Any]) -> Void)?' => '((_ id: Int, _ tags: [String: Any]) -> Void)?',
    '((id: Int, outer name: Array(String)) -> Void)?' => '((_ id: Int, _ name: [String]) -> Void)?'
  }.freeze

  it 'writes each member as Swift' do
    SJUI_FN_MEMBERS.each do |spec_type, swift|
      expect(SJUI_FN_CONVERTER.to_swift_type(spec_type, 'swiftui')).to eq(swift), spec_type
    end
  end

  it 'warns for none of them' do
    warned = []
    allow(SjuiTools::Core::Logger).to receive(:warn) { |m| warned << m }
    SJUI_FN_MEMBERS.each_key { |t| SJUI_FN_CONVERTER.convert_type(t, 'swiftui') }
    expect(warned).to eq([])
  end

  it 'type-checks with swiftc' do
    # What the converter writes, not the table's expectation.
    props = SJUI_FN_MEMBERS.keys.each_with_index.map do |t, i|
      "var p#{i}: #{SJUI_FN_CONVERTER.to_swift_type(t, 'swiftui')}? = nil"
    end
    expect(compilable_data(props.join("\n"), stubs: 'struct Photo {}')).to compile_as_swift
    # The control: a label as it was written is refused.
    expect(compilable_data('var p: ((id: Int) -> Void)? = nil', stubs: '')).not_to compile_as_swift
  end
end
