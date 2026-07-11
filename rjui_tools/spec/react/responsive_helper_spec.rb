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

    # Regression: rjui-responsive-compact-overrides-emitted-unprefixed —
    # the helper emits ONLY breakpoint-scoped override classes. Base values
    # are emitted unprefixed by the converters' normal attribute mapping;
    # re-emitting them here duplicated the class (p-5 ... p-5 p-4).
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

        expect(result[:classes]).to include('lg:flex-row')
        expect(result[:classes]).not_to include('flex-col')
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

        expect(result[:classes]).to include('lg:gap-6')
        expect(result[:classes]).not_to include('gap-2')
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

        expect(result[:classes]).to include('lg:text-xl')
        expect(result[:classes]).not_to include('text-sm')
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

        # Base `hidden` comes from build_class_name's normal visibility
        # handling; the helper contributes only the scoped override.
        expect(result[:classes]).to include('lg:block')
        expect(result[:classes]).not_to include('hidden')
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

        expect(result[:classes]).to include('lg:w-[300px]')
        expect(result[:classes]).not_to include('w-full')
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

        expect(result[:classes]).to include('lg:bg-[#000000]')
        expect(result[:classes]).not_to include('bg-[#FFFFFF]')
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

        expect(result[:classes]).to include('lg:text-center')
        expect(result[:classes]).not_to include('text-left')
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

        expect(result[:classes]).to include('md:flex-row')
        expect(result[:classes]).not_to include('flex-col')
      end
    end

    # Regression: rjui-responsive-compact-overrides-emitted-unprefixed —
    # compact overrides are scoped below the md breakpoint (max-md:), NOT
    # emitted unprefixed (which applied them at every width and collided
    # with the base classes).
    context 'with compact (max-md:) breakpoint' do
      it 'scopes orientation override below md' do
        component = {
          'type' => 'View',
          'orientation' => 'horizontal',
          'responsive' => {
            'compact' => { 'orientation' => 'vertical' }
          }
        }
        result = described_class.build_responsive(component)

        expect(result[:classes]).to include('max-md:flex-col')
        expect(result[:classes]).not_to include('flex-col')
        expect(result[:classes]).not_to include('flex-row')
      end

      it 'emits max-md:hidden for compact visibility gone' do
        component = {
          'type' => 'View',
          'responsive' => {
            'compact' => { 'visibility' => 'gone' }
          }
        }
        result = described_class.build_responsive(component)

        expect(result[:classes]).to include('max-md:hidden')
        expect(result[:classes]).not_to include('hidden')
      end

      it 'scopes padding override below md' do
        component = {
          'type' => 'View',
          'padding' => 20,
          'responsive' => {
            'compact' => { 'padding' => 16 }
          }
        }
        result = described_class.build_responsive(component)

        expect(result[:classes]).to include('max-md:p-4')
        expect(result[:classes]).not_to include('p-5')
        expect(result[:classes]).not_to include('p-4')
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

        # Medium breakpoint
        expect(result[:classes]).to include('md:flex-row')
        expect(result[:classes]).to include('md:gap-3')

        # Regular breakpoint
        expect(result[:classes]).to include('lg:flex-row')
        expect(result[:classes]).to include('lg:gap-6')

        # Base values are NOT re-emitted by the helper
        expect(result[:classes]).not_to include('flex-col')
        expect(result[:classes]).not_to include('gap-1')
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

        expect(result[:classes]).to include('lg:p-4')
        expect(result[:classes]).not_to include('p-2')
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

        expect(result[:classes]).to include('lg:py-4 lg:px-8')
        expect(result[:classes]).not_to include('py-2 px-4')
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
