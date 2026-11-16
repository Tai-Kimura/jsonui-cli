# frozen_string_literal: true

require 'json'
require 'set'
require 'tmpdir'
require 'core/logger'
require 'compose/generators/kotlin_component_generator'
require 'compose/generators/dynamic_component_generator'
require_relative '../../support/kotlin_compiler'

# `kjui g converter` with one prop of each scalar type: the composable it
# scaffolds and the Dynamic wrapper that reads the prop, compiled together
# with kotlinc against the real Gson and a stub of Compose / KotlinJsonUI.
#
# The wrapper passed `0.0` — a Double — as the default of resolveFloat, which
# takes a Float, so a component with a Float prop did not build in Debug
# (measured on a face's copy, 2026-09-25). Ticket
# kjui-dynamic-wrapper-float-default-is-a-double. Long and CGFloat scaffold a
# composable parameter `Any = null`, which is another shape and not here.
RSpec.describe 'the kjui Dynamic wrapper and a scalar prop' do
  before do
    %i[info debug warn success error].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
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
      class Context
      object LocalContext { val current = Context() }
      object ModifierBuilder {
          fun buildModifier(json: JsonObject, data: Map<String, Any>, context: Context): Modifier = Modifier
          fun isBinding(s: String): Boolean = false
          fun extractBindingProperty(s: String): String? = null
      }
      object ResourceResolver { fun resolveText(json: JsonObject, key: String, data: Map<String, Any>, context: Context): String = "" }
      @Composable fun DynamicView(json: JsonObject, data: Map<String, Any>) {}
    KT
  end

  def body(kotlin)
    kotlin.lines.reject { |l| l =~ /\A\s*(package|import)\s/ || l =~ %r{\A\s*//} }.join
  end

  it 'compiles a composable and its wrapper for Int, Double, Float, Bool and String props' do
    source = Dir.mktmpdir('kjui_props_gen') do |dir|
      Dir.chdir(dir) do
        File.write('kjui.config.json', JSON.generate('package_name' => 'probe'))
        %w[Int Double Float Bool String].map do |type|
          options = { is_container: nil, attributes: { 'v' => type } }
          name = "Prop#{type}"
          body(KjuiTools::Compose::Generators::KotlinComponentGenerator.new(name, options).send(:kotlin_template)) +
            body(KjuiTools::Compose::Generators::DynamicComponentGenerator.new(name, options).send(:dynamic_template))
        end.join("\n")
      end
    end
    expect(stub + "\n" + source).to compile_as_kotlin(:gson)
  end
end
