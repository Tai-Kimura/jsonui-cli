# frozen_string_literal: true

require 'json'
require 'set'
require 'stringio'
require 'tmpdir'
require 'core/logger'
require 'core/attribute_types'
require 'compose/generators/kotlin_component_generator'
require 'compose/generators/converter_generator'
require_relative '../../support/kotlin_compiler'

# A literal a layout gives a custom component's prop, as the converter that
# `kjui g converter` writes renders it: every type in the shared vocabulary
# (lib/core/attribute_types.rb, the table the composable scaffold is made
# from), its aliases, and `T?` / `[T]` around them — the converter's output
# compiled with kotlinc against the composable scaffolded from the same
# attributes (types only; Compose is a stub).
#
# Until 1.8.121 the converter kept its own spellings: a `Float` got `1.5`
# (Kotlin wants `1.5f`), a list got Ruby's `["a", "b"]`, a map `{"a"=>1}`, a
# `String?` its text without quotes, and a string with a `$` became a
# template. Ticket converter-literal-props-do-not-compile.
RSpec.describe 'kjui g converter: a literal the layout gives a prop' do
  EXTENSIONS = File.expand_path('../../../lib/compose/components/extensions', __dir__)

  before do
    %i[info debug warn success error].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
  end

  STRING = 'Say "hi" \\ $x ${y}'

  # canonical type => the literal a layout gives it
  LITERALS = {
    'string' => STRING, 'int' => 3, 'long' => 5, 'float' => 1.5, 'double' => 2, 'cgfloat' => 1,
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
    generator = KjuiTools::Compose::Generators::ConverterGenerator.new(name, { attributes: attributes })
    code = generator.send(:converter_template)
    code = code.gsub(/require_relative '([^']+)'/) { "require '#{File.expand_path(Regexp.last_match(1), EXTENSIONS)}'" }
    eval(code, TOPLEVEL_BINDING, "#{name}_component.rb") # rubocop:disable Security/Eval
    KjuiTools::Compose::Components::Extensions.const_get("#{name}Component")
  end

  def in_project
    Dir.mktmpdir('kjui_literals') do |dir|
      Dir.chdir(dir) do
        File.write('kjui.config.json', JSON.generate('package_name' => 'probe'))
        yield
      end
    end
  end

  def emitted(name, attributes, component)
    in_project { converter_for(name, attributes).generate(component, 0, Set.new) }
  end

  def body(kotlin)
    kotlin.lines.reject { |l| l =~ /\A\s*(package|import)\s/ || l =~ %r{\A\s*//} }.join
  end

  STUB = <<~KT
    @Target(AnnotationTarget.FUNCTION, AnnotationTarget.TYPE, AnnotationTarget.TYPE_PARAMETER)
    annotation class Composable
    interface BoxScope
    object BoxScopeImpl : BoxScope
    open class Modifier { companion object : Modifier() }
    @Composable fun Box(modifier: Modifier = Modifier, content: @Composable BoxScope.() -> Unit) { BoxScopeImpl.content() }
    class Color(val argb: Int = 0) { companion object { val Unspecified = Color() } }
    object android { object graphics { object Color { fun parseColor(hex: String): Int = 0 } } }
    class CollectionDataSource
  KT

  it 'derives its list from the shared vocabulary' do
    expect(props.map(&:first)).to include('long', 'cgfloat', 'integer', 'boolean', 'number', 'text', 'object')
  end

  it 'gives the composable every literal the layout names, as Kotlin the scaffold compiles against' do
    attributes = props.each_with_index.to_h { |(type, _), i| ["v#{i}", type] }
    component = props.each_with_index.to_h { |(_, value), i| ["v#{i}", value] }.merge('type' => 'LiteralProbe')
    call = emitted('LiteralProbe', attributes, component)
    scaffold = in_project do
      KjuiTools::Compose::Generators::KotlinComponentGenerator
        .new('LiteralProbe', { is_container: false, attributes: attributes }).send(:kotlin_template)
    end
    aggregate_failures do
      # Every prop the layout names reaches the call — a `false` too.
      expect(call.scan(/^\s*v\d+ = /).size).to eq(props.size), call
      expect(<<~KT).to compile_as_kotlin
        #{STUB}
        #{body(scaffold)}
        @Composable fun literalProbeHost() {
        #{call}
        }
      KT
    end
  end

  it 'keeps a string literal whole: its quotes, backslashes and templates are escaped' do
    call = emitted('LiteralString', { 'v' => 'String' }, { 'type' => 'LiteralString', 'v' => STRING })
    expect(call).to include('v = "Say \\"hi\\" \\\\ \\$x \\${y}"')
  end

  # A JSON null the layout gives a prop. `null` is written only for a type
  # every tool writes a null for — the ones sjui's Swift scaffold declares
  # optional (the shared table's swift_type, the declaration, not the
  # question the converter asks) — and every other prop gets nothing and a
  # line naming it; the composable's default stands. Until 1.8.121 a `Row!!`
  # model got `null` here without a word while sjui refused it. Ticket
  # converter-writes-nil-for-a-forced-model-prop.
  describe 'a JSON null' do
    def null_types
      JsonUIShared::AttributeTypes::VOCABULARY.keys + JsonUIShared::AttributeTypes::ALIASES.keys +
        ['String?', 'Int?', 'Object?', '[String]', '[Int]?', 'Array(Float)', 'Array', 'Row', 'Row?', 'Row!!',
         '[Row]', 'Callback', '(() -> Void)?']
    end

    it 'writes null only where Swift declares the prop optional, names every other, and compiles each call' do
      rows = null_types.each_with_index.map do |type, i|
        name = "NullProbe#{i}"
        said = StringIO.new
        saved = $stderr
        call = begin
          $stderr = said
          emitted(name, { 'v' => type }, { 'type' => name, 'v' => nil })
        ensure
          $stderr = saved
        end
        scaffold = in_project do
          KjuiTools::Compose::Generators::KotlinComponentGenerator
            .new(name, { is_container: false, attributes: { 'v' => type } }).send(:kotlin_template)
        end
        [type, call, said.string, scaffold, i]
      end
      aggregate_failures do
        rows.each do |type, call, said, _, _|
          optional = JsonUIShared::AttributeTypes.swift_type(JsonUIShared::AttributeTypes.parse(type)).end_with?('?')
          expect(call.match?(/^\s*v = null,?$/)).to eq(optional), "#{type}: #{call}"
          next if optional

          expect(call).not_to match(/^\s*v = /), "#{type}: #{call}"
          expect(said).to include("the layout's nil is not a #{type} literal"), "#{type}: #{said.inspect}"
        end
      end
      source = rows.map do |_, call, _, scaffold, i|
        "#{body(scaffold)}\n@Composable fun nullProbeHost#{i}() {\n#{call}\n}\n"
      end.join
      expect("#{STUB}\n#{source}").to compile_as_kotlin
    end
  end
end
