# frozen_string_literal: true

require 'stringio'
require 'core/attribute_types'
require 'swiftui/generators/swift_component_generator'
require 'swiftui/generators/converter_generator'

# A prop the converter does not write — the layout leaves it out, gives it
# null, or gives a value of the wrong kind — as the call `sjui g converter`'s
# converter writes it, typechecked with swiftc against the component
# scaffolded from the same attribute.
#
# Until 1.8.121 (measured on 1b80b5ba + the literal-null fix, 2026-09-26) the
# component's init declared a default only for optional parameters, so every
# such call for a non-optional prop — `String` as `Row!!`, 21 of 31 types —
# failed with "missing argument for parameter 'v'", while the converter said
# "the prop keeps its default". Now every parameter declares the default the
# vocabulary gives it (nil, or the value the Dynamic adapter falls back to),
# the call compiles and the prop keeps it; a `T!!` model has none, and the
# converter says the call does not compile — also when the layout leaves the
# prop out. Ticket sjui-unwritten-non-optional-prop-does-not-compile.
RSpec.describe 'sjui g converter: a prop the converter does not write' do
  EXT_UNWRITTEN = File.expand_path('../../../lib/swiftui/views/extensions', __dir__)

  before do
    %i[info debug warn success error].each { |m| allow(SjuiTools::Core::Logger).to receive(m) }
  end

  def types
    JsonUIShared::AttributeTypes::VOCABULARY.keys + JsonUIShared::AttributeTypes::ALIASES.keys +
      ['String?', 'Int?', 'Object?', '[String]', '[Int]?', 'Array(Float)', 'Array', 'Row', 'Row?', 'Row!!',
       '[Row]', 'Callback', '(() -> Void)?', '@String', '@Int', '@Row!!']
  end

  # What the layout gives in each case (absent: no key). The wrong kind is
  # an object, or a number for a map (which takes an object).
  def value_for(type, kase)
    return nil if kase == :null

    JsonUIShared::AttributeTypes.parse(type).canonical == 'map' ? 5 : { 'not' => 'this type' }
  end

  # A binding takes any value it is given as a property name (the layout's
  # `"v": "x"` becomes `$data.x`), so for a binding only the case where the
  # layout gives nothing is the converter's to settle here.
  def cases_for(spelled)
    spelled.start_with?('@') ? %i[absent] : %i[absent null wrong]
  end

  def converter_for(name, attributes)
    code = SjuiTools::SwiftUI::Generators::ConverterGenerator.new(name, attributes: attributes).send(:converter_template)
    code = code.gsub(/require_relative '([^']+)'/) { "require '#{File.expand_path(Regexp.last_match(1), EXT_UNWRITTEN)}'" }
    eval(code, TOPLEVEL_BINDING, "#{name}_converter.rb") # rubocop:disable Security/Eval
    SjuiTools::SwiftUI::Views::Extensions.const_get("#{name}Converter")
  end

  def plain(swift)
    swift.lines.reject { |l| l =~ /\A\s*(import |#if DEBUG|#endif)/ || l =~ %r{\A//} }.join
  end

  # [type, case, the call, what it said, the scaffold, name]
  def rows
    @rows ||= types.each_with_index.flat_map do |spelled, i|
      binding = spelled.start_with?('@')
      type = spelled.delete_prefix('@')
      key = binding ? '@v' : 'v'
      cases_for(spelled).map do |kase|
        name = "Unwritten#{kase.to_s.capitalize}#{i}"
        node = { 'type' => name }
        node['v'] = value_for(type, kase) unless kase == :absent
        said = StringIO.new
        saved = $stderr
        call = begin
          $stderr = said
          converter_for(name, key => type).new(node, 0, nil, nil, nil, nil).convert
        ensure
          $stderr = saved
        end
        scaffold = SjuiTools::SwiftUI::Generators::SwiftComponentGenerator
                   .new(name, is_container: false, attributes: { key => type }, command: 'spec').send(:swift_template)
        [spelled, kase, call, said.string, scaffold, name]
      end
    end
  end

  # The one kind of type the vocabulary gives no default: a model the app
  # declares, marked `!!` (non-optional). Read from the spelling, not from
  # the table the generators ask.
  def required?(spelled)
    spelled.end_with?('!!')
  end

  it 'compiles every call without the prop, except for a type Swift has no default for' do
    compiling = rows.reject { |spelled, *| required?(spelled) }
    source = +"struct Row { static var mock: Row { Row() } }\nclass CollectionDataSource {}\n"
    compiling.each do |_, _, call, _, scaffold, name|
      # A binding the layout does not give is not passed: the call is the
      # component's own init with its defaults.
      source << "#{plain(scaffold)}\nstruct #{name}Host: View {\n    var body: some View {\n#{call}\n    }\n}\n"
    end
    expect(compiling.size).to be >= 80
    expect(source).to compile_as_swift
  end

  it 'says the call does not compile for a type Swift has no default for — left out, null, or not a literal' do
    required = rows.select { |spelled, *| required?(spelled) }
    expect(required.map(&:first).uniq).to contain_exactly('Row!!', '@Row!!')
    aggregate_failures do
      required.each do |spelled, kase, call, said, _, _|
        expect(call).not_to match(/^\s*v: /), "#{spelled} #{kase}: #{call}"
        expect(said).to include('Row!! has no default in Swift, so the call does not compile'),
                        "#{spelled} #{kase}: #{said.inspect}"
      end
    end
  end

  it 'names the default the scaffold declares, for every non-optional type it does not write' do
    aggregate_failures do
      rows.each do |spelled, kase, _, said, scaffold, _|
        next if spelled.start_with?('@') || kase == :absent || required?(spelled)
        next if JsonUIShared::AttributeTypes.takes_null?(spelled) # nil is written for these

        declared = scaffold[/^\s*init\(v: [^=]+ = (.+?)\) \{$/, 1]
        expect(declared).not_to be_nil, "#{spelled}: #{scaffold[/init\(.*$/]}"
        expect(said).to include("the prop keeps its default (#{declared}), which the component declares"),
                        "#{spelled} #{kase}: #{said.inspect}"
      end
    end
  end
end
