# frozen_string_literal: true

require_relative '../spec_helper'
require 'react/data_model_generator'

RSpec.describe 'CollectionDataSource TS emission' do
  let(:instance) { RjuiTools::React::DataModelGenerator.allocate }

  it 'defaults T to `unknown`, not `Record<string, unknown>`' do
    output = instance.send(:generate_collection_data_source_typescript)
    expect(output).to include('export interface CollectionDataSection<T = unknown>')
    expect(output).to include('export class CollectionDataSource<T = unknown>')
    expect(output).to include('export const createCollectionDataSource = <T = unknown>')
  end

  it 'does not constrain T with an index signature' do
    output = instance.send(:generate_collection_data_source_typescript)
    expect(output).not_to include('T = Record<string, unknown>')
    expect(output).not_to include('T extends Record<string, unknown>')
  end

  it 'still uses Record<string, unknown> for header/footer slots (no generic leakage there)' do
    output = instance.send(:generate_collection_data_source_typescript)
    expect(output).to include('header?: Record<string, unknown>;')
    expect(output).to include('footer?: Record<string, unknown>;')
  end
end
