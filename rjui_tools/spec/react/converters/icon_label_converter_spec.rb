# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/icon_label_converter'

RSpec.describe RjuiTools::React::Converters::IconLabelConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'basic icon label' do
      it 'generates div with icon and text' do
        converter = create_converter({ 'class' => 'IconLabel', 'text' => 'Label Text', 'icon' => 'icon.png' })
        result = converter.convert
        expect(result).to include('<div')
        expect(result).to include('<img')
        expect(result).to include('icon.png')
        expect(result).to include('Label Text')
        expect(result).to include('flex')
      end
    end

    context 'with icon position left (default)' do
      it 'uses flex-row' do
        converter = create_converter({ 'class' => 'IconLabel', 'text' => 'Text', 'icon' => 'icon.png' })
        result = converter.convert
        expect(result).to include('flex-row')
        expect(result).to include('mr-[4px]')
      end
    end

    context 'with icon position right' do
      it 'uses flex-row-reverse' do
        converter = create_converter({ 'class' => 'IconLabel', 'text' => 'Text', 'icon' => 'icon.png', 'iconPosition' => 'Right' })
        result = converter.convert
        expect(result).to include('flex-row-reverse')
        expect(result).to include('ml-[4px]')
      end
    end

    context 'with icon position top' do
      it 'uses flex-col' do
        converter = create_converter({ 'class' => 'IconLabel', 'text' => 'Text', 'icon' => 'icon.png', 'iconPosition' => 'Top' })
        result = converter.convert
        expect(result).to include('flex-col')
        expect(result).to include('mb-[4px]')
      end
    end

    context 'with icon position bottom' do
      it 'uses flex-col-reverse' do
        converter = create_converter({ 'class' => 'IconLabel', 'text' => 'Text', 'icon' => 'icon.png', 'iconPosition' => 'Bottom' })
        result = converter.convert
        expect(result).to include('flex-col-reverse')
        expect(result).to include('mt-[4px]')
      end
    end

    context 'with custom icon margin' do
      it 'applies custom margin' do
        converter = create_converter({ 'class' => 'IconLabel', 'text' => 'Text', 'icon' => 'icon.png', 'iconMargin' => 8 })
        result = converter.convert
        expect(result).to include('mr-[8px]')
      end
    end

    context 'with icon size array' do
      it 'applies width and height' do
        converter = create_converter({ 'class' => 'IconLabel', 'text' => 'Text', 'icon' => 'icon.png', 'iconSize' => [24, 24] })
        result = converter.convert
        expect(result).to include('w-[24px]')
        expect(result).to include('h-[24px]')
      end
    end

    context 'with icon size number' do
      it 'applies size to both dimensions' do
        converter = create_converter({ 'class' => 'IconLabel', 'text' => 'Text', 'icon' => 'icon.png', 'iconSize' => 20 })
        result = converter.convert
        expect(result).to include('w-[20px]')
        expect(result).to include('h-[20px]')
      end
    end

    context 'with selected state and icon_on/icon_off' do
      it 'generates conditional icon src' do
        converter = create_converter({ 'class' => 'IconLabel', 'text' => 'Text', 'selected' => '@{isSelected}', 'icon_on' => 'on.png', 'icon_off' => 'off.png' })
        result = converter.convert
        expect(result).to include("isSelected ? 'on.png' : 'off.png'")
      end
    end

    context 'with fontSize' do
      it 'applies font size to text' do
        converter = create_converter({ 'class' => 'IconLabel', 'text' => 'Text', 'icon' => 'icon.png', 'fontSize' => 16 })
        result = converter.convert
        expect(result).to include('text-base')
      end
    end

    context 'with fontWeight' do
      it 'applies font weight to text' do
        converter = create_converter({ 'class' => 'IconLabel', 'text' => 'Text', 'icon' => 'icon.png', 'fontWeight' => 'bold' })
        result = converter.convert
        expect(result).to include('font-bold')
      end
    end

    context 'with fontColor' do
      it 'applies font color to text' do
        converter = create_converter({ 'class' => 'IconLabel', 'text' => 'Text', 'icon' => 'icon.png', 'fontColor' => '#333333' })
        result = converter.convert
        expect(result).to include('text-[#333333]')
      end
    end

    context 'with onClick' do
      it 'adds onClick and cursor-pointer' do
        converter = create_converter({ 'class' => 'IconLabel', 'text' => 'Text', 'icon' => 'icon.png', 'onClick' => '@{handleClick}' })
        result = converter.convert
        expect(result).to include('onClick={data.handleClick}')
        expect(result).to include('cursor-pointer')
      end
    end

    context 'with testId' do
      it 'generates data-testid attribute' do
        converter = create_converter({ 'class' => 'IconLabel', 'text' => 'Text', 'icon' => 'icon.png', 'testId' => 'menu-item' })
        result = converter.convert
        expect(result).to include('data-testid="menu-item"')
      end
    end

    context 'with visibility binding' do
      it 'wraps with conditional rendering' do
        converter = create_converter({ 'class' => 'IconLabel', 'text' => 'Text', 'icon' => 'icon.png', 'visibility' => '@{showItem}' })
        result = converter.convert
        expect(result).to include('{data.showItem !== "gone" &&')
      end
    end
  end
end
