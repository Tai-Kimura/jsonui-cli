# frozen_string_literal: true

require 'stringio'
require 'core/logger'
require 'core/attribute_types'
require 'react/generators/react_component_generator'
require 'react/generators/converter_generator'
require_relative '../../support/typescript_compiler'

# A literal the layout gives a custom component's prop, through the converter
# `rjui g converter` writes: every type × a valid value, a `false`, and a value
# of the wrong kind. Every call is type-checked with tsc --strict against the
# component scaffolded from the same attribute; a value that is not written is
# named; and for every type in the vocabulary rjui writes exactly the values
# sjui and kjui write (the shared table's swift_literal / kotlin_literal —
# one answer on the three tools). The one difference is a type outside the
# vocabulary: `any` in TypeScript, so its JSON value is written.
#
# Until 1.8.121 (measured on 1b80b5ba + the literal-null fix, 2026-09-26)
# rjui wrote literals through its own path and checked none: a `false` was
# dropped without a word, `"abc"` for an Int became `{abc}` (TS2304), "yes"
# for a Bool `{true}`, a number for a String its text, a callback's string
# `{"x"}` (TS2322) — 22 of 31 wrong-kind values did not type-check, and two
# valid ones. Ticket rjui-literal-props-are-not-checked-against-the-type.
RSpec.describe 'rjui g converter: a literal the layout gives a prop, against its type' do
  EXT_LITERAL_TYPES = File.expand_path('../../../lib/react/converters/extensions', __dir__)

  REACT_LITERAL_TYPES = <<~TS
    declare module 'react' {
      namespace React { type ReactNode = any; type FC<P = {}> = (props: P) => any; function createElement(...a: any[]): any; }
      export default React;
    }
  TS

  before do
    %i[info debug warn success error].each { |m| allow(RjuiTools::Core::Logger).to receive(m) }
  end

  STR_LITERAL_TYPES = 'Hi "q" $x \\(y) `t` ${z}'

  # type => [a valid value, a value of the wrong kind]
  def self.values
    {
      'String' => [STR_LITERAL_TYPES, false], 'Int' => [3, 'abc'], 'Long' => [5, 'abc'], 'Float' => [1.5, 'abc'],
      'Double' => [2.25, 'abc'], 'CGFloat' => [1.5, 'abc'], 'Bool' => [false, 'yes'], 'Color' => ['#FF8800', 5],
      'Object' => [{ 'a' => 1, 'b' => 'x "y"' }, 'x'], 'text' => [STR_LITERAL_TYPES, 7], 'integer' => [4, 'x'],
      'number' => [0.5, 'x'], 'boolean' => [true, 'no'], 'hash' => [{ 'k' => 'v' }, 3],
      'dictionary' => [{ 'k' => [1, nil] }, true], '[String]' => [['a', 'b "q"'], 'x'], '[Int]' => [[1, 2], [1, 'x']],
      'Array(Float)' => [[1, 0.5], 'x'], 'Array' => [[1, 'a', nil], 'x'], 'Row!!' => [{ 'k' => 'v' }, 'x'],
      '[Row]' => [[{ 'k' => 'v' }], 'x'], 'CollectionDataSource' => [{ 'k' => 'v' }, 'x'],
      'String?' => [STR_LITERAL_TYPES, 5], 'Int?' => [7, 'x'], 'Bool?' => [false, 1], 'Object?' => [{ 'k' => 'v' }, 'x'],
      '[Int]?' => [[1], 'x'], 'Row' => [{ 'k' => 'v' }, 'x'], 'Row?' => [{ 'k' => 'v' }, 'x'], 'Callback' => ['x', 5],
      '(() -> Void)?' => ['x', 5]
    }
  end

  def converter_for(name, type)
    code = RjuiTools::React::Generators::ConverterGenerator
           .new(name, { attributes: { 'v' => type }, is_container: false }, {}, 'spec').send(:converter_template)
    code = code.gsub(/require_relative '([^']+)'/) { "require '#{File.expand_path(Regexp.last_match(1), EXT_LITERAL_TYPES)}'" }
    eval(code, TOPLEVEL_BINDING, "#{name}_converter.rb") # rubocop:disable Security/Eval
    RjuiTools::React::Converters::Extensions.const_get("#{name}Converter")
  end

  # Built once (the converters are classes; building them per example
  # redefines them, and Ruby says so under --warnings).
  before(:all) do
    @rows = self.class.values.each_with_index.flat_map do |(type, (valid, wrong)), i|
      [[:valid, valid], [:false, false], [:wrong, wrong]].map do |kase, value|
        name = "LiteralType#{kase.to_s.capitalize}#{i}"
        said = StringIO.new
        saved = $stderr
        call = begin
          $stderr = said
          converter_for(name, type).new({ 'type' => name, 'v' => value }, {}).convert(0)
        ensure
          $stderr = saved
        end
        component = RjuiTools::React::Generators::ReactComponentGenerator
                    .new(name, { is_container: false, attributes: { 'v' => type } }, {}).send(:component_template)
        [type, kase, value, call, said.string.lines.grep(/\A\[rjui\] /).join, component]
      end
    end
  end

  def written?(call)
    call.include?(' v=')
  end

  it 'type-checks every call against its component' do
    source = @rows.each_with_index.map do |(_, _, _, call, _, component), i|
      body = component.lines.reject { |l| l.start_with?('import React', 'export default') }.join
      "#{body}\nconst literalTypeHost#{i} = (\n#{call}\n);\n"
    end.join
    expect("import React from 'react';\n#{source}").to compile_as_typescript.with_ambient(REACT_LITERAL_TYPES)
  end

  it 'writes a false for a Bool, and names every value it does not write' do
    aggregate_failures do
      @rows.each do |type, kase, value, call, said, _|
        expect(call).to include(' v={false}'), type if kase == :false && type.sub('?', '').casecmp?('bool')
        next if written?(call)

        expect(said).to include("the layout's #{value.inspect} is not a #{type} literal"), "#{type} #{kase}: #{call}"
      end
    end
  end

  it 'writes exactly the values sjui and kjui write, for every type in the vocabulary' do
    aggregate_failures do
      @rows.each do |type, kase, value, call, _, _|
        parsed = JsonUIShared::AttributeTypes.parse(type)
        next unless parsed.vocabulary?

        # The sjui and kjui converters write a colour through their own
        # hook (a hex or a resource name, any String) — given here as they
        # give it.
        color = ->(canonical, literal) { 'color' if canonical == 'color' && literal.is_a?(String) }
        swift = !JsonUIShared::AttributeTypes.swift_literal(type, value, &color).nil?
        kotlin = !JsonUIShared::AttributeTypes.kotlin_literal(type, value, &color).nil?
        expect([written?(call), written?(call)]).to eq([swift, kotlin]), "#{type} #{kase} #{value.inspect}: #{call}"
      end
    end
  end

  it 'writes the JSON value of a type outside the vocabulary, which TypeScript declares `any`' do
    row = @rows.find { |type, kase, *| type == 'Row!!' && kase == :valid }
    expect(row[3]).to include(' v={{"k":"v"}}')
  end
end
