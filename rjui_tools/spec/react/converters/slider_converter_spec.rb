# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/slider_converter'

RSpec.describe RjuiTools::React::Converters::SliderConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'basic slider' do
      it 'generates range input' do
        converter = create_converter({ 'class' => 'Slider' })
        result = converter.convert
        expect(result).to include('<input')
        expect(result).to include('type="range"')
        expect(result).to include('min={0}')
        expect(result).to include('max={100}')
      end
    end

    context 'with custom min/max' do
      it 'uses custom range' do
        converter = create_converter({ 'class' => 'Slider', 'minimumValue' => 10, 'maximumValue' => 50 })
        result = converter.convert
        expect(result).to include('min={10}')
        expect(result).to include('max={50}')
      end
    end

    context 'with range array' do
      it 'uses array range values' do
        converter = create_converter({ 'class' => 'Slider', 'range' => [0, 200] })
        result = converter.convert
        expect(result).to include('min={0}')
        expect(result).to include('max={200}')
      end
    end

    context 'with step value' do
      it 'adds step attribute' do
        converter = create_converter({ 'class' => 'Slider', 'step' => 5 })
        result = converter.convert
        expect(result).to include('step={5}')
      end
    end

    context 'with value binding' do
      it 'generates value binding' do
        converter = create_converter({ 'class' => 'Slider', 'value' => '@{sliderValue}' })
        result = converter.convert
        expect(result).to include('value={data.sliderValue}')
      end
    end

    context 'with static value' do
      it 'generates defaultValue' do
        converter = create_converter({ 'class' => 'Slider', 'value' => 50 })
        result = converter.convert
        expect(result).to include('defaultValue={50}')
      end
    end

    context 'with onValueChange handler' do
      it 'generates onChange with optional chaining and number conversion' do
        converter = create_converter({ 'class' => 'Slider', 'onValueChange' => '@{handleSlide}' })
        result = converter.convert
        expect(result).to include('onChange={(e) => data.handleSlide?.(Number(e.target.value))}')
      end
    end

    context 'with value binding but no onValueChange (auto-generated)' do
      it 'auto-generates onChange handler from value binding' do
        converter = create_converter({ 'class' => 'Slider', 'value' => '@{sliderValue}' })
        result = converter.convert
        expect(result).to include('value={data.sliderValue}')
        expect(result).to include('onChange={(e) => data.onSliderValueChange?.(Number(e.target.value))}')
      end
    end

    context 'with tintColor' do
      it 'adds accent color style' do
        converter = create_converter({ 'class' => 'Slider', 'tintColor' => '#FF0000' })
        result = converter.convert
        expect(result).to include("accentColor: '#FF0000'")
      end
    end

    context 'with minimumTrackTintColor' do
      it 'uses minimum track color as accent' do
        converter = create_converter({ 'class' => 'Slider', 'minimumTrackTintColor' => '#00FF00' })
        result = converter.convert
        expect(result).to include("accentColor: '#00FF00'")
      end
    end

    context 'track colours' do
      it 'emits exactly one style attribute' do
        # Two `style={...}` on one element is a duplicate JSX attribute
        # (TS17001) and the generated file cannot be hand-patched.
        converter = create_converter({ 'class' => 'Slider', 'tintColor' => '#FF0000' })
        expect(converter.convert.scan('style={').length).to eq(1)
      end

      it 'resolves a palette name instead of emitting it as a colour' do
        # 'dark_red' is not CSS. The raw spelling used to reach the style
        # object through the Slider's own emitter.
        converter = create_converter({ 'class' => 'Slider', 'tintColor' => 'dark_red' })
        result = converter.convert
        expect(result).to include("accentColor: ColorManager.resolveColor('dark_red')")
        expect(result).not_to include("accentColor: 'dark_red'")
      end

      it 'reads the declared spellings ahead of the UIKit legacy ones' do
        converter = create_converter({
          'class' => 'Slider',
          'progressTintColor' => '#111111',
          'trackTintColor' => '#222222',
          'tintColor' => '#333333',
          'minimumTrackTintColor' => '#444444',
          'maximumTrackTintColor' => '#555555'
        })
        result = converter.convert
        expect(result).to include("accentColor: '#111111'")
        expect(result).to include('[&::-webkit-slider-runnable-track]:bg-[#222222]')
      end

      it 'falls back to the legacy spellings when the declared ones are absent' do
        converter = create_converter({
          'class' => 'Slider',
          'maximumTrackTintColor' => '#555555'
        })
        expect(converter.convert).to include('[&::-webkit-slider-runnable-track]:bg-[#555555]')
      end

      # Measured in Chromium: a background-color on the <input type="range">
      # itself is pixel-identical to no colour at all — the native control
      # paints the track over it. The pseudo-element accepts one, and does
      # not need `appearance: none` (which would take the thumb with it).
      it 'colours the track pseudo-element, not the input background' do
        converter = create_converter({ 'class' => 'Slider', 'trackTintColor' => '#222222' })
        result = converter.convert
        expect(result).to include('[&::-webkit-slider-runnable-track]:bg-[#222222]')
        expect(result).not_to include("backgroundColor: '#222222'")
      end
    end

    context 'with enabled=false' do
      it 'adds disabled attribute and styling' do
        converter = create_converter({ 'class' => 'Slider', 'enabled' => false })
        result = converter.convert
        expect(result).to include('disabled')
        expect(result).to include('opacity-50')
        expect(result).to include('cursor-not-allowed')
      end
    end

    context 'with enabled binding' do
      it 'generates dynamic disabled attribute' do
        converter = create_converter({ 'class' => 'Slider', 'enabled' => '@{canSlide}' })
        result = converter.convert
        expect(result).to include('disabled={!data.canSlide}')
      end
    end

    context 'with testId' do
      it 'generates data-testid attribute' do
        converter = create_converter({ 'class' => 'Slider', 'testId' => 'volume-slider' })
        result = converter.convert
        expect(result).to include('data-testid="volume-slider"')
      end
    end

    context 'with visibility binding' do
      it 'wraps with conditional rendering' do
        converter = create_converter({ 'class' => 'Slider', 'visibility' => '@{showSlider}' })
        result = converter.convert
        expect(result).to include('{data.showSlider !== "gone" &&')
      end
    end
  end
end
