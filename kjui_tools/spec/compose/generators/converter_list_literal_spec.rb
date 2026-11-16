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

# A list literal the layout gives a custom component's prop, as the converter
# `kjui g converter` writes it: each item by the rule a scalar of the item's
# type follows. A type outside the vocabulary (a model the app declares) or a
# callback takes no literal as a scalar, so it takes none as a list item
# either — as in Swift; a bare `Array`'s items are any value, and a nested
# list is a list. Compiled with kotlinc against the composable.
#
# Until 1.9.0 (measured on 32785ce8, 2026-09-26) every item that was not a
# vocabulary scalar went out as JSON, so `[Row]` was written
# (`listOf(mapOf<String, Any?>("k" to "v"))`) while `Row` was refused. Ticket
# binding-prop-with-a-non-binding-value-does-not-compile.
RSpec.describe 'kjui g converter: a list literal and the rule its items follow' do
  EXT_LIST = File.expand_path('../../../lib/compose/components/extensions', __dir__)

  STUB_LIST = <<~KT
    @Target(AnnotationTarget.FUNCTION, AnnotationTarget.TYPE, AnnotationTarget.TYPE_PARAMETER)
    annotation class Composable
    interface BoxScope
    object BoxScopeImpl : BoxScope
    open class Modifier { companion object : Modifier() }
    @Composable fun Box(modifier: Modifier = Modifier, content: @Composable BoxScope.() -> Unit) { BoxScopeImpl.content() }
    class Color(val argb: Int = 0) { companion object { val Unspecified = Color() } }
  KT

  before do
    %i[info debug warn success error].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
  end

  # type => a list value
  def self.values
    {
      '[Row]' => [{ 'k' => 'v' }], '[Callback]' => ['x'], '[String]' => ['a', 'b "q"'], '[Int]' => [1, 2],
      '[[Int]]' => [[1], [2, 3]], 'Array' => [1, 'a', nil], '[Object]' => [{ 'a' => 1 }], '[Row]?' => [{ 'k' => 'v' }]
    }
  end

  def converter_for(name, type)
    code = KjuiTools::Compose::Generators::ConverterGenerator.new(name, { attributes: { 'v' => type } }).send(:converter_template)
    code = code.gsub(/require_relative '([^']+)'/) { "require '#{File.expand_path(Regexp.last_match(1), EXT_LIST)}'" }
    eval(code, TOPLEVEL_BINDING, "#{name}_component.rb") # rubocop:disable Security/Eval
    KjuiTools::Compose::Components::Extensions.const_get("#{name}Component")
  end

  def rows
    @rows ||= Dir.mktmpdir('kjui_list') do |dir|
      Dir.chdir(dir) do
        File.write('kjui.config.json', JSON.generate('package_name' => 'probe'))
        self.class.values.each_with_index.map do |(type, value), i|
          name = "ListLiteral#{i}"
          # What it printed through kjui's warning logger (not stubbed for
          # this; stdout captured) — from 1.9.0 the line goes there,
          # "⚠️  [kjui] …", not to stderr through a bare `warn`.
          said = StringIO.new
          saved = $stdout
          call = begin
            allow(KjuiTools::Core::Logger).to receive(:warn).and_call_original
            $stdout = said
            converter_for(name, type).generate({ 'type' => name, 'v' => value }, 0, Set.new)
          ensure
            $stdout = saved
          end
          composable = KjuiTools::Compose::Generators::KotlinComponentGenerator
                       .new(name, { is_container: false, attributes: { 'v' => type } }).send(:kotlin_template)
          [type, value, call, said.string, composable, i]
        end
      end
    end
  end

  it 'writes a list exactly when Swift writes it — the item rule of the scalars' do
    aggregate_failures do
      rows.each do |type, value, call, said, _, _|
        swift = !JsonUIShared::AttributeTypes.swift_literal(type, value).nil?
        expect(call.match?(/^\s*v = /)).to eq(swift), "#{type}: #{call}"
        expect(said).to include("is not a #{type} literal") unless swift
      end
    end
    expect(rows.find { |type, *| type == '[Row]' }[2]).not_to include('v = ')
  end

  it 'compiles every call with kotlinc' do
    source = rows.map do |_, _, call, _, composable, i|
      body = composable.lines.reject { |l| l =~ /\A\s*(package|import)\s/ || l =~ %r{\A\s*//} }.join
      "#{body}\n@Composable fun listLiteralHost#{i}() {\n#{call}\n}\n"
    end.join
    expect("#{STUB_LIST}\n#{source}").to compile_as_kotlin
  end
end
