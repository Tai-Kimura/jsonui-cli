# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/blur_converter'

RSpec.describe RjuiTools::React::Converters::BlurConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'basic blur view' do
      it 'generates div with backdrop blur' do
        converter = create_converter({ 'class' => 'Blur' })
        result = converter.convert
        expect(result).to include('<div')
        expect(result).to include("backdropFilter: 'blur")
        expect(result).to include("WebkitBackdropFilter: 'blur")
      end
    end

    context 'with effectStyle light' do
      it 'applies light blur effect' do
        converter = create_converter({ 'class' => 'Blur', 'effectStyle' => 'light' })
        result = converter.convert
        expect(result).to include('rgba(255, 255, 255, 0.7)')
      end
    end

    context 'with effectStyle dark' do
      it 'applies dark blur effect' do
        converter = create_converter({ 'class' => 'Blur', 'effectStyle' => 'dark' })
        result = converter.convert
        expect(result).to include('rgba(0, 0, 0, 0.5)')
      end
    end

    context 'with effectStyle thick' do
      it 'applies thick blur effect' do
        converter = create_converter({ 'class' => 'Blur', 'effectStyle' => 'thick' })
        result = converter.convert
        expect(result).to include("blur(16px)")
      end
    end

    context 'with intensity' do
      it 'maps intensity to blur amount' do
        converter = create_converter({ 'class' => 'Blur', 'intensity' => 0.5 })
        result = converter.convert
        expect(result).to include("blur(10px)")
      end
    end

    context 'with blurRadius' do
      it 'uses direct blur radius' do
        converter = create_converter({ 'class' => 'Blur', 'blurRadius' => 15 })
        result = converter.convert
        expect(result).to include("blur(15px)")
      end
    end

    context 'with cornerRadius' do
      it 'adds corner radius and overflow hidden' do
        converter = create_converter({ 'class' => 'Blur', 'cornerRadius' => 12 })
        result = converter.convert
        expect(result).to include('rounded-[12px]')
        expect(result).to include('overflow-hidden')
      end
    end

    context 'with custom backgroundColor' do
      it 'uses custom background color' do
        converter = create_converter({ 'class' => 'Blur', 'backgroundColor' => 'rgba(0, 0, 255, 0.3)' })
        result = converter.convert
        expect(result).to include("backgroundColor: 'rgba(0, 0, 255, 0.3)'")
      end
    end

    context 'with children' do
      it 'converts children' do
        converter = create_converter({ 'class' => 'Blur', 'child' => [{ 'class' => 'View', 'width' => 10 }] })
        result = converter.convert
        expect(result).to include('</div>')
      end
    end

    context 'with onClick' do
      it 'adds onClick and cursor-pointer' do
        converter = create_converter({ 'class' => 'Blur', 'onClick' => '@{handleClick}' })
        result = converter.convert
        expect(result).to include('onClick={data.handleClick}')
        expect(result).to include('cursor-pointer')
      end
    end

    context 'with testId' do
      it 'generates data-testid attribute' do
        converter = create_converter({ 'class' => 'Blur', 'testId' => 'blur-overlay' })
        result = converter.convert
        expect(result).to include('data-testid="blur-overlay"')
      end
    end

    context 'with visibility binding' do
      it 'wraps with conditional rendering' do
        converter = create_converter({ 'class' => 'Blur', 'visibility' => '@{showBlur}' })
        result = converter.convert
        expect(result).to include('{data.showBlur !== "gone" &&')
      end
    end
  end
end
