# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/view_converter'

RSpec.describe 'BaseConverter maxHeight collision' do
  let(:config_without_claim) { { 'use_tailwind' => true } }
  let(:config_with_claim) do
    {
      'use_tailwind' => true,
      '_attribute_definitions' => {
        'CodeBlock' => {
          'maxHeight' => { 'type' => 'number', 'description' => 'max visible height' }
        }
      }
    }
  end

  it 'still emits max-h-* for a plain View with maxHeight' do
    converter = RjuiTools::React::Converters::ViewConverter.new(
      { 'type' => 'View', 'maxHeight' => 200 },
      config_without_claim
    )
    result = converter.convert
    expect(result).to match(/max-h-/)
  end

  it 'suppresses max-h-* when the component type claims maxHeight as a prop' do
    converter = RjuiTools::React::Converters::ViewConverter.new(
      { 'type' => 'CodeBlock', 'maxHeight' => 400 },
      config_with_claim
    )
    result = converter.convert
    expect(result).not_to match(/max-h-/)
  end

  it 'still emits max-h-* for other component types even when CodeBlock claims maxHeight' do
    converter = RjuiTools::React::Converters::ViewConverter.new(
      { 'type' => 'View', 'maxHeight' => 200 },
      config_with_claim
    )
    result = converter.convert
    expect(result).to match(/max-h-/)
  end
end
