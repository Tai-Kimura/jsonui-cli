# frozen_string_literal: true

require 'swiftui/data_model_updater'
require_relative '../support/emitted_swift'

# A CollectionDataSource default in the explicit shape carries each section's
# header and footer data (INTERACTIVE_HOST_CONTRACT.md §4, from jsonui-cli
# 1.9.0): `{"sections": [{"cells": [...], "header": {...}, "footer": {...}}]}`.
# The literal dropped both until then, so a layout that declared a section
# header drew none on the codegen path — the generated flow, list and grid
# read `section.header?.data` and found nil — while the web drew it; no
# conformance fixture could show a header on iOS.
RSpec.describe 'sjui CollectionDataSource default: a section header and footer' do
  let(:updater) { SjuiTools::SwiftUI::DataModelUpdater.allocate }

  def literal(value)
    updater.send(:format_default_value, value, 'CollectionDataSource')
  end

  EDGES = { 'sections' => [
    { 'cell' => 'conformance_cell', 'header' => { 'title' => 'Header' }, 'cells' => [{ 'title' => 'A' }],
      'footer' => { 'title' => 'Footer', 'n' => 2 } },
    { 'cells' => [{ 'title' => 'B' }], 'header' => {} }
  ] }.freeze

  it 'emits the header before the cells and the footer after, in the initializer order' do
    out = literal(EDGES)
    expect(out).to eq(
      'CollectionDataSource(sections: [' \
      'CollectionDataSection(header: (viewName: "", data: ["title": "Header"]), ' \
      'cells: (viewName: "conformance_cell", data: [["title": "A"]]), ' \
      'footer: (viewName: "", data: ["title": "Footer", "n": 2])), ' \
      'CollectionDataSection(header: (viewName: "", data: [:]), cells: (viewName: "", data: [["title": "B"]]))])'
    )
  end

  it 'control: a section with neither, and the shorthand, emit what they always did' do
    expect(literal([{ 'title' => 'A' }])).to eq('CollectionDataSource(sections: [CollectionDataSection(cells: (viewName: "", data: [["title": "A"]]))])')
    expect(literal('sections' => [{ 'cells' => [], 'header' => 'not a dictionary' }]))
      .to eq('CollectionDataSource(sections: [CollectionDataSection(cells: (viewName: "", data: []))])')
  end

  # Against the library's shape as transcribed in EmittedSwift (a transcription,
  # not the library: the stub's memberwise initializer takes header, cells,
  # footer in the order CollectionDataSource.swift's init does).
  it 'type-checks', :swift_compile do
    expect(<<~SWIFT).to compile_as_swift
      #{EmittedSwift::COLLECTION_DATA_SOURCE_STUB}
      let items: CollectionDataSource = #{literal(EDGES)}
    SWIFT
  end
end
