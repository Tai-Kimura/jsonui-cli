# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/select_box_converter'

RSpec.describe RjuiTools::React::Converters::SelectBoxConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'basic select with string items' do
      it 'generates select with options' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['Option 1', 'Option 2', 'Option 3'] })
        result = converter.convert
        expect(result).to include('<select')
        expect(result).to include('<option value="Option 1">Option 1</option>')
        expect(result).to include('<option value="Option 2">Option 2</option>')
        expect(result).to include('<option value="Option 3">Option 3</option>')
      end
    end

    context 'with hash items' do
      it 'generates options with value and text' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => [{ 'value' => '1', 'text' => 'First' }, { 'value' => '2', 'text' => 'Second' }] })
        result = converter.convert
        expect(result).to include('<option value="1">First</option>')
        expect(result).to include('<option value="2">Second</option>')
      end
    end

    context 'with items binding' do
      it 'generates dynamic options mapping' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => '@{options}' })
        result = converter.convert
        expect(result).to include('{data.options?.map((item) =>')
        expect(result).to include('{item.text || item.label}')
      end
    end

    context 'with placeholder/hint' do
      it 'adds disabled placeholder option' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A', 'B'], 'placeholder' => 'Select one...' })
        result = converter.convert
        expect(result).to include('<option value="" disabled hidden>Select one...</option>')
      end
    end

    context 'with selectedValue binding' do
      it 'generates value binding' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A', 'B'], 'selectedValue' => '@{selected}' })
        result = converter.convert
        expect(result).to include('value={data.selected}')
      end
    end

    context 'with static default value' do
      it 'generates defaultValue' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A', 'B'], 'value' => 'B' })
        result = converter.convert
        expect(result).to include('defaultValue="B"')
      end
    end

    context 'with onChange handler' do
      it 'generates onChange with optional chaining' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A', 'B'], 'onChange' => '@{handleChange}' })
        result = converter.convert
        expect(result).to include('onChange={(e) => data.handleChange?.(e.target.value)}')
      end
    end

    context 'with borderColor' do
      it 'applies border color' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A'], 'borderColor' => '#CCCCCC' })
        result = converter.convert
        expect(result).to include('border-[#CCCCCC]')
      end
    end

    context 'with fontColor' do
      it 'applies font color' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A'], 'fontColor' => '#333333' })
        result = converter.convert
        expect(result).to include('text-[#333333]')
      end
    end

    context 'with enabled=false' do
      it 'adds disabled state' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A'], 'enabled' => false })
        result = converter.convert
        expect(result).to include('disabled')
        expect(result).to include('opacity-50')
        expect(result).to include('cursor-not-allowed')
      end
    end

    context 'with testId' do
      it 'generates data-testid attribute' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A'], 'testId' => 'country-select' })
        result = converter.convert
        expect(result).to include('data-testid="country-select"')
      end
    end

    context 'with visibility binding' do
      it 'wraps with conditional rendering' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A'], 'visibility' => '@{showSelect}' })
        result = converter.convert
        expect(result).to include('{data.showSelect !== "gone" &&')
      end
    end
  end
end
