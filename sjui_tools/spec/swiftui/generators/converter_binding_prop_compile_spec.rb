# frozen_string_literal: true

require 'stringio'
require 'core/attribute_types'
require 'swiftui/generators/swift_component_generator'
require 'swiftui/generators/converter_generator'

# A binding prop (`@v:T`) as the converter `sjui g converter` writes it for
# each thing a layout can give it — a binding `@{v}`, a literal of its type, a
# value of another kind, null, nothing — typechecked with swiftc against the
# component scaffolded from the same attribute, in a host whose data has `v`.
#
# Until 1.8.121 (measured on 32785ce8, 2026-09-26) every value that was not
# `@{…}` was read as a property name: `$data.Hi`, `$data.3`,
# `$data.{"a"=>1}` — 21 of 50 calls did not compile — and a `false` or null
# was dropped without a word. Now a value that is not a binding is a literal
# of the prop's type held in a constant binding, `.constant(…)` — what the
# Dynamic adapter does with it — or, when it is not one, it is named and the
# parameter keeps its default. Ticket
# binding-prop-with-a-non-binding-value-does-not-compile.
RSpec.describe 'sjui g converter: a binding prop and what the layout gives it' do
  EXT_BINDING = File.expand_path('../../../lib/swiftui/views/extensions', __dir__)

  before do
    %i[info debug warn success error].each { |m| allow(SjuiTools::Core::Logger).to receive(m) }
  end

  # type => [a literal of it, a value of another kind]
  def self.values
    {
      'String' => ['Hi "q"', 5], 'Int' => [3, 'abc'], 'Bool' => [false, 'yes'], 'Double' => [2.5, 'x'],
      'Color' => ['#FF8800', 5], 'Object' => [{ 'a' => 1 }, 'x'], '[String]' => [%w[a b], 'x'],
      'String?' => ['Hi', 5], 'Row' => [{ 'k' => 'v' }, 'x'], 'Row!!' => [{ 'k' => 'v' }, 'x']
    }
  end

  def converter_for(name, type)
    code = SjuiTools::SwiftUI::Generators::ConverterGenerator.new(name, attributes: { '@v' => type }).send(:converter_template)
    code = code.gsub(/require_relative '([^']+)'/) { "require '#{File.expand_path(Regexp.last_match(1), EXT_BINDING)}'" }
    eval(code, TOPLEVEL_BINDING, "#{name}_converter.rb") # rubocop:disable Security/Eval
    SjuiTools::SwiftUI::Views::Extensions.const_get("#{name}Converter")
  end

  def plain(swift)
    swift.lines.reject { |l| l =~ /\A\s*(import |#if DEBUG|#endif)/ || l =~ %r{\A//} }.join
  end

  # [type, case, the call, what it said, the host source]
  def rows
    @rows ||= self.class.values.each_with_index.flat_map do |(type, (literal, wrong)), i|
      { binding: '@{v}', literal: literal, false: false, wrong: wrong, null: nil, absent: :absent }.map do |kase, value|
        name = "BindingProp#{kase.to_s.capitalize}#{i}"
        node = { 'type' => name }
        node['v'] = value unless kase == :absent
        # What it printed through sjui's warning logger (not stubbed for
        # this; stdout captured) — from 1.8.121 the line goes there,
        # "WARNING: [sjui] …", not to stderr through a bare `warn`.
        said = StringIO.new
        saved = $stdout
        call = begin
          allow(SjuiTools::Core::Logger).to receive(:warn).and_call_original
          $stdout = said
          converter_for(name, type).new(node, 0, nil, nil, nil, nil).convert
        ensure
          $stdout = saved
        end
        t = JsonUIShared::AttributeTypes.parse(type)
        swift = JsonUIShared::AttributeTypes.swift_type(t)
        init = swift.end_with?('?') ? 'nil' : (JsonUIShared::AttributeTypes.swift_default(t) || 'Row()')
        scaffold = SjuiTools::SwiftUI::Generators::SwiftComponentGenerator
                   .new(name, is_container: false, attributes: { '@v' => type }, command: 'spec').send(:swift_template)
        host = "#{plain(scaffold)}\nstruct #{name}Holder { var v: #{swift} = #{init} }\n" \
               "struct #{name}Host: View {\n    @State var data = #{name}Holder()\n    var body: some View {\n#{call}\n    }\n}\n"
        [type, kase, call, said.string, host]
      end
    end
  end

  it 'typechecks every call, except where a `T!!` model is not given a binding (it has no default)' do
    compiling = rows.reject { |type, kase, *| type.end_with?('!!') && kase != :binding }
    expect(compiling.size).to be >= 50
    expect("struct Row { static var mock: Row { Row() } }\n#{compiling.map(&:last).join}").to compile_as_swift
  end

  it 'holds a literal of the type in a constant binding — a false too — and never reads a value as a property name' do
    aggregate_failures do
      rows.each do |type, kase, call, _, _|
        next if kase == :binding

        expect(call).not_to match(/v: \$data\.(?!v\b)/), "#{type} #{kase}: #{call}"
        written = JsonUIShared::AttributeTypes.swift_literal(type, self.class.values[type][0]) { |c, _| 'x' if c == 'color' }
        expect(call).to match(/^\s*v: \.constant\(/), "#{type}: #{call}" if kase == :literal && written
        expect(call).to include('v: .constant(false)'), call if kase == :false && type == 'Bool'
      end
    end
  end

  it 'names a value it does not write, in the sentence the three tools share' do
    aggregate_failures do
      rows.each do |type, kase, call, said, _|
        next if %i[binding absent].include?(kase) || call.match?(/^\s*v: /)

        expect(said).to(include('is not a').and(include('literal this converter can write')), "#{type} #{kase}: #{call}")
      end
    end
  end
end
