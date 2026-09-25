# frozen_string_literal: true

require 'stringio'
require 'core/attribute_types'
require 'swiftui/generators/swift_component_generator'
require 'swiftui/generators/converter_generator'

# A literal a layout gives a custom component's prop, as the converter that
# `sjui g converter` writes renders it: every type in the shared vocabulary
# (lib/core/attribute_types.rb, the table the component scaffold is made
# from), its aliases, and `T?` / `[T]` around them — the converter's output
# typechecked with swiftc against the component scaffolded from the same
# attributes.
#
# Until 1.8.121 the converter kept its own spellings: a `String?` or `text`
# prop got its literal without quotes, a map got Ruby's `{"a"=>1}`, and a
# string with a quote in it closed the literal early. Ticket
# converter-literal-props-do-not-compile.
RSpec.describe 'sjui g converter: a literal the layout gives a prop' do
  EXTENSIONS = File.expand_path('../../../lib/swiftui/views/extensions', __dir__)

  before do
    %i[info debug warn success error].each { |m| allow(SjuiTools::Core::Logger).to receive(m) }
  end

  STRING = 'Say "hi" \\ $x \\(y)'

  # canonical type => the literal a layout gives it
  LITERALS = {
    'string' => STRING, 'int' => 3, 'long' => 5, 'float' => 1.5, 'double' => 2.25, 'cgfloat' => 1.5,
    'bool' => true, 'color' => '#FF8800', 'map' => { 'a' => 1, 'b' => 'x "y"', 'c' => [true, nil] }
  }.freeze

  # The vocabulary (a data source takes a binding, not a literal) and its
  # aliases, then the shapes around it — each with a literal.
  def props
    vocab = JsonUIShared::AttributeTypes::VOCABULARY.keys - ['collection_data_source']
    aliases = JsonUIShared::AttributeTypes::ALIASES.reject { |_, canonical| canonical == 'collection_data_source' }
    rows = vocab.map { |t| [t, LITERALS.fetch(t)] } + aliases.map { |a, canonical| [a, LITERALS.fetch(canonical)] }
    rows + [['String?', STRING], ['Int?', 7], ['Float?', 0.25], ['Bool?', false], ['Color?', '#00FF00'],
            ['Object?', { 'k' => 'v' }], ['[String]', ['a', 'b "q"']], ['[Int]?', [1, 2]], ['[Double]', [1, 2.5]],
            ['Array(Float)', [1, 0.5]], ['[Bool]', [true, false]]]
  end

  # The converter as `g converter` writes it, loaded as if it sat in the
  # extensions directory (its require_relative lines resolved from there).
  def converter_for(name, attributes)
    generator = SjuiTools::SwiftUI::Generators::ConverterGenerator.new(name, attributes: attributes)
    code = generator.send(:converter_template)
    code = code.gsub(/require_relative '([^']+)'/) { "require '#{File.expand_path(Regexp.last_match(1), EXTENSIONS)}'" }
    eval(code, TOPLEVEL_BINDING, "#{name}_converter.rb") # rubocop:disable Security/Eval
    SjuiTools::SwiftUI::Views::Extensions.const_get("#{name}Converter")
  end

  def emitted(name, attributes, component)
    converter_for(name, attributes).new(component, 0, nil, nil, nil, nil).convert
  end

  def plain(swift)
    swift.lines.reject { |l| l =~ /\A\s*(import |#if DEBUG|#endif)/ || l =~ %r{\A//} }.join
  end

  it 'derives its list from the shared vocabulary' do
    expect(props.map(&:first)).to include('long', 'cgfloat', 'integer', 'boolean', 'number', 'text', 'object')
  end

  it 'gives the component every literal the layout names, as Swift the scaffold typechecks against' do
    attributes = props.each_with_index.to_h { |(type, _), i| ["v#{i}", type] }
    component = props.each_with_index.to_h { |(_, value), i| ["v#{i}", value] }.merge('type' => 'LiteralProbe')
    call = emitted('LiteralProbe', attributes, component)
    scaffold = SjuiTools::SwiftUI::Generators::SwiftComponentGenerator
               .new('LiteralProbe', is_container: false, attributes: attributes, command: 'spec').send(:swift_template)
    aggregate_failures do
      # Every prop the layout names reaches the call — a `false` too.
      expect(call.scan(/^\s*v\d+: /).size).to eq(props.size), call
      expect(<<~SWIFT).to compile_as_swift
        #{plain(scaffold)}
        struct LiteralProbeHost: View {
            var body: some View {
        #{call}
            }
        }
      SWIFT
    end
  end

  it 'keeps a string literal whole: its quotes, backslashes and interpolation markers are escaped' do
    call = emitted('LiteralString', { 'v' => 'String' }, { 'type' => 'LiteralString', 'v' => STRING })
    expect(call).to include('v: "Say \\"hi\\" \\\\ $x \\\\(y)"')
  end

  # A JSON null the layout gives a prop. `nil` is written only where the
  # component the same attributes scaffold declares the prop optional — read
  # back from that Swift, not from the table the converter asks — and every
  # other prop gets nothing and a line naming it. Until 1.8.121 a `Row!!`
  # model (declared `Row`) got `nil`, which swiftc refuses, without a word.
  # Ticket converter-writes-nil-for-a-forced-model-prop.
  describe 'a JSON null' do
    def null_types
      JsonUIShared::AttributeTypes::VOCABULARY.keys + JsonUIShared::AttributeTypes::ALIASES.keys +
        ['String?', 'Int?', 'Object?', '[String]', '[Int]?', 'Array(Float)', 'Array', 'Row', 'Row?', 'Row!!',
         '[Row]', 'Callback', '(() -> Void)?']
    end

    # [type, what the scaffold declares, the call, what it said]
    def null_rows
      null_types.each_with_index.map do |type, i|
        name = "NullProbe#{i}"
        said = StringIO.new
        saved = $stderr
        call = begin
          $stderr = said
          emitted(name, { 'v' => type }, { 'type' => name, 'v' => nil })
        ensure
          $stderr = saved
        end
        scaffold = SjuiTools::SwiftUI::Generators::SwiftComponentGenerator
                   .new(name, is_container: false, attributes: { 'v' => type }, command: 'spec').send(:swift_template)
        [type, scaffold[/^\s*let v: (.+)$/, 1], call, said.string, scaffold]
      end
    end

    it 'writes nil only where the scaffold declares the prop optional, and names every other' do
      rows = null_rows
      expect(rows.map { |_, declared, *| declared }).to all(be_a(String))
      aggregate_failures do
        rows.each do |type, declared, call, said, _|
          optional = declared.end_with?('?')
          expect(call.match?(/^\s*v: nil,?$/)).to eq(optional), "#{type} (declared #{declared}): #{call}"
          next if optional

          expect(call).not_to match(/^\s*v: /), "#{type}: #{call}"
          expect(said).to include("the layout's nil is not a #{type} literal"), "#{type}: #{said.inspect}"
        end
      end
      # The table the converter asks answers the same for Swift, Kotlin and
      # TypeScript; here it is held to what Swift declares.
      expect(rows.map { |type, declared, *| [type, declared.end_with?('?')] })
        .to eq(rows.map { |type, *| [type, JsonUIShared::AttributeTypes.takes_null?(type)] })
    end

    it 'writes a nil that swiftc takes, wherever it writes one' do
      rows = null_rows.select { |_, _, call, *| call.match?(/^\s*v: nil,?$/) }
      source = +"struct Row { static var mock: Row { Row() } }\nclass CollectionDataSource {}\n"
      rows.each_with_index do |(_, _, call, _, scaffold), i|
        source << "#{plain(scaffold)}\nstruct NullHost#{i}: View {\n    var body: some View {\n#{call}\n    }\n}\n"
      end
      expect(rows.size).to be >= 10
      expect(source).to compile_as_swift
    end
  end
end
