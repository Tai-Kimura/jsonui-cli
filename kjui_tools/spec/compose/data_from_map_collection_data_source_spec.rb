# frozen_string_literal: true

require 'compose/data_model_updater'
require_relative '../support/kotlin_compiler'

# kjui-frommap-drops-collectiondatasource: a generated `XxxData.fromMap` wrote
# `CollectionDataSource()` for a CollectionDataSource field whatever the map
# held, while the generated `updateData` (`value as? CollectionDataSource`)
# and iOS's `update(dictionary:)` read the value. A contract test that builds
# its Data with `fromMap(...)`, or a cell whose data carries a nested
# Collection, got an empty source. It reads the map now, falling back to the
# declared default and else the empty source, as the other types do.
#
# The arm RUNS the emitted Data class on the JVM: the emitted text with
# `com.kotlinjsonui.data.` dropped, against stubs of the three data classes.
RSpec.describe 'kjui codegen: fromMap reads a CollectionDataSource field' do
  let(:updater) { KjuiTools::Compose::DataModelUpdater.allocate }

  after { KjuiTools::Core::TypeConverter.clear_project_type_map_cache }

  def emitted
    props = [
      { 'name' => 'rows', 'class' => 'CollectionDataSource', 'defaultValue' => nil },
      { 'name' => 'seeded', 'class' => 'CollectionDataSource', 'defaultValue' => [{ 'title' => 'Declared' }] }
    ]
    updater.send(:generate_data_content, 'Probe', props, [])
  end

  it 'emits the map read with the declared default behind it' do
    text = emitted
    expect(text).to include('rows = map["rows"] as? com.kotlinjsonui.data.CollectionDataSource ?: com.kotlinjsonui.data.CollectionDataSource()')
    expect(text).to match(/seeded = map\["seeded"\] as\? com\.kotlinjsonui\.data\.CollectionDataSource \?: com\.kotlinjsonui\.data\.CollectionDataSource\(sections = /)
  end

  it 'returns the value the map holds, the declared default, else an empty source', :kotlin_compile do
    skip KotlinCompiler.unavailable_reason if KotlinCompiler.unavailable_reason

    model = emitted.lines.reject { |l| l.start_with?('package ') }.join.gsub('com.kotlinjsonui.data.', '')
    source = <<~KOTLIN
      data class CollectionDataSection(val cells: CellData? = null) {
          data class CellData(val viewName: String, val data: List<Map<String, Any>>)
      }
      data class CollectionDataSource(val sections: List<CollectionDataSection> = emptyList())

      #{model}

      fun titles(s: CollectionDataSource?): String =
          s?.sections?.flatMap { it.cells?.data ?: emptyList() }?.joinToString(",") { it["title"].toString() } ?: "null"

      fun main() {
          val given = CollectionDataSource(listOf(CollectionDataSection(CollectionDataSection.CellData("Row", listOf(mapOf("title" to "Given"))))))
          val read = ProbeData.fromMap(mapOf("rows" to given, "seeded" to given))
          println("given rows=" + titles(read.rows) + " seeded=" + titles(read.seeded))
          val absent = ProbeData.fromMap(emptyMap())
          println("absent rows=" + titles(absent.rows) + " seeded=" + titles(absent.seeded))
          val wrong = ProbeData.fromMap(mapOf("rows" to "not a source"))
          println("wrong rows=" + titles(wrong.rows))
          println("round trip=" + (ProbeData.fromMap(read.toMap()) == read))
      }
    KOTLIN

    # The ratchet's arm (emitted_kotlin_reaches_a_compiler_spec); the run below compiles it again to run it.
    expect(source).to compile_as_kotlin
    run = KotlinCompiler.run(source)
    expect(run.errors).to eq([])
    expect(run.output.lines.map(&:strip)).to eq([
      # Through jsonui-cli 1.9.5: "given rows= seeded=" — both emptied.
      'given rows=Given seeded=Given',
      'absent rows= seeded=Declared',
      'wrong rows=',
      'round trip=true'
    ])
  end
end
