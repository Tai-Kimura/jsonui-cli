# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/view_converter'
require 'react/converters/label_converter'

RSpec.describe 'BaseConverter#build_id_attr' do
  let(:config) { { 'use_tailwind' => true } }

  it 'emits literal id when json["id"] is a plain string' do
    converter = RjuiTools::React::Converters::ViewConverter.new(
      { 'type' => 'View', 'id' => 'my_root' },
      config
    )
    expect(converter.send(:build_id_attr)).to eq(' id="my_root"')
  end

  it 'emits nothing when id is absent' do
    converter = RjuiTools::React::Converters::ViewConverter.new(
      { 'type' => 'View' },
      config
    )
    expect(converter.send(:build_id_attr)).to eq('')
  end

  it 'emits a JSX expression when id is a @{field} binding' do
    converter = RjuiTools::React::Converters::ViewConverter.new(
      { 'type' => 'View', 'id' => '@{id}' },
      config
    )
    expect(converter.send(:build_id_attr)).to eq(' id={String(data.id)}')
  end

  it 'preserves a user-supplied data. prefix in the binding' do
    converter = RjuiTools::React::Converters::ViewConverter.new(
      { 'type' => 'View', 'id' => '@{data.itemId}' },
      config
    )
    expect(converter.send(:build_id_attr)).to eq(' id={String(data.itemId)}')
  end

  it 'converts view generated output: literal id renders unchanged' do
    converter = RjuiTools::React::Converters::ViewConverter.new(
      { 'type' => 'View', 'id' => 'root' },
      config
    )
    expect(converter.convert).to include('id="root"')
  end

  it 'converts view generated output: @{id} binding renders as JSX expression' do
    converter = RjuiTools::React::Converters::ViewConverter.new(
      { 'type' => 'View', 'id' => '@{id}' },
      config
    )
    result = converter.convert
    expect(result).to include('id={String(data.id)}')
    expect(result).not_to include('id="@{id}"')
  end
end
