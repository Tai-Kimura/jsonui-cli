# frozen_string_literal: true

require 'set'
require 'tmpdir'
require 'json'
require 'core/logger'
require 'compose/helpers/modifier_builder'
require 'compose/generators/converter_generator'
require 'compose/generators/kotlin_component_generator'
require 'compose/generators/dynamic_component_generator'
require_relative '../../support/kotlin_compiler'

# `kjui g converter` writes three files that must agree on whether the
# component takes a content lambda: the composable, the converter that calls
# it from generated views, and the Dynamic wrapper that calls it in Debug.
#
# Until 1.8.121 each read the mode its own way — the composable `!= false`,
# the wrapper truthy, the converter not at all — and two combinations did
# not compile (measured on e1a85ca2 with kotlinc): the default's wrapper
# called its composable without the content it required, and a --container
# or default converter with no children omitted the lambda. Ticket
# kjui-converter-scaffolds-disagree-on-content.
#
# Compiled, not read: the defect was three texts that each looked right.
RSpec.describe 'the three kjui converter scaffolds agree' do
  before do
    %i[info debug warn success error].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
  end

  # Enough of Compose and KotlinJsonUI for the generated calls to resolve,
  # in the package the wrapper names DynamicView by (fully qualified). The
  # leaf wrapper's refusal names android.util.Log, material3's Text and
  # Color fully qualified; one file holds one package, so those names are
  # shortened onto the stubs below (the real resolution is measured on a face
  # at KotlinJsonUI 2.41.1 and on conformance-host at 2.42.0).
  # A method, not a constant: a constant in a describe block is top-level.
  def stub
    <<~KT
    package com.kotlinjsonui.dynamic

    @Target(AnnotationTarget.FUNCTION, AnnotationTarget.TYPE, AnnotationTarget.TYPE_PARAMETER)
    annotation class Composable
    interface BoxScope
    object BoxScopeImpl : BoxScope
    open class Modifier { companion object : Modifier() }
    fun Modifier.testTag(tag: String): Modifier = this
    class SemanticsScope { var testTagsAsResourceId: Boolean = false }
    fun Modifier.semantics(block: SemanticsScope.() -> Unit): Modifier = this
    @Composable fun Box(modifier: Modifier = Modifier, content: @Composable BoxScope.() -> Unit) { BoxScopeImpl.content() }
    @Composable fun Text(text: String) {}
    class JsonElement {
        val isJsonObject = true; val isJsonArray = false; val isJsonPrimitive = false; val asString = ""
        val asJsonObject: JsonObject get() = JsonObject(); val asJsonArray: JsonArray get() = JsonArray()
    }
    class JsonArray : Iterable<JsonElement> { override fun iterator() = listOf<JsonElement>().iterator() }
    class JsonObject { fun get(key: String): JsonElement? = null; fun has(key: String): Boolean = false }
    class Context
    object LocalContext { val current = Context() }
    object ModifierBuilder { fun buildModifier(json: JsonObject, data: Map<String, Any>, context: Context): Modifier = Modifier }
    object ResourceResolver { fun resolveText(json: JsonObject, key: String, data: Map<String, Any>, context: Context): String = "" }
    @Composable fun DynamicView(json: JsonObject, data: Map<String, Any>) {}
    object Log { fun w(tag: String, message: String): Int = 0 }
    class Color { companion object { val Red = Color() } }
    @Composable fun Text(text: String, color: Color) {}
  KT
  end

  def modes
    { 'Shelf' => true, 'Auto' => nil, 'Leaf' => false }
  end

  def body(kotlin)
    kotlin.lines.reject { |l| l =~ /\A\s*(package|import)\s/ || l =~ %r{\A\s*//} }.join
  end

  # The composable, both converter calls and the wrapper for every mode, in
  # one compile — each name its own, so a failure names the mode.
  def sources
    Dir.mktmpdir('kjui_agree') do |dir|
      Dir.chdir(dir) do
        File.write('kjui.config.json', JSON.generate('package_name' => 'probe'))
        modes.map do |name, mode|
          options = { is_container: mode, attributes: { 'title' => 'String' } }
          composable = body(KjuiTools::Compose::Generators::KotlinComponentGenerator.new(name, options).send(:kotlin_template))
          wrapper = body(KjuiTools::Compose::Generators::DynamicComponentGenerator.new(name, options).send(:dynamic_template))
                    .gsub('android.util.Log', 'Log').gsub('androidx.compose.material3.Text', 'Text')
                    .gsub('androidx.compose.ui.graphics.Color', 'Color').gsub('com.google.gson.JsonElement', 'JsonElement')
          source = KjuiTools::Compose::Generators::ConverterGenerator.new(name, options).send(:converter_template)
                                                                   .gsub(/^\s*require_relative .*$/, '')
          eval(source, TOPLEVEL_BINDING, "#{name}_component.rb") # rubocop:disable Security/Eval
          klass = KjuiTools::Compose::Components::Extensions.const_get("#{name}Component")
          calls = [true, false].map do |kids|
            node = { 'type' => name, 'id' => "n_#{name.downcase}", 'title' => 'x' }
            node['child'] = [{ 'type' => 'Label', 'text' => 'Kid' }] if kids && mode != false
            out = klass.generate(node, 1, Set.new)
            code = out.is_a?(Hash) ? "#{out[:code]}#{"\n        Text(\"Kid\")" unless out[:children].to_a.empty?}#{out[:closing]}" : out
            "@Composable fun screen#{name}#{kids ? 'WithChild' : 'Alone'}() {\n#{code}\n}\n"
          end
          [composable, wrapper, *calls].join("\n")
        end.join("\n")
      end
    end
  end

  it 'compiles every mode: the composable, its converter with and without children, and its Dynamic wrapper' do
    expect(stub + "\n" + sources).to compile_as_kotlin
  end

  # The compiler's own control: the shape the default mode's wrapper had —
  # a call without the lambda its composable requires — is refused here.
  it 'is a check that can fail: kotlinc refuses a call without a required content lambda' do
    skip "kotlinc: #{KotlinCompiler.unavailable_reason}" if KotlinCompiler.unavailable_reason
    result = KotlinCompiler.compile(stub + <<~KT)
      @Composable fun Needs(modifier: Modifier = Modifier, content: @Composable BoxScope.() -> Unit) {}
      @Composable fun call() { Needs(modifier = Modifier) }
    KT
    expect(result.errors.join).to include("No value passed for parameter 'content'").or include("no value passed for parameter 'content'")
  end

  it 'reads the mode the same way in all three' do
    Dir.mktmpdir('kjui_agree') do |dir|
      Dir.chdir(dir) do
        File.write('kjui.config.json', JSON.generate('package_name' => 'probe'))
        takes = modes.to_h do |name, mode|
          options = { is_container: mode, attributes: {} }
          composable = KjuiTools::Compose::Generators::KotlinComponentGenerator.new(name, options).send(:kotlin_template)
          wrapper = KjuiTools::Compose::Generators::DynamicComponentGenerator.new(name, options).send(:dynamic_template)
          [name, [composable.include?('content:'), wrapper.include?('// Process children')]]
        end
        expect(takes).to eq('Shelf' => [true, true], 'Auto' => [true, true], 'Leaf' => [false, false])
      end
    end
  end
end
