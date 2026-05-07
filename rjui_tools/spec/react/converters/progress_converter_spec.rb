# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/progress_converter'

RSpec.describe RjuiTools::React::Converters::ProgressConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'basic progress bar' do
      it 'generates progress element' do
        converter = create_converter({ 'class' => 'Progress', 'value' => 50 })
        result = converter.convert
        expect(result).to include('<progress')
        expect(result).to include('value={50}')
        expect(result).to include('max={100}')
      end
    end

    context 'with custom maximum' do
      it 'uses custom max value' do
        converter = create_converter({ 'class' => 'Progress', 'value' => 25, 'maximumValue' => 50 })
        result = converter.convert
        expect(result).to include('max={50}')
      end
    end

    context 'with value binding' do
      it 'generates value binding' do
        converter = create_converter({ 'class' => 'Progress', 'value' => '@{progressValue}' })
        result = converter.convert
        expect(result).to include('value={data.progressValue}')
      end
    end

    context 'with progress property' do
      it 'uses progress as value' do
        converter = create_converter({ 'class' => 'Progress', 'progress' => 75 })
        result = converter.convert
        expect(result).to include('value={75}')
      end
    end

    context 'with tintColor' do
      it 'applies progress tint color' do
        converter = create_converter({ 'class' => 'Progress', 'value' => 50, 'tintColor' => '#FF5500' })
        result = converter.convert
        expect(result).to include('[&::-webkit-progress-value]:bg-[#FF5500]')
        expect(result).to include('[&::-moz-progress-bar]:bg-[#FF5500]')
      end
    end

    context 'with progressTintColor' do
      it 'applies progress tint color' do
        converter = create_converter({ 'class' => 'Progress', 'value' => 50, 'progressTintColor' => '#00FF00' })
        result = converter.convert
        expect(result).to include('[&::-webkit-progress-value]:bg-[#00FF00]')
      end
    end

    context 'with trackTintColor' do
      it 'applies track background color' do
        converter = create_converter({ 'class' => 'Progress', 'value' => 50, 'trackTintColor' => '#EEEEEE' })
        result = converter.convert
        expect(result).to include('[&::-webkit-progress-bar]:bg-[#EEEEEE]')
      end
    end

    context 'with custom height' do
      it 'applies custom height' do
        converter = create_converter({ 'class' => 'Progress', 'value' => 50, 'progressHeight' => 8 })
        result = converter.convert
        expect(result).to include('h-[8px]')
      end
    end

    context 'with barHeight' do
      it 'uses barHeight for height' do
        converter = create_converter({ 'class' => 'Progress', 'value' => 50, 'barHeight' => 4 })
        result = converter.convert
        expect(result).to include('h-[4px]')
      end
    end

    context 'with testId' do
      it 'generates data-testid attribute' do
        converter = create_converter({ 'class' => 'Progress', 'value' => 50, 'testId' => 'download-progress' })
        result = converter.convert
        expect(result).to include('data-testid="download-progress"')
      end
    end

    context 'with visibility binding' do
      it 'wraps with conditional rendering' do
        converter = create_converter({ 'class' => 'Progress', 'value' => 50, 'visibility' => '@{showProgress}' })
        result = converter.convert
        expect(result).to include('{data.showProgress !== "gone" &&')
      end
    end
  end
end
