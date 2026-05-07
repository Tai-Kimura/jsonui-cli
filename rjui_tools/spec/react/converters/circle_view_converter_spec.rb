# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/circle_view_converter'

RSpec.describe RjuiTools::React::Converters::CircleViewConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'basic circle view' do
      it 'generates circular div' do
        converter = create_converter({ 'class' => 'CircleView', 'width' => 50, 'height' => 50 })
        result = converter.convert
        expect(result).to include('<div')
        expect(result).to include('rounded-full')
        expect(result).to include('overflow-hidden')
      end
    end

    context 'with fillColor' do
      it 'applies background color' do
        converter = create_converter({ 'class' => 'CircleView', 'fillColor' => '#FF5500' })
        result = converter.convert
        expect(result).to include("backgroundColor: '#FF5500'")
      end
    end

    context 'with background color binding' do
      it 'generates dynamic background color' do
        converter = create_converter({ 'class' => 'CircleView', 'fillColor' => '@{circleColor}' })
        result = converter.convert
        expect(result).to include('backgroundColor: data.circleColor')
      end
    end

    context 'with strokeColor' do
      it 'applies border' do
        converter = create_converter({ 'class' => 'CircleView', 'strokeColor' => '#000000', 'strokeWidth' => 2 })
        result = converter.convert
        expect(result).to include("border: '2px solid #000000'")
      end
    end

    context 'with borderColor (alternative to strokeColor)' do
      it 'uses border properties' do
        converter = create_converter({ 'class' => 'CircleView', 'borderColor' => '#333333', 'borderWidth' => 3 })
        result = converter.convert
        expect(result).to include("border: '3px solid #333333'")
      end
    end

    context 'with borderStyle' do
      it 'applies border style' do
        converter = create_converter({ 'class' => 'CircleView', 'strokeColor' => '#000000', 'borderStyle' => 'dashed' })
        result = converter.convert
        expect(result).to include('dashed')
      end
    end

    context 'with shadow' do
      it 'applies box shadow' do
        converter = create_converter({ 'class' => 'CircleView', 'shadow' => { 'x' => 2, 'y' => 4, 'blur' => 8, 'color' => 'rgba(0,0,0,0.3)' } })
        result = converter.convert
        expect(result).to include("boxShadow: '2px 4px 8px rgba(0,0,0,0.3)'")
      end
    end

    context 'with children' do
      it 'converts children and centers content' do
        converter = create_converter({ 'class' => 'CircleView', 'child' => [{ 'class' => 'View', 'width' => 10 }] })
        result = converter.convert
        expect(result).to include('</div>')
        expect(result).to include('flex items-center justify-center')
      end
    end

    context 'with onClick' do
      it 'adds onClick and cursor-pointer' do
        converter = create_converter({ 'class' => 'CircleView', 'onClick' => '@{handleCircleClick}' })
        result = converter.convert
        expect(result).to include('onClick={data.handleCircleClick}')
        expect(result).to include('cursor-pointer')
      end
    end

    context 'with testId' do
      it 'generates data-testid attribute' do
        converter = create_converter({ 'class' => 'CircleView', 'testId' => 'avatar-circle' })
        result = converter.convert
        expect(result).to include('data-testid="avatar-circle"')
      end
    end

    context 'with tag' do
      it 'generates data-tag attribute' do
        converter = create_converter({ 'class' => 'CircleView', 'tag' => 'circle-1' })
        result = converter.convert
        expect(result).to include('data-tag="circle-1"')
      end
    end

    context 'with visibility binding' do
      it 'wraps with conditional rendering' do
        converter = create_converter({ 'class' => 'CircleView', 'visibility' => '@{showCircle}' })
        result = converter.convert
        expect(result).to include('{data.showCircle !== "gone" &&')
      end
    end
  end
end
