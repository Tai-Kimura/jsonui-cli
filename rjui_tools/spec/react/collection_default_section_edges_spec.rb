# frozen_string_literal: true

require 'json'
require 'open3'
require_relative '../spec_helper'
require_relative '../support/typescript_compiler'
require 'react/data_model_generator'

# A CollectionDataSource default in the explicit shape carries each section's
# header and footer data (INTERACTIVE_HOST_CONTRACT.md §4, from jsonui-cli
# 1.9.0): `{"sections": [{"cells": [...], "header": {...}, "footer": {...}}]}`.
# The literal dropped both until then; the web drew a declared header anyway,
# with `{}` for its data.
RSpec.describe 'rjui CollectionDataSource default: a section header and footer' do
  let(:instance) { RjuiTools::React::DataModelGenerator.allocate }

  EDGES = { 'sections' => [
    { 'cell' => 'conformance_cell', 'header' => { 'title' => 'Header' }, 'cells' => [{ 'title' => 'A' }],
      'footer' => { 'title' => 'Footer', 'n' => 2 } },
    { 'cells' => [{ 'title' => 'B' }] }
  ] }.freeze

  # The sections the emitted constructor call builds, evaluated by node.
  def sections(value)
    js = instance.send(:collection_data_source_literal, value)
    program = "class CollectionDataSource { constructor(s) { this.sections = s; } }\n" \
              "console.log(JSON.stringify((#{js}).sections));"
    out, status = Open3.capture2e('node', '-e', program)
    raise "node: #{out}\n#{js}" unless status.success?

    JSON.parse(out)
  end

  it 'the header and footer data reach the section, where the Collection reads them' do
    expect(sections(EDGES)).to eq([
      { 'header' => { 'title' => 'Header' }, 'cells' => { 'data' => [{ 'title' => 'A' }] },
        'footer' => { 'title' => 'Footer', 'n' => 2 } },
      { 'cells' => { 'data' => [{ 'title' => 'B' }] } }
    ])
  end

  it 'control: the shorthand is one section of cells' do
    expect(sections([{ 'title' => 'A' }])).to eq([{ 'cells' => { 'data' => [{ 'title' => 'A' }] } }])
  end

  # Against the CollectionDataSource class the build writes (the TypeScript
  # emit itself, `export` dropped), not a copy of it.
  it 'type-checks against the generated CollectionDataSource' do
    generated = instance.send(:generate_collection_data_source_typescript).gsub(/^export /, '')
    expect("const items = #{instance.send(:collection_data_source_literal, EDGES)};\nexport default items;\n")
      .to compile_as_typescript.with_ambient(generated)
  end
end
