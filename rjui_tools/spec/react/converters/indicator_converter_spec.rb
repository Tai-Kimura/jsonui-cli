# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/indicator_converter'

RSpec.describe RjuiTools::React::Converters::IndicatorConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'basic indicator' do
      it 'generates loading spinner' do
        converter = create_converter({ 'class' => 'Indicator' })
        result = converter.convert
        expect(result).to include('<div')
        expect(result).to include('animate-spin')
        expect(result).to include('rounded-full')
        expect(result).to include('border-2')
      end
    end

    # `size` is not an Indicator attribute: the layout normalizer folds it into
    # width / height before any converter runs, so the converter draws the
    # medium spinner for it rather than reading a second spelling.
    context 'with a legacy size' do
      it 'draws the medium spinner and reads no size' do
        %w[small large].each do |size|
          result = create_converter({ 'class' => 'Indicator', 'size' => size }).convert
          expect(result).to include('w-6 h-6')
          expect(result).not_to include('w-4 h-4')
          expect(result).not_to include('w-8 h-8')
        end
      end
    end

    context 'with wrapContent width/height' do
      it 'draws the medium spinner, not a px class of the keyword' do
        result = create_converter({ 'class' => 'Indicator', 'width' => 'wrapContent', 'height' => 'wrapContent' }).convert
        expect(result).to include('w-6 h-6')
        expect(result).not_to include('wrapContentpx')
      end
    end

    context 'with custom width/height' do
      it 'applies custom dimensions' do
        converter = create_converter({ 'class' => 'Indicator', 'width' => 32, 'height' => 32 })
        result = converter.convert
        expect(result).to include('w-[32px]')
        expect(result).to include('h-[32px]')
      end
    end

    context 'with color' do
      it 'applies spinner color' do
        converter = create_converter({ 'class' => 'Indicator', 'color' => '#FF5500' })
        result = converter.convert
        expect(result).to include('border-t-[#FF5500]')
      end
    end

    context 'with tintColor' do
      it 'uses tintColor for spinner' do
        converter = create_converter({ 'class' => 'Indicator', 'tintColor' => '#007AFF' })
        result = converter.convert
        expect(result).to include('border-t-[#007AFF]')
      end
    end

    context 'with custom strokeWidth' do
      it 'applies custom border width' do
        converter = create_converter({ 'class' => 'Indicator', 'strokeWidth' => 4 })
        result = converter.convert
        expect(result).to include('border-4')
      end
    end

    context 'with testId' do
      it 'generates data-testid attribute' do
        converter = create_converter({ 'class' => 'Indicator', 'testId' => 'loading-spinner' })
        result = converter.convert
        expect(result).to include('data-testid="loading-spinner"')
      end
    end

    context 'with visibility binding' do
      it 'wraps with conditional rendering' do
        converter = create_converter({ 'class' => 'Indicator', 'visibility' => '@{isLoading}' })
        result = converter.convert
        expect(result).to include('{data.isLoading !== "gone" &&')
      end
    end
  end
end
