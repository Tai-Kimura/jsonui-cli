# frozen_string_literal: true

require_relative '../spec_helper'
require 'react/responsive_helper'

RSpec.describe RjuiTools::React::ResponsiveHelper do
  describe '.build_responsive' do
    context 'when component has no responsive block' do
      it 'returns empty result' do
        component = { 'type' => 'View', 'orientation' => 'vertical' }
        result = described_class.build_responsive(component)

        expect(result[:classes]).to be_empty
        expect(result[:needs_landscape_hook]).to be false
        expect(result[:landscape_styles]).to be_empty
        expect(result[:stripped_keys]).to be_empty
      end
    end

    context 'with regular (lg:) breakpoint' do
      it 'generates orientation responsive classes' do
        component = {
          'type' => 'View',
          'orientation' => 'vertical',
          'responsive' => {
            'regular' => { 'orientation' => 'horizontal' }
          }
        }
        result = described_class.build_responsive(component)

        expect(result[:classes]).to include('flex-col')
        expect(result[:classes]).to include('lg:flex-row')
        expect(result[:needs_landscape_hook]).to be false
      end

      it 'generates spacing responsive classes' do
        component = {
          'type' => 'View',
          'spacing' => 8,
          'responsive' => {
            'regular' => { 'spacing' => 24 }
          }
        }
        result = described_class.build_responsive(component)

        expect(result[:classes]).to include('gap-2')
        expect(result[:classes]).to include('lg:gap-6')
      end

      it 'generates fontSize responsive classes' do
        component = {
          'type' => 'Label',
          'fontSize' => 14,
          'responsive' => {
            'regular' => { 'fontSize' => 20 }
          }
        }
        result = described_class.build_responsive(component)

        expect(result[:classes]).to include('text-sm')
        expect(result[:classes]).to include('lg:text-xl')
      end

      it 'generates visibility responsive classes (hidden to visible)' do
        component = {
          'type' => 'View',
          'visibility' => 'gone',
          'responsive' => {
            'regular' => { 'visibility' => 'visible' }
          }
        }
        result = described_class.build_responsive(component)

        expect(result[:classes]).to include('hidden')
        expect(result[:classes]).to include('lg:block')
      end

      it 'generates width responsive classes' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'responsive' => {
            'regular' => { 'width' => 300 }
          }
        }
        result = described_class.build_responsive(component)

        expect(result[:classes]).to include('w-full')
        expect(result[:classes]).to include('lg:w-[300px]')
      end

      it 'generates background responsive classes' do
        component = {
          'type' => 'View',
          'background' => '#FFFFFF',
          'responsive' => {
            'regular' => { 'background' => '#000000' }
          }
        }
        result = described_class.build_responsive(component)

        expect(result[:classes]).to include('bg-[#FFFFFF]')
        expect(result[:classes]).to include('lg:bg-[#000000]')
      end

      it 'generates textAlign responsive classes' do
        component = {
          'type' => 'Label',
          'textAlign' => 'left',
          'responsive' => {
            'regular' => { 'textAlign' => 'center' }
          }
        }
        result = described_class.build_responsive(component)

        expect(result[:classes]).to include('text-left')
        expect(result[:classes]).to include('lg:text-center')
      end
    end

    context 'with medium (md:) breakpoint' do
      it 'generates md: prefixed classes' do
        component = {
          'type' => 'View',
          'orientation' => 'vertical',
          'responsive' => {
            'medium' => { 'orientation' => 'horizontal' }
          }
        }
        result = described_class.build_responsive(component)

        expect(result[:classes]).to include('flex-col')
        expect(result[:classes]).to include('md:flex-row')
      end
    end

    context 'with multiple breakpoints' do
      it 'generates classes for all breakpoints' do
        component = {
          'type' => 'View',
          'orientation' => 'vertical',
          'spacing' => 4,
          'responsive' => {
            'medium' => { 'orientation' => 'horizontal', 'spacing' => 12 },
            'regular' => { 'orientation' => 'horizontal', 'spacing' => 24 }
          }
        }
        result = described_class.build_responsive(component)

        # Default classes
        expect(result[:classes]).to include('flex-col')
        expect(result[:classes]).to include('gap-1')

        # Medium breakpoint
        expect(result[:classes]).to include('md:flex-row')
        expect(result[:classes]).to include('md:gap-3')

        # Regular breakpoint
        expect(result[:classes]).to include('lg:flex-row')
        expect(result[:classes]).to include('lg:gap-6')
      end
    end

    context 'with landscape breakpoint' do
      it 'sets needs_landscape_hook to true' do
        component = {
          'type' => 'View',
          'spacing' => 8,
          'responsive' => {
            'landscape' => { 'spacing' => 16 }
          }
        }
        result = described_class.build_responsive(component)

        expect(result[:needs_landscape_hook]).to be true
      end

      it 'stores landscape styles separately' do
        component = {
          'type' => 'View',
          'orientation' => 'vertical',
          'responsive' => {
            'landscape' => { 'orientation' => 'horizontal' }
          }
        }
        result = described_class.build_responsive(component)

        expect(result[:landscape_styles]).to have_key('landscape')
        expect(result[:landscape_styles]['landscape']).to include('flex-row')
      end

      it 'handles compound landscape size class' do
        component = {
          'type' => 'View',
          'spacing' => 8,
          'responsive' => {
            'regular-landscape' => { 'spacing' => 32 }
          }
        }
        result = described_class.build_responsive(component)

        expect(result[:needs_landscape_hook]).to be true
        expect(result[:landscape_styles]).to have_key('regular-landscape')
      end
    end

    context 'with padding responsive' do
      it 'generates padding responsive classes for numeric values' do
        component = {
          'type' => 'View',
          'padding' => 8,
          'responsive' => {
            'regular' => { 'padding' => 16 }
          }
        }
        result = described_class.build_responsive(component)

        expect(result[:classes]).to include('p-2')
        expect(result[:classes]).to include('lg:p-4')
      end

      it 'generates padding responsive classes for array values' do
        component = {
          'type' => 'View',
          'padding' => [8, 16],
          'responsive' => {
            'regular' => { 'padding' => [16, 32] }
          }
        }
        result = described_class.build_responsive(component)

        expect(result[:classes]).to include('py-2 px-4')
        expect(result[:classes]).to include('lg:py-4 lg:px-8')
      end
    end

    context 'stripped_keys tracking' do
      it 'tracks overridden attribute keys' do
        component = {
          'type' => 'View',
          'orientation' => 'vertical',
          'spacing' => 8,
          'responsive' => {
            'regular' => { 'orientation' => 'horizontal', 'spacing' => 24 }
          }
        }
        result = described_class.build_responsive(component)

        expect(result[:stripped_keys]).to include('orientation')
        expect(result[:stripped_keys]).to include('spacing')
      end
    end
  end

  describe '.landscape_hook_declaration' do
    it 'returns the useMediaQuery hook call' do
      declaration = described_class.landscape_hook_declaration
      expect(declaration).to eq("const isLandscape = useMediaQuery('(orientation: landscape)');")
    end
  end

  describe '.build_landscape_class_expression' do
    it 'returns empty string for empty styles' do
      expr = described_class.build_landscape_class_expression({})
      expect(expr).to eq('')
    end

    it 'builds conditional expression for landscape styles' do
      landscape_styles = {
        'landscape' => ['flex-row', 'gap-4']
      }
      expr = described_class.build_landscape_class_expression(landscape_styles)
      expect(expr).to include('isLandscape')
      expect(expr).to include('flex-row gap-4')
    end
  end

  describe '.needs_landscape_hook?' do
    it 'returns false for non-responsive component' do
      component = { 'type' => 'View' }
      expect(described_class.needs_landscape_hook?(component)).to be false
    end

    it 'returns false for responsive without landscape' do
      component = {
        'type' => 'View',
        'responsive' => { 'regular' => { 'orientation' => 'horizontal' } }
      }
      expect(described_class.needs_landscape_hook?(component)).to be false
    end

    it 'returns true for landscape responsive' do
      component = {
        'type' => 'View',
        'responsive' => { 'landscape' => { 'orientation' => 'horizontal' } }
      }
      expect(described_class.needs_landscape_hook?(component)).to be true
    end

    it 'returns true when child has landscape responsive' do
      component = {
        'type' => 'View',
        'child' => [
          {
            'type' => 'Label',
            'responsive' => { 'landscape' => { 'fontSize' => 20 } }
          }
        ]
      }
      expect(described_class.needs_landscape_hook?(component)).to be true
    end
  end
end
