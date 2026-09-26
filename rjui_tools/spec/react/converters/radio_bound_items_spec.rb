# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/radio_converter'
require_relative '../../support/typescript_compiler'

# Radio `items` is declared ["array", "binding"]: an array is the options,
# written out one by one; a binding is a list the data holds, mapped at render
# time — what KotlinJsonUI's dynamic renderer does with it.
#
# Until 1.8.121 (measured on 32785ce8, 2026-09-26) a bound `items` raised
# NoMethodError (`any?` on a String) and took the build down. Ticket
# kjui-codegen-table-crashes-on-an-items-array.
RSpec.describe 'rjui Radio: each declared shape of `items`' do
  def convert(node)
    RjuiTools::React::Converters::RadioConverter.new(node, { 'use_tailwind' => true }).convert
  end

  let(:array) { convert('type' => 'Radio', 'id' => 'r', 'items' => %w[a b], 'selectedValue' => '@{sel}') }
  let(:bound) { convert('type' => 'Radio', 'id' => 'r', 'items' => '@{rows}', 'selectedValue' => '@{sel}') }

  it 'maps a bound list to one option per item, compared and chosen by the item' do
    expect(bound).to include('{data.rows.map((item) => (')
      .and include('value={item}').and include('checked={data.sel === item}').and include('onChange={() => data.setSel?.(item)}')
    expect(bound.scan('<input').size).to eq(1)
    expect(array.scan('<input').size).to eq(2)
  end

  it 'a static selection still answers at codegen time for an array, and compares at run time for a binding' do
    static_array = convert('type' => 'Radio', 'id' => 'r', 'items' => %w[a b], 'selectedValue' => 'a')
    static_bound = convert('type' => 'Radio', 'id' => 'r', 'items' => '@{rows}', 'selectedValue' => 'a')
    expect(static_array).to include('checked={true}').and include('checked={false}')
    expect(static_bound).to include('checked={"a" === item}')
  end

  it 'typechecks both shapes under --strict' do
    ambient = <<~TS
      declare const data: { rows: string[]; sel: string; setSel?: (value: string) => void };
    TS
    expect(<<~TSX).to compile_as_typescript.with_ambient("#{TypeScriptCompiler::AMBIENT}\n#{ambient}")
      export const FromArray = (): JSX.Element => (
      #{array}
      );
      export const FromBinding = (): JSX.Element => (
      #{bound}
      );
    TSX
  end
end
