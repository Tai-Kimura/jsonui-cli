# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/view_converter'
require 'react/converters/label_converter'

RSpec.describe 'Responsive integration with converters' do
  let(:default_config) { { 'use_tailwind' => true } }

  describe RjuiTools::React::Converters::ViewConverter do
    def create_converter(json_data, config = nil)
      described_class.new(json_data, config || default_config)
    end

    context 'with responsive orientation' do
      it 'generates responsive Tailwind classes in className' do
        converter = create_converter({
          'type' => 'View',
          'orientation' => 'vertical',
          'responsive' => {
            'regular' => { 'orientation' => 'horizontal' }
          },
          'child' => [
            { 'type' => 'Label', 'text' => 'A' }
          ]
        })
        output = converter.convert(2)

        expect(output).to include('flex-col')
        expect(output).to include('lg:flex-row')
      end
    end

    context 'with responsive spacing' do
      it 'generates responsive gap classes' do
        converter = create_converter({
          'type' => 'View',
          'orientation' => 'vertical',
          'spacing' => 8,
          'responsive' => {
            'regular' => { 'spacing' => 24 }
          },
          'child' => [
            { 'type' => 'Label', 'text' => 'A' }
          ]
        })
        output = converter.convert(2)

        expect(output).to include('gap-2')
        expect(output).to include('lg:gap-6')
      end
    end

    context 'with responsive visibility (hidden to visible)' do
      it 'generates hidden lg:block pattern' do
        converter = create_converter({
          'type' => 'View',
          'visibility' => 'gone',
          'responsive' => {
            'regular' => { 'visibility' => 'visible' }
          },
          'child' => []
        })
        output = converter.convert(2)

        expect(output).to include('hidden')
        expect(output).to include('lg:block')
      end
    end

    # Regression: rjui-responsive-compact-overrides-emitted-unprefixed —
    # compact overrides compile mobile-first: base value stays unprefixed
    # (emitted once by the normal attribute mapping) and the compact
    # override is scoped with max-md:.
    context 'with compact responsive overrides' do
      it 'scopes compact visibility gone to max-md:hidden' do
        converter = create_converter({
          'type' => 'View',
          'orientation' => 'horizontal',
          'responsive' => {
            'compact' => { 'visibility' => 'gone' }
          },
          'child' => []
        })
        output = converter.convert(2)

        expect(output).to include('max-md:hidden')
        expect(output).to include('flex flex-row')
        expect(output).not_to match(/(?<!max-md:)hidden/)
      end

      it 'keeps base orientation and scopes the compact override' do
        converter = create_converter({
          'type' => 'View',
          'orientation' => 'horizontal',
          'responsive' => {
            'compact' => { 'orientation' => 'vertical' }
          },
          'child' => []
        })
        output = converter.convert(2)

        expect(output).to include('flex-row')
        expect(output).to include('max-md:flex-col')
        expect(output.scan(/(?<![-\w])flex-row/).length).to eq(1)
        expect(output).not_to match(/(?<!max-md:)flex-col/)
      end

      it 'emits base padding once and scopes the compact padding override' do
        converter = create_converter({
          'type' => 'View',
          'padding' => 20,
          'responsive' => {
            'compact' => { 'padding' => 16 }
          },
          'child' => []
        })
        output = converter.convert(2)

        expect(output).to include('p-5')
        expect(output).to include('max-md:p-4')
        expect(output.scan(/(?<![-\w:])p-5/).length).to eq(1)
        expect(output).not_to match(/(?<!max-md:)p-4/)
      end
    end

    context 'with landscape responsive' do
      it 'generates template literal className with isLandscape conditional' do
        converter = create_converter({
          'type' => 'View',
          'orientation' => 'vertical',
          'responsive' => {
            'landscape' => { 'orientation' => 'horizontal' }
          },
          'child' => [
            { 'type' => 'Label', 'text' => 'A' }
          ]
        })
        output = converter.convert(2)

        # Should use template literal for dynamic className
        expect(output).to include('className={`')
        expect(output).to include('isLandscape')
      end
    end

    context 'without responsive block' do
      it 'generates normal className without responsive classes' do
        converter = create_converter({
          'type' => 'View',
          'orientation' => 'horizontal',
          'child' => [
            { 'type' => 'Label', 'text' => 'A' }
          ]
        })
        output = converter.convert(2)

        expect(output).to include('flex flex-row')
        expect(output).not_to include('lg:')
        expect(output).not_to include('md:')
      end
    end

    context 'with multiple breakpoints' do
      it 'generates classes for all breakpoints' do
        converter = create_converter({
          'type' => 'View',
          'orientation' => 'vertical',
          'responsive' => {
            'medium' => { 'orientation' => 'horizontal' },
            'regular' => { 'orientation' => 'horizontal' }
          },
          'child' => [
            { 'type' => 'Label', 'text' => 'A' }
          ]
        })
        output = converter.convert(2)

        expect(output).to include('flex-col')
        expect(output).to include('md:flex-row')
        expect(output).to include('lg:flex-row')
      end
    end
  end

  describe RjuiTools::React::Converters::LabelConverter do
    def create_converter(json_data, config = nil)
      described_class.new(json_data, config || default_config)
    end

    context 'with responsive fontSize' do
      it 'generates responsive text size classes' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Hello',
          'fontSize' => 14,
          'responsive' => {
            'regular' => { 'fontSize' => 20 }
          }
        })
        output = converter.convert(2)

        expect(output).to include('text-sm')
        expect(output).to include('lg:text-xl')
      end
    end

    context 'with responsive fontColor' do
      it 'generates responsive text color classes' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Hello',
          'fontColor' => '#000000',
          'responsive' => {
            'regular' => { 'fontColor' => '#FF0000' }
          }
        })
        output = converter.convert(2)

        expect(output).to include('text-[#000000]')
        expect(output).to include('lg:text-[#FF0000]')
      end
    end
  end
end
