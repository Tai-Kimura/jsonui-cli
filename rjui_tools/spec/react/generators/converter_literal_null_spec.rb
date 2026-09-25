# frozen_string_literal: true

require 'stringio'
require 'core/logger'
require 'core/attribute_types'
require 'react/generators/react_component_generator'
require 'react/generators/converter_generator'
require_relative '../../support/typescript_compiler'

# A JSON null the layout gives a custom component's prop, through the
# converter `rjui g converter` writes: never written (every prop is optional
# in the component's TypeScript, and `null` is none of its types), and — for
# a type no tool writes a null for, the ones sjui's Swift scaffold declares
# non-optional (`String`, `[Int]`, `Object`, `Row!!` …; the shared table's
# swift_type, the declaration, not the question the converter asks) — named
# in the sentence sjui and kjui print. The calls type-check with tsc --strict
# against the components scaffolded from the same attributes.
#
# Until 1.8.121 rjui dropped a null for every type without a word (measured
# on 1b80b5ba, 2026-09-26). Ticket converter-writes-nil-for-a-forced-model-prop.
RSpec.describe 'rjui g converter: a JSON null the layout gives a prop' do
  EXTENSIONS_NULL = File.expand_path('../../../lib/react/converters/extensions', __dir__)

  before do
    %i[info debug warn success error].each { |m| allow(RjuiTools::Core::Logger).to receive(m) }
  end

  REACT_NULL = <<~TS
    declare module 'react' {
      namespace React { type ReactNode = any; type FC<P = {}> = (props: P) => any; function createElement(...a: any[]): any; }
      export default React;
    }
  TS

  def null_types
    JsonUIShared::AttributeTypes::VOCABULARY.keys + JsonUIShared::AttributeTypes::ALIASES.keys +
      ['String?', 'Int?', 'Object?', '[String]', '[Int]?', 'Array(Float)', 'Array', 'Row', 'Row?', 'Row!!',
       '[Row]', 'Callback', '(() -> Void)?']
  end

  # The converter as `g converter` writes it, loaded as if it sat in the
  # extensions directory.
  def converter_for(name, type)
    generator = RjuiTools::React::Generators::ConverterGenerator
                .new(name, { attributes: { 'v' => type }, is_container: false }, {}, 'spec')
    code = generator.send(:converter_template)
    code = code.gsub(/require_relative '([^']+)'/) { "require '#{File.expand_path(Regexp.last_match(1), EXTENSIONS_NULL)}'" }
    eval(code, TOPLEVEL_BINDING, "#{name}_converter.rb") # rubocop:disable Security/Eval
    RjuiTools::React::Converters::Extensions.const_get("#{name}Converter")
  end

  # Built once for the group (the converters are classes; building them per
  # example redefines them, and Ruby says so on stderr under --warnings).
  before(:all) { @rows = build_rows }

  def rows
    @rows
  end

  # [type, the call, the converter's own lines on stderr, the component, i]
  # — only its `[rjui]` sentences: stderr also carries Ruby's warnings when
  # the suite runs with them on.
  def build_rows
    null_types.each_with_index.map do |type, i|
      name = "NullProbe#{i}"
      said = StringIO.new
      saved = $stderr
      call = begin
        $stderr = said
        converter_for(name, type).new({ 'type' => name, 'v' => nil }, {}).convert(0)
      ensure
        $stderr = saved
      end
      component = RjuiTools::React::Generators::ReactComponentGenerator
                  .new(name, { is_container: false, attributes: { 'v' => type } }, {}).send(:component_template)
      [type, call, said.string.lines.grep(/\A\[rjui\] /).join, component, i]
    end
  end

  it 'writes no null, and names the prop exactly for the types Swift declares non-optional' do
    aggregate_failures do
      rows.each do |type, call, said, _, i|
        expect(call).not_to include(' v='), "#{type}: #{call}"
        optional = JsonUIShared::AttributeTypes.swift_type(JsonUIShared::AttributeTypes.parse(type)).end_with?('?')
        if optional
          expect(said).to be_empty, "#{type}: #{said.inspect}"
        else
          expect(said).to include("[rjui] NullProbe#{i}.v: the layout's nil is not a #{type} literal"),
                          "#{type}: #{said.inspect}"
        end
      end
    end
    expect(rows.count { |_, _, said, _, _| !said.empty? }).to be >= 15
  end

  it 'type-checks each call against its component' do
    source = rows.map do |_, call, _, component, i|
      body = component.lines.reject { |l| l.start_with?('import React', 'export default') }.join
      "#{body}\nconst nullProbeHost#{i} = (\n#{call}\n);\n"
    end.join
    expect("import React from 'react';\n#{source}").to compile_as_typescript.with_ambient(REACT_NULL)
  end
end
