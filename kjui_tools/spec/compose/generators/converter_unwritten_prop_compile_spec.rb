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

# A prop the converter does not write — the layout leaves it out, gives it
# null, or gives a value of the wrong kind — as the call `kjui g converter`'s
# converter writes it, compiled with kotlinc against the composable
# scaffolded from the same attribute (types only; Compose is a stub).
#
# The composable declares a default for every parameter, so these calls
# compile and the prop keeps it — what the converter now says, naming the
# value. Until 1.8.121 it said "the prop keeps its default" on all three
# tools, which on sjui was false (ticket
# sjui-unwritten-non-optional-prop-does-not-compile); the sentence is one,
# from lib/core/attribute_types.rb, and says what happens on each face.
RSpec.describe 'kjui g converter: a prop the converter does not write' do
  EXT_UNWRITTEN_K = File.expand_path('../../../lib/compose/components/extensions', __dir__)

  before do
    %i[info debug warn success error].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
  end

  STUB_UNWRITTEN = <<~KT
    @Target(AnnotationTarget.FUNCTION, AnnotationTarget.TYPE, AnnotationTarget.TYPE_PARAMETER)
    annotation class Composable
    interface BoxScope
    object BoxScopeImpl : BoxScope
    open class Modifier { companion object : Modifier() }
    @Composable fun Box(modifier: Modifier = Modifier, content: @Composable BoxScope.() -> Unit) { BoxScopeImpl.content() }
    class Color(val argb: Int = 0) { companion object { val Unspecified = Color() } }
    class CollectionDataSource
  KT

  def types
    JsonUIShared::AttributeTypes::VOCABULARY.keys + JsonUIShared::AttributeTypes::ALIASES.keys +
      ['String?', 'Int?', 'Object?', '[String]', '[Int]?', 'Array(Float)', 'Array', 'Row', 'Row?', 'Row!!',
       '[Row]', 'Callback', '(() -> Void)?']
  end

  def value_for(type, kase)
    return nil if kase == :null

    JsonUIShared::AttributeTypes.parse(type).canonical == 'map' ? 5 : { 'not' => 'this type' }
  end

  def converter_for(name, attributes)
    code = KjuiTools::Compose::Generators::ConverterGenerator.new(name, { attributes: attributes }).send(:converter_template)
    code = code.gsub(/require_relative '([^']+)'/) { "require '#{File.expand_path(Regexp.last_match(1), EXT_UNWRITTEN_K)}'" }
    eval(code, TOPLEVEL_BINDING, "#{name}_component.rb") # rubocop:disable Security/Eval
    KjuiTools::Compose::Components::Extensions.const_get("#{name}Component")
  end

  # [type, case, the call, what it said, the composable]
  def rows
    @rows ||= Dir.mktmpdir('kjui_unwritten') do |dir|
      Dir.chdir(dir) do
        File.write('kjui.config.json', JSON.generate('package_name' => 'probe'))
        types.each_with_index.flat_map do |type, i|
          %i[absent null wrong].map do |kase|
            name = "Unwritten#{kase.to_s.capitalize}#{i}"
            node = { 'type' => name }
            node['v'] = value_for(type, kase) unless kase == :absent
            said = StringIO.new
            saved = $stderr
            call = begin
              $stderr = said
              converter_for(name, 'v' => type).generate(node, 0, Set.new)
            ensure
              $stderr = saved
            end
            composable = KjuiTools::Compose::Generators::KotlinComponentGenerator
                         .new(name, { is_container: false, attributes: { 'v' => type } }).send(:kotlin_template)
            [type, kase, call, said.string, composable]
          end
        end
      end
    end
  end

  def body(kotlin)
    kotlin.lines.reject { |l| l =~ /\A\s*(package|import)\s/ || l =~ %r{\A\s*//} }.join
  end

  it 'compiles every call without the prop' do
    source = rows.each_with_index.map do |(_, _, call, _, composable), i|
      "#{body(composable)}\n@Composable fun unwrittenHost#{i}() {\n#{call}\n}\n"
    end.join
    expect(rows.size).to be >= 90
    expect("#{STUB_UNWRITTEN}\n#{source}").to compile_as_kotlin
  end

  it 'names the default the composable declares, for every prop it does not write' do
    aggregate_failures do
      rows.each do |type, kase, call, said, composable|
        next if kase == :absent || call.match?(/^\s*v = /)

        declared = composable[/^\s*v: [^=]+ = (.+),$/, 1]
        expect(declared).not_to be_nil, "#{type}: #{composable}"
        expect(said).to include("the prop keeps its default (#{declared})"), "#{type} #{kase}: #{said.inspect}"
      end
    end
  end
end
