# frozen_string_literal: true

require 'stringio'
require 'core/logger'
require 'core/attribute_types'
require 'react/generators/react_component_generator'
require 'react/generators/converter_generator'
require_relative '../../support/typescript_compiler'

# A binding attribute (`@v:T`) through `rjui g converter`: the component
# declares the prop `v` (React passes it one way), and the converter reads the
# layout's `v` — a binding `@{v}` as `data.v`, any other value by the rules
# of every other prop (the shared ts_literal; a value of another kind named).
# Type-checked with tsc --strict.
#
# Until 1.9.0 (measured on 32785ce8, 2026-09-26) the component declared
# `@v?: …`, which is not TypeScript (TS1131) — 50 of 50 calls failed — and the
# converter read `json['@v']`, which no layout has, so the prop was dropped
# whatever the layout gave it. Ticket
# binding-prop-with-a-non-binding-value-does-not-compile.
RSpec.describe 'rjui g converter: a binding attribute' do
  EXT_BINDING_R = File.expand_path('../../../lib/react/converters/extensions', __dir__)

  REACT_BINDING = <<~TS
    declare module 'react' {
      namespace React { type ReactNode = any; type FC<P = {}> = (props: P) => any; function createElement(...a: any[]): any; }
      export default React;
    }
  TS

  before do
    %i[info debug warn success error].each { |m| allow(RjuiTools::Core::Logger).to receive(m) }
  end

  def self.values
    { 'String' => ['Hi', 5], 'Int' => [3, 'abc'], 'Bool' => [false, 'yes'], 'Object' => [{ 'a' => 1 }, 'x'],
      '[String]' => [%w[a b], 'x'], 'String?' => ['Hi', 5] }
  end

  before(:all) do
    @rows = self.class.values.each_with_index.flat_map do |(type, (literal, wrong)), i|
      { binding: '@{v}', literal: literal, wrong: wrong, absent: :absent }.map do |kase, value|
        name = "BindingAttr#{kase.to_s.capitalize}#{i}"
        code = RjuiTools::React::Generators::ConverterGenerator
               .new(name, { attributes: { '@v' => type }, is_container: false }, {}, 'spec').send(:converter_template)
        code = code.gsub(/require_relative '([^']+)'/) { "require '#{File.expand_path(Regexp.last_match(1), EXT_BINDING_R)}'" }
        eval(code, TOPLEVEL_BINDING, "#{name}_converter.rb") # rubocop:disable Security/Eval
        node = { 'type' => name }
        node['v'] = value unless kase == :absent
        # Printed through rjui's warning logger ("[WARN] ", stdout; the
        # logger is not stubbed in before(:all)) — from 1.9.0 the line goes
        # there, not to stderr through a bare `warn`.
        said = StringIO.new
        saved = $stdout
        call = begin
          $stdout = said
          RjuiTools::React::Converters::Extensions.const_get("#{name}Converter").new(node, {}).convert(0)
        ensure
          $stdout = saved
        end
        component = RjuiTools::React::Generators::ReactComponentGenerator
                    .new(name, { is_container: false, attributes: { '@v' => type } }, {}).send(:component_template)
        [type, kase, call, said.string.lines.grep(/\[rjui\] /).map { |l| l.sub(/\A.*?(?=\[rjui\] )/, '') }.join,
         component, i]
      end
    end
  end

  it 'declares the prop `v`, and type-checks every call in a host whose data has `v`' do
    expect(@rows.map { |r| r[4] }).to all(include('  v?: ')), @rows.first[4]
    source = @rows.map do |type, _, call, _, component, _|
      body = component.lines.reject { |l| l.start_with?('import React', 'export default') }.join
      ts = JsonUIShared::AttributeTypes.ts_type(JsonUIShared::AttributeTypes.parse(type))
      "#{body}\nconst #{component[/export const (\w+)/, 1]}Host = (data: { v: #{ts} }) => (\n#{call}\n);\n"
    end.join
    expect("import React from 'react';\n#{source}").to compile_as_typescript.with_ambient(REACT_BINDING)
  end

  it 'passes a binding as data.v, a literal of the type (a false too) as itself, and names any other value' do
    aggregate_failures do
      @rows.each do |type, kase, call, said, _, _|
        case kase
        when :binding then expect(call).to include(' v={data.v}'), call
        when :literal then expect(call).to include(' v={'), "#{type}: #{call}"
        when :wrong
          expect(call).not_to include(' v=')
          expect(said).to include("is not a #{type} literal"), "#{type}: #{said.inspect}"
        else expect(call).not_to include(' v=')
        end
      end
    end
    expect(@rows.find { |type, kase, *| type == 'Bool' && kase == :literal }[2]).to include(' v={false}')
  end
end
