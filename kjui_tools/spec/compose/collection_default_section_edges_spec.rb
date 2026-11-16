# frozen_string_literal: true

require 'compose/data_model_updater'
require_relative '../support/kotlin_compiler'

# A CollectionDataSource default in the explicit shape carries each section's
# header and footer data (INTERACTIVE_HOST_CONTRACT.md §4, from jsonui-cli
# 1.9.0): `{"sections": [{"cells": [...], "header": {...}, "footer": {...}}]}`.
# The literal dropped both until then, so a layout that declared a section
# header drew none on the codegen path — the generated Collection reads
# `section.header?.let` and found null — while the web drew it.
RSpec.describe 'kjui CollectionDataSource default: a section header and footer' do
  let(:updater) { KjuiTools::Compose::DataModelUpdater.allocate }

  def literal(value)
    updater.send(:collection_data_source_literal, value)
  end

  EDGES = { 'sections' => [
    { 'cell' => 'conformance_cell', 'header' => { 'title' => 'Header' }, 'cells' => [{ 'title' => 'A' }],
      'footer' => { 'title' => 'Footer', 'n' => 2 } },
    { 'cells' => [{ 'title' => 'B' }], 'header' => {} }
  ] }.freeze

  it 'emits the header and footer as HeaderFooterData beside the cells' do
    out = literal(EDGES)
    section0 = out[/CollectionDataSection\(cells = .*?"A"\)\)\), header = .*?, footer = .*?"n" to 2\)\)/]
    expect(section0).to include('header = com.kotlinjsonui.data.CollectionDataSection.HeaderFooterData(viewName = "", data = mapOf("title" to "Header"))')
    expect(section0).to include('footer = com.kotlinjsonui.data.CollectionDataSection.HeaderFooterData(viewName = "", data = mapOf("title" to "Footer", "n" to 2))')
    expect(out).to include('data = listOf(mapOf("title" to "B"))), header = com.kotlinjsonui.data.CollectionDataSection.HeaderFooterData(viewName = "", data = mapOf()))')
  end

  it 'control: a section with neither, and the shorthand, emit what they always did' do
    expect(literal([{ 'title' => 'A' }])).to eq(
      'com.kotlinjsonui.data.CollectionDataSource(sections = listOf(com.kotlinjsonui.data.CollectionDataSection(cells = ' \
      'com.kotlinjsonui.data.CollectionDataSection.CellData(viewName = "", data = listOf(mapOf("title" to "A"))))))'
    )
    expect(literal('sections' => [{ 'cells' => [], 'footer' => 'not a dictionary' }])).not_to include('footer')
  end

  # Against the library's classes as transcribed here (a transcription, not
  # the library: KotlinJsonUI library/src/main/kotlin/com/kotlinjsonui/data/
  # CollectionDataSection.kt and CollectionDataSource.kt, the constructors'
  # parameter names and types). The value is read back after construction.
  it 'compiles against the library shape' do
    expect(<<~KOTLIN).to compile_as_kotlin
      package com.kotlinjsonui.data

      data class CollectionDataSection(
          val header: HeaderFooterData? = null,
          val footer: HeaderFooterData? = null,
          val cells: CellData? = null,
          val columns: Int? = null,
          val cellIdProperty: String? = null,
          val autoChangeTrackingId: Boolean = false
      ) {
          data class CellData(val viewName: String, val data: List<Map<String, Any>>)
          data class HeaderFooterData(val viewName: String, val data: Map<String, Any>)
      }
      data class CollectionDataSource(val sections: List<CollectionDataSection> = emptyList())

      val items = #{literal(EDGES)}
      val headerTitle: Any? = items.sections[0].header?.data?.get("title")
    KOTLIN
  end
end
