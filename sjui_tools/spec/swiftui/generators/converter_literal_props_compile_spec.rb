# frozen_string_literal: true

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
end
