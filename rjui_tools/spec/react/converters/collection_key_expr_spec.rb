# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/collection_converter'

RSpec.describe 'CollectionConverter key expression' do
  let(:ts_config) { { 'use_tailwind' => true, 'typescript' => true } }
  let(:js_config) { { 'use_tailwind' => true, 'typescript' => false } }

  def convert(json, config)
    RjuiTools::React::Converters::CollectionConverter.new(json, config).convert
  end

  it 'casts cellData to Record<string, unknown> before indexing under TypeScript' do
    # CollectionDataSource<T = unknown> leaves cellData typed as `unknown`
    # after the 2026-04-23 #7b fix. Bracket access on `unknown` is a TS18046.
    result = convert(
      {
        'type' => 'Collection',
        'id' => 'featured',
        'cellIdProperty' => 'id',
        'items' => '@{featuredLinks}',
        'sections' => [{ 'cell' => 'FeaturedCard' }]
      },
      ts_config
    )
    expect(result).to include(
      'key={String((cellData as Record<string, unknown>)["cellId"] ?? ' \
      '(cellData as Record<string, unknown>)["id"] ?? cellIndex)}'
    )
  end

  it 'uses plain bracket access in JavaScript (no `as` cast)' do
    result = convert(
      {
        'type' => 'Collection',
        'id' => 'featured',
        'cellIdProperty' => 'id',
        'items' => '@{featuredLinks}',
        'sections' => [{ 'cell' => 'FeaturedCard' }]
      },
      js_config
    )
    expect(result).to include('key={String(cellData["cellId"] ?? cellData["id"] ?? cellIndex)}')
    expect(result).not_to include('as Record<string, unknown>')
  end

  it 'wraps key in String(...) when autoChangeTrackingId + cellIdProperty are combined' do
    # enrichCellIds returns Array<... & {cellId: string}> so the dot access is
    # fine even under T = unknown — no cast needed in this branch.
    result = convert(
      {
        'type' => 'Collection',
        'id' => 'platforms',
        'cellIdProperty' => 'id',
        'autoChangeTrackingId' => true,
        'items' => '@{platformCards}',
        'sections' => [{ 'cell' => 'PlatformCard' }]
      },
      ts_config
    )
    expect(result).to include('key={String(cellData.cellId ?? cellIndex)}')
  end

  it 'falls back to plain cellIndex when cellIdProperty is absent (no String wrap needed)' do
    result = convert(
      {
        'type' => 'Collection',
        'id' => 'simple',
        'items' => '@{items}',
        'sections' => [{ 'cell' => 'SimpleCell' }]
      },
      ts_config
    )
    expect(result).to include('key={cellIndex}')
  end
end
