# frozen_string_literal: true

require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require 'react/converters/view_converter'
require 'react/converters/image_converter'
require 'react/converters/label_converter'
require 'react/viewmodel_generator'
require 'react/data_model_generator'

# An empty or blank tap handler names no method (shared/core/
# tap_accessibility.rb `handler?`), so it is no tap: no onClick, no pointer
# cursor, no action stub. rjui emitted `onClick={}`, `onClick={data.}`,
# `onClick={data.   }` and `data.?.()` for them — TSX that does not compile
# (ticket kjui-empty-onclick-emits-invalid-kotlin, all three codegens).
RSpec.describe 'rjui empty and blank tap handlers' do
  let(:config) { { 'use_tailwind' => true } }

  EMPTY_TAP_HANDLERS = [
    { 'onClick' => '' }, { 'onClick' => '   ' }, { 'onClick' => '@{}' }, { 'onClick' => '@{ }' },
    { 'onclick' => '' }, { 'onclick' => '   ' }, { 'onclick' => [] }, { 'onclick' => ['', ' '] }
  ].freeze

  EMPTY_TAP_AMBIENT = <<~TS
    declare const data: { onOpen?: () => void };
    declare function partialText(
      text: string,
      specs: Array<{ range: unknown; className?: string; onClick?: () => void }>
    ): JSX.Element;
  TS

  def view(attrs)
    RjuiTools::React::Converters::ViewConverter.new({ 'type' => 'View', 'id' => 't' }.merge(attrs), config).convert_node(1)
  end

  def image(attrs)
    RjuiTools::React::Converters::ImageConverter
      .new({ 'type' => 'Image', 'id' => 'i', 'srcName' => 'icon' }.merge(attrs), config).convert_node(1)
  end

  def label(range_attrs)
    RjuiTools::React::Converters::LabelConverter.new(
      { 'type' => 'Label', 'id' => 'p', 'text' => 'Open terms',
        'partialAttributes' => [{ 'range' => [0, 4], 'fontColor' => '#FF0000' }.merge(range_attrs)] }, config
    ).convert_node(1)
  end

  def tsx(*elements)
    <<~TSX
      export const Emitted = (): JSX.Element => (
        <>
      #{elements.join("\n")}
        </>
      );
    TSX
  end

  EMPTY_TAP_HANDLERS.each do |handler|
    context handler.inspect do
      it 'gives a View, an Image and a partial range no tap, and the TSX compiles', :typescript_compile do
        elements = [view(handler), image(handler), label(handler)]
        elements.each do |code|
          expect(code).not_to include('onClick')
          expect(code).not_to include('cursor-pointer')
        end
        expect(tsx(*elements)).to compile_as_typescript.with_ambient(EMPTY_TAP_AMBIENT)
      end

      it 'generates no action stub' do
        layout = { 'type' => 'View', 'child' => [{ 'type' => 'Label', 'text' => 'x' }.merge(handler)] }
        expect(RjuiTools::React::ViewModelGenerator.allocate.send(:extract_onclick_actions, layout).to_a).to eq([])
        expect(RjuiTools::React::DataModelGenerator.allocate.send(:extract_onclick_actions, layout).to_a).to eq([])
      end
    end
  end

  # The controls: a blank element of an array is dropped from the calls, and a
  # blank onClick leaves the tap to onclick.
  it 'calls only the named elements, and the TSX compiles', :typescript_compile do
    array = view('onclick' => ['', 'onOpen', ' '])
    fallback = view('onClick' => '', 'onclick' => 'onOpen')
    ranged = label('onclick' => 'onOpen')
    expect(array).to include('onClick={() => { data.onOpen?.(); }}')
    expect(fallback).to include('onClick={data.onOpen}')
    expect(ranged).to include('onClick: data.onOpen')
    [array, fallback, ranged].each { |code| expect(code).to include('cursor-pointer') }
    expect(tsx(array, fallback, ranged)).to compile_as_typescript.with_ambient(EMPTY_TAP_AMBIENT)
    layout = { 'type' => 'View', 'child' => [{ 'type' => 'Label', 'text' => 'x', 'onclick' => ['', 'onOpen'] }] }
    expect(RjuiTools::React::ViewModelGenerator.allocate.send(:extract_onclick_actions, layout).to_a).to eq(['onOpen'])
  end
end
