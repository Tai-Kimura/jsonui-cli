# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/radio_converter'
require_relative '../../support/typescript_compiler'

# Radio `items` is declared ["array", "binding"]: an array is the options,
# written out one by one; a binding is a list the data holds, mapped at render
# time — what KotlinJsonUI's dynamic renderer does with it.
#
# Until 1.9.0 (measured on 32785ce8, 2026-09-26) a bound `items` raised
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

  # A static selection is where the group starts and the user changes it
  # (6750135d, ticket static-valued-controls-do-not-change-on-a-users-tap): it
  # seeds an uncontrolled `defaultChecked`. For an array the converter knows
  # which option that is; for a binding the option is a runtime value, so the
  # seed compares at run time.
  let(:static_array) { convert('type' => 'Radio', 'id' => 'r', 'items' => %w[a b], 'selectedValue' => 'a') }
  let(:static_bound) { convert('type' => 'Radio', 'id' => 'r', 'items' => '@{rows}', 'selectedValue' => 'a') }

  it 'a static selection seeds the option it names for an array, and compares at run time for a binding' do
    inputs = static_array.scan(/<input [^>]*>/)
    expect(inputs.size).to eq(2)
    expect(inputs[0]).to include('value="a"').and include('defaultChecked')
    expect(inputs[1]).to include('value="b"')
    expect(inputs[1]).not_to include('defaultChecked')
    expect(static_array).not_to match(/\bchecked=|readOnly/)
    expect(static_bound).to include('defaultChecked={"a" === item}')
    expect(static_bound).not_to match(/\bchecked=|readOnly/)
  end

  it 'typechecks both shapes, bound and seeded, under --strict' do
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
      export const SeededArray = (): JSX.Element => (
      #{static_array}
      );
      export const SeededBinding = (): JSX.Element => (
      #{static_bound}
      );
    TSX
  end
end
