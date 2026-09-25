# frozen_string_literal: true

require 'json'
require 'set'
require 'tmpdir'
require 'core/logger'
require 'core/attribute_types'
require 'compose/generators/kotlin_component_generator'
require 'compose/generators/dynamic_component_generator'
require_relative '../../support/kotlin_compiler'

# Every attribute type `kjui g converter` understands, one prop each: the
# composable it scaffolds and the Dynamic wrapper that reads the prop,
# compiled together with kotlinc against the real Gson and a stub of Compose /
# KotlinJsonUI. The list is DERIVED from the shared vocabulary
# (lib/core/attribute_types.rb) — a type added there is compiled here — plus
# the shapes around it (`T?`, `[T]`, callbacks) and types outside it.
#
# Until 1.8.121, of 26 spellings compiled this way 17 did not compile: the
# composable declared `v: Any = null` for a Long, a callback, a `String?`, a
# data source…, and the wrapper read Dp / Alignment as text (2026-09-26).
# Ticket kjui-sjui-converter-attr-types-do-not-compile. sjui's and rjui's
# generators run the same list (attribute_types_compile_spec in each).
RSpec.describe 'kjui g converter and every attribute type' do
  before do
    %i[info debug warn success error].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
  end

  def types
    vocab = JsonUIShared::AttributeTypes::VOCABULARY.keys.reject { |k| k.include?('_') } +
            JsonUIShared::AttributeTypes::ALIASES.keys
    vocab + %w[String? Int? Long? Bool? Color? [String] [Int]? Array(Double) Array Object? (()\ ->\ Void)? ((String)\ ->\ Void)? Callback] +
      # outside the vocabulary: a model type the app declares, and one as a list
      %w[Date [AppRow] Array(AppSection) Dp Alignment]
  end

  def stub
    <<~KT
      package com.kotlinjsonui.dynamic
      import com.google.gson.JsonObject
      @Target(AnnotationTarget.FUNCTION, AnnotationTarget.TYPE, AnnotationTarget.TYPE_PARAMETER)
      annotation class Composable
      interface BoxScope
      object BoxScopeImpl : BoxScope
      open class Modifier { companion object : Modifier() }
      @Composable fun Box(modifier: Modifier = Modifier, content: @Composable BoxScope.() -> Unit) { BoxScopeImpl.content() }
      class Color { companion object { val Unspecified = Color() } }
      class Context
      object LocalContext { val current = Context() }
      object ModifierBuilder {
          fun buildModifier(json: JsonObject, data: Map<String, Any>, context: Context): Modifier = Modifier
          fun isBinding(s: String): Boolean = false
          fun extractBindingProperty(s: String): String? = null
      }
      object ResourceResolver { fun resolveText(json: JsonObject, key: String, data: Map<String, Any>, context: Context): String = "" }
      object ColorParser { fun parseColorWithBinding(json: JsonObject, key: String, data: Map<String, Any>, context: Context): Color? = null }
      class CollectionDataSource
      @Composable fun DynamicView(json: JsonObject, data: Map<String, Any>) {}
    KT
  end

  def body(kotlin)
    kotlin.lines.reject { |l| l =~ /\A\s*(package|import)\s/ || l =~ %r{\A\s*//} }.join
  end

  it 'derives its list from the shared vocabulary' do
    expect(types).to include('long', 'cgfloat', 'integer', 'boolean', 'number', 'collectiondatasource')
  end

  it 'compiles the composable and its wrapper for every type, and for the types outside the vocabulary' do
    source = Dir.mktmpdir('kjui_types') do |dir|
      Dir.chdir(dir) do
        File.write('kjui.config.json', JSON.generate('package_name' => 'probe'))
        types.each_with_index.map do |type, i|
          options = { is_container: nil, attributes: { 'v' => type } }
          body(KjuiTools::Compose::Generators::KotlinComponentGenerator.new("T#{i}", options).send(:kotlin_template)) +
            body(KjuiTools::Compose::Generators::DynamicComponentGenerator.new("T#{i}", options).send(:dynamic_template))
        end.join("\n")
      end
    end
    expect(stub + "\n" + source).to compile_as_kotlin(:gson)
  end

  it 'writes no `Any = null`, the shape that did not compile' do
    Dir.mktmpdir('kjui_types') do |dir|
      Dir.chdir(dir) do
        File.write('kjui.config.json', JSON.generate('package_name' => 'probe'))
        types.each do |type|
          kotlin = KjuiTools::Compose::Generators::KotlinComponentGenerator
                   .new('T', is_container: nil, attributes: { 'v' => type }).send(:kotlin_template)
          expect(kotlin).not_to match(/v: Any = null/), type
        end
      end
    end
  end
end
