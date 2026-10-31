# frozen_string_literal: true

require_relative '../../lib/core/type_converter'
require_relative '../support/typescript_compiler'

# A collection or a function inside a function type — a parameter or the
# return — comes out as one outside it does. The members went through a
# converter of their own that read only the type-name table, so
# `(([File]) -> Void)?` was written `(arg0: [File]) => void`: a one-element
# tuple, which still accepts a handler of `File[]`, so nothing said so
# (ticket rjui-closure-param-array-type-becomes-tuple). `[K: V]`,
# `Array(T)`, `Dictionary(K, V)`, a nested `(Int) -> Void` and a Swift
# label (`arg0: _ id: Int`) came out as written, which TypeScript does not
# read; a label now names the parameter.
RSpec.describe 'rjui data types: collections and functions inside a function type' do
  RJUI_FN_CONVERTER = RjuiTools::Core::TypeConverter
  RJUI_FN_MEMBERS = {
    '(([Photo]) -> Void)?' => '((arg0: Photo[]) => void) | undefined',
    '(([Photo]?) -> Void)?' => '((arg0: Photo[] | undefined) => void) | undefined',
    '(([String: Int]) -> Void)?' => '((arg0: Record<string, number>) => void) | undefined',
    '((Array(Int)) -> Void)?' => '((arg0: number[]) => void) | undefined',
    '((Dictionary(String, Int)) -> Void)?' => '((arg0: Record<string, number>) => void) | undefined',
    '(([[Double?]]) -> Void)?' => '((arg0: (number | undefined)[][]) => void) | undefined',
    '((Int, [String]) -> Void)?' => '((arg0: number, arg1: string[]) => void) | undefined',
    '(((Int) -> Void) -> Void)?' => '((arg0: (arg0: number) => void) => void) | undefined',
    '((((Int) -> Void)?) -> Void)?' => '((arg0: ((arg0: number) => void) | undefined) => void) | undefined',
    '(() -> [String])' => '(() => string[]) | undefined',
    '(() -> Array(String))?' => '(() => string[]) | undefined',
    '(() -> [String: Int]?)?' => '(() => Record<string, number> | undefined) | undefined',
    '(() -> (Int) -> Bool)?' => '(() => (arg0: number) => boolean) | undefined',
    '((Int) -> Bool?)?' => '((arg0: number) => boolean | undefined) | undefined',
    '((_ id: Int, _ tags: [String: Any]) -> Void)?' => '((id: number, tags: Record<string, any>) => void) | undefined',
    '((name: String, Int) -> Void)?' => '((name: string, arg1: number) => void) | undefined'
  }.freeze

  it 'writes each member as TypeScript' do
    RJUI_FN_MEMBERS.each { |spec_type, ts| expect(RJUI_FN_CONVERTER.to_typescript_type(spec_type)).to eq(ts), spec_type }
  end

  it 'warns for none of them' do
    warned = []
    allow(RjuiTools::Core::Logger).to receive(:warn) { |m| warned << m }
    RJUI_FN_MEMBERS.each_key { |t| RJUI_FN_CONVERTER.convert_type(t) }
    expect(warned).to eq([])
  end

  # What the converter writes, not the table's expectation; the first member
  # is called with two photos, which a one-element tuple refuses.
  def holder(first_type = RJUI_FN_CONVERTER.to_typescript_type(RJUI_FN_MEMBERS.keys[0]))
    props = RJUI_FN_MEMBERS.keys.each_with_index.map do |t, i|
      "  p#{i}?: #{i.zero? ? first_type : RJUI_FN_CONVERTER.to_typescript_type(t)};"
    end
    <<~TS
      export interface Photo { id: string }
      export interface Holder {
      #{props.join("\n")}
      }
      export function hand(h: Holder, photos: Photo[]): void {
        h.p0?.(photos);
        h.p0?.([{ id: 'a' }, { id: 'b' }]);
      }
    TS
  end

  it 'type-checks with tsc, a callback handed an array of two', :typescript_compile do
    expect(holder).to compile_as_typescript
  end

  # The compiler's own control: the tuple rjui wrote before is refused.
  it 'would not type-check with the tuple', :typescript_compile do
    expect(holder('((arg0: [Photo]) => void) | undefined')).not_to compile_as_typescript
  end
end
