# frozen_string_literal: true

require 'set'
require 'compose/helpers/resource_resolver'
require 'compose/helpers/binding_expression'
require 'compose/compose_builder'
require 'compose/data_model_updater'
require_relative '../support/kotlin_compiler'

# kjui-object-path-binding-does-not-compile: a field of a data item declared
# as a JSON container (Object / Hash — the Data class holds it as
# Map<String, Any?>?) bound as `@{obj.name}` was written `data.obj.name`, and
# the generated updateData cast the item `value as? Object`. Neither compiles
# (measured: conformance Label/text__binding_unresolved_path, kotlinc
# "Unresolved reference 'name'" and "Argument type mismatch"). The path now
# reads the map field by field, and updateData casts to the Data field's type.
# The arm RUNS the emitted text expression on the JVM.
RSpec.describe 'kjui codegen: a path into an Object data item' do
  OBJECT_PATH_EXPR = KjuiTools::Compose::Helpers::BindingExpression unless defined?(OBJECT_PATH_EXPR)

  around do |example|
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
      'obj' => { 'name' => 'obj', 'class' => 'Object' },
      'items' => { 'name' => 'items', 'class' => 'Array' },
      'user' => { 'name' => 'user', 'class' => 'UserDto' }
    }
    example.run
  ensure
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  it 'reads the map field by field in text' do
    expect(OBJECT_PATH_EXPR.interpolated_access('obj.name')).to eq('"${data.obj?.get("name") ?: ""}"')
    expect(OBJECT_PATH_EXPR.interpolated_access('obj.a.b')).to eq('"${(data.obj?.get("a") as? Map<*, *>)?.get("b") ?: ""}"')
  end

  it 'reads a list by index, and an element as a map' do
    expect(OBJECT_PATH_EXPR.interpolated_access('items[1]')).to eq('"${data.items?.getOrNull(1) ?: ""}"')
    expect(OBJECT_PATH_EXPR.interpolated_access('items[0].title')).to eq('"${(data.items?.getOrNull(0) as? Map<*, *>)?.get("title") ?: ""}"')
  end

  it 'leaves a model type path as property access (control)' do
    expect(OBJECT_PATH_EXPR.interpolated_access('user.name')).to eq('"${data.user.name ?: ""}"')
  end

  it 'reads "" for an absent item or field and the value for a present one, when run' do
    skip "compile: #{KotlinCompiler.unavailable_reason}" if KotlinCompiler.unavailable_reason

    source = <<~KT
      class Data(val obj: Map<String, Any?>? = null, val items: List<Any?>? = null)
      fun name(data: Data): String = #{OBJECT_PATH_EXPR.interpolated_access('obj.name')}
      fun deep(data: Data): String = #{OBJECT_PATH_EXPR.interpolated_access('obj.a.b')}
      fun first(data: Data): String = #{OBJECT_PATH_EXPR.interpolated_access('items[0].title')}
      fun second(data: Data): String = #{OBJECT_PATH_EXPR.interpolated_access('items[1]')}
      fun main() {
          println("absent=[" + name(Data()) + "]")
          println("field-absent=[" + name(Data(mapOf("other" to 1))) + "]")
          println("present=[" + name(Data(mapOf("name" to "Ann"))) + "]")
          println("deep=[" + deep(Data(mapOf("a" to mapOf("b" to 3)))) + "]")
          println("deep-absent=[" + deep(Data(mapOf("a" to "not a map"))) + "]")
          println("first=[" + first(Data(items = listOf(mapOf("title" to "First")))) + "]")
          println("second=[" + second(Data(items = listOf("alpha", "beta"))) + "]")
          println("out-of-range=[" + second(Data(items = listOf("alpha"))) + "]")
      }
    KT
    run = KotlinCompiler.run(source)
    expect(run.errors).to eq([])
    expect(run.output.lines.map(&:strip)).to eq(
      ['absent=[]', 'field-absent=[]', 'present=[Ann]', 'deep=[3]', 'deep-absent=[]',
       'first=[First]', 'second=[beta]', 'out-of-range=[]']
    )
  end

  it 'casts an Object / Hash / Array item in updateData to the Data field type, which compiles' do
    builder = KjuiTools::Compose::ComposeBuilder.allocate
    builder.instance_variable_set(:@mode, 'compose')
    casts = { 'obj' => 'Object', 'meta' => 'Hash', 'rows' => 'Array' }.to_h { |n, c| [n, builder.send(:get_kotlin_cast, c, n)] }
    # Through 1.9.5: value as? Object / Hash / Array.
    expect(casts['obj']).to eq('value as? Map<String, Any?> ?: updated.obj')
    expect(casts['rows']).to eq('value as? List<Any?> ?: updated.rows')
    expect(<<~KT).to compile_as_kotlin
      data class Data(val obj: Map<String, Any?>? = null, val meta: Map<String, Any?>? = null, val rows: List<Any?>? = null)
      @Suppress("UNCHECKED_CAST")
      fun apply(updated: Data, key: String, value: Any): Data = when (key) {
          "obj" -> updated.copy(obj = #{casts['obj']})
          "meta" -> updated.copy(meta = #{casts['meta']})
          "rows" -> updated.copy(rows = #{casts['rows']})
          else -> updated
      }
    KT
  end

  # The Data class: an Object / Array item with a defaultValue is a non-null
  # field, and fromMap wrote a nullable cast with no fallback into it.
  it 'reads an Object / Array item in fromMap with its default behind it, which compiles' do
    updater = KjuiTools::Compose::DataModelUpdater.allocate
    props = [
      { 'name' => 'profile', 'class' => 'Object', 'defaultValue' => { 'name' => 'Grace' } },
      { 'name' => 'items', 'class' => 'Array', 'defaultValue' => ['a'] },
      { 'name' => 'loose', 'class' => 'Object' }
    ]
    text = updater.send(:generate_data_content, 'Probe', props, [])
    expect(text).to include('profile = map["profile"] as? Map<String, Any?> ?: mapOf("name" to "Grace")')
    expect(text).to include('items = map["items"] as? List<Any?> ?: listOf("a")')
    model = text.lines.reject { |l| l.start_with?('package ') }.join
    expect(model).to compile_as_kotlin
  ensure
    KjuiTools::Core::TypeConverter.clear_project_type_map_cache
  end
end
