# frozen_string_literal: true

require 'core/attribute_types'
require 'react/generators/react_component_generator'
require_relative '../../support/typescript_compiler'

# Every attribute type `rjui g converter` understands: the React component it
# scaffolds, compiled with tsc --strict. The list is DERIVED from the shared
# vocabulary (lib/core/attribute_types.rb) that sjui and kjui scaffold from,
# plus `T?`, `[T]`, callbacks and types outside it.
#
# Until 1.8.121 rjui compiled every type by turning most of them into `any`
# without a word — a Long, a Color, `String?`, `[String]` (2026-09-26). Each is
# asserted to be the table's type here, and the whole set compiled. Ticket
# kjui-sjui-converter-attr-types-do-not-compile.
RSpec.describe 'rjui g converter and every attribute type' do
  # Enough of React for the scaffold: `import React from 'react'` and
  # `React.FC<Props>`.
  def react
    <<~TS
      declare module 'react' {
        namespace React { type ReactNode = any; type FC<P = {}> = (props: P) => any; function createElement(...a: any[]): any; }
        export default React;
      }
    TS
  end

  def types
    vocab = JsonUIShared::AttributeTypes::VOCABULARY.keys.reject { |k| k.include?('_') } +
            JsonUIShared::AttributeTypes::ALIASES.keys
    vocab + ['String?', 'Int?', '[String]', '[Int]?', 'Array(Double)', 'Array', 'Object?', '(() -> Void)?', 'Callback'] +
      %w[Date [AppRow] Array(AppSection)]
  end

  def component(name, type)
    RjuiTools::React::Generators::ReactComponentGenerator
      .new(name, { is_container: nil, attributes: { 'v' => type } }, {}).send(:component_template)
  end

  it 'types each prop as the shared table does' do
    expect(component('A', 'Long')).to include('v?: number;')
    expect(component('B', 'Color')).to include('v?: string;')
    expect(component('C', '[String]')).to include('v?: string[];')
    expect(component('D', 'String?')).to include('v?: string;')
    expect(component('E', '[AppRow]')).to include('v?: any[];')
  end

  it 'compiles the component for every type, and for the types outside the vocabulary' do
    source = types.each_with_index.map do |type, i|
      component("T#{i}", type).lines.reject { |l| l.start_with?('import React', 'export default') }.join
    end.join("\n")
    expect("import React from 'react';\n#{source}").to compile_as_typescript.with_ambient(react)
  end
end
