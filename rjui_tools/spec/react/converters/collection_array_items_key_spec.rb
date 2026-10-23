# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/collection_converter'
require_relative '../../support/typescript_compiler'

# A Collection given a plain array (items binds a declared list, no sections)
# keys each cell by the row's own cellIdProperty value, the index when the row
# has none, and by the index alone with no cellIdProperty (ticket
# 2026-10-23-rjui-collection-array-items-key-ignores-cell-id-property; ruling:
# this path is an ordinary one). Keyed by index, a row inserted above moved
# every cell's state to the row below.
RSpec.describe RjuiTools::React::Converters::CollectionConverter, 'a plain array\'s cell key' do
  def emit(extra = {}, ts: false)
    config = { 'use_tailwind' => true, '_data_classes' => { 'rows' => '[RowCellData]' } }
    config['typescript'] = true if ts
    described_class.new({ 'type' => 'Collection', 'items' => '@{rows}', 'cellClasses' => ['RowCell'] }.merge(extra), config).convert
  end

  it 'is the row\'s cellIdProperty value, the index when it has none' do
    expect(emit({ 'cellIdProperty' => 'id' })).to include('<RowCell key={String(item["id"] ?? index)} data={item} />')
  end

  it 'reads the row as a record in TypeScript' do
    expect(emit({ 'cellIdProperty' => 'id' }, ts: true))
      .to include('key={String((item as unknown as Record<string, unknown>)["id"] ?? index)}')
  end

  it 'rides the sizing wrapper when the cell has a size' do
    expect(emit({ 'cellIdProperty' => 'id', 'cellWidth' => 100 })).to include('<div key={String(item["id"] ?? index)} className="shrink-0 overflow-hidden"')
  end

  it 'compiles as TypeScript, keyed and not, wrapped and not' do
    emits = [{ 'cellIdProperty' => 'id' }, { 'cellIdProperty' => 'id', 'cellWidth' => 100 }, {}].map { |extra| emit(extra, ts: true) }
    expect(TypeScriptCompiler.component(*emits)).to compile_as_typescript.with_ambient(<<~TS)
      declare namespace JSX { interface IntrinsicAttributes { key?: string | number } }   // React's, on every element
      interface RowCellData { id?: string; title: string }
      declare const data: { rows?: RowCellData[] };
      declare function RowCell(props: { data: RowCellData; id?: string }): JSX.Element;
    TS
  end

  it 'is the index with no cellIdProperty, as before' do
    out = emit
    expect(out).to include('<RowCell key={index} data={item} />')
    expect(out).not_to include('String(item')
  end
end
