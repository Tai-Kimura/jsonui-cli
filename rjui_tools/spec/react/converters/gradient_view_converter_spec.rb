# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/gradient_view_converter'

RSpec.describe RjuiTools::React::Converters::GradientViewConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'basic gradient view' do
      it 'generates div with linear gradient' do
        converter = create_converter({ 'class' => 'GradientView', 'gradient' => ['#FF0000', '#0000FF'] })
        result = converter.convert
        expect(result).to include('<div')
        expect(result).to include('linear-gradient')
        expect(result).to include('#FF0000')
        expect(result).to include('#0000FF')
      end
    end

    context 'with vertical direction (default)' do
      it 'uses to bottom direction' do
        converter = create_converter({ 'class' => 'GradientView', 'gradient' => ['#FF0000', '#0000FF'] })
        result = converter.convert
        expect(result).to include('to bottom')
      end
    end

    context 'with horizontal direction' do
      it 'uses to right direction' do
        converter = create_converter({ 'class' => 'GradientView', 'gradient' => ['#FF0000', '#0000FF'], 'gradientDirection' => 'horizontal' })
        result = converter.convert
        expect(result).to include('to right')
      end
    end

    context 'with oblique direction' do
      it 'uses 45deg angle' do
        converter = create_converter({ 'class' => 'GradientView', 'gradient' => ['#FF0000', '#0000FF'], 'gradientDirection' => 'oblique' })
        result = converter.convert
        expect(result).to include('45deg')
      end
    end

    context 'with custom angle' do
      it 'uses custom angle' do
        converter = create_converter({ 'class' => 'GradientView', 'gradient' => ['#FF0000', '#0000FF'], 'angle' => 135 })
        result = converter.convert
        expect(result).to include('135deg')
      end
    end

    context 'with startPoint and endPoint' do
      it 'calculates angle from points' do
        converter = create_converter({ 'class' => 'GradientView', 'gradient' => ['#FF0000', '#0000FF'], 'startPoint' => [0, 0], 'endPoint' => [1, 1] })
        result = converter.convert
        expect(result).to include('deg')
      end
    end

    context 'with locations' do
      it 'applies color stop positions' do
        converter = create_converter({ 'class' => 'GradientView', 'gradient' => ['#FF0000', '#FFFF00', '#0000FF'], 'locations' => [0, 0.5, 1] })
        result = converter.convert
        expect(result).to include('#FF0000 0%')
        expect(result).to include('#FFFF00 50%')
        expect(result).to include('#0000FF 100%')
      end
    end

    context 'with radial gradient type' do
      it 'uses radial gradient' do
        converter = create_converter({ 'class' => 'GradientView', 'gradient' => ['#FF0000', '#0000FF'], 'gradientType' => 'radial' })
        result = converter.convert
        expect(result).to include('radial-gradient')
      end
    end

    context 'with colors array (alternative to gradient)' do
      it 'supports colors property' do
        converter = create_converter({ 'class' => 'GradientView', 'colors' => ['#00FF00', '#FF00FF'] })
        result = converter.convert
        expect(result).to include('#00FF00')
        expect(result).to include('#FF00FF')
      end
    end

    context 'with cornerRadius' do
      it 'adds corner radius and overflow hidden' do
        converter = create_converter({ 'class' => 'GradientView', 'gradient' => ['#FF0000', '#0000FF'], 'cornerRadius' => 16 })
        result = converter.convert
        expect(result).to include('rounded-[16px]')
        expect(result).to include('overflow-hidden')
      end
    end

    context 'with children' do
      it 'converts children and adds flex' do
        converter = create_converter({ 'class' => 'GradientView', 'gradient' => ['#FF0000', '#0000FF'], 'child' => [{ 'class' => 'View', 'width' => 10 }] })
        result = converter.convert
        expect(result).to include('</div>')
        expect(result).to include('flex flex-col')
      end
    end

    context 'with onClick' do
      it 'adds onClick and cursor-pointer' do
        converter = create_converter({ 'class' => 'GradientView', 'gradient' => ['#FF0000', '#0000FF'], 'onClick' => '@{handleClick}' })
        result = converter.convert
        expect(result).to include('onClick={data.handleClick}')
        expect(result).to include('cursor-pointer')
      end
    end

    context 'with testId' do
      it 'generates data-testid attribute' do
        converter = create_converter({ 'class' => 'GradientView', 'gradient' => ['#FF0000', '#0000FF'], 'testId' => 'gradient-bg' })
        result = converter.convert
        expect(result).to include('data-testid="gradient-bg"')
      end
    end

    context 'with visibility binding' do
      it 'wraps with conditional rendering' do
        converter = create_converter({ 'class' => 'GradientView', 'gradient' => ['#FF0000', '#0000FF'], 'visibility' => '@{showGradient}' })
        result = converter.convert
        expect(result).to include('{data.showGradient !== "gone" &&')
      end
    end
  end
end
