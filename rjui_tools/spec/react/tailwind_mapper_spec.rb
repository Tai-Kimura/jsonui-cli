# frozen_string_literal: true

require_relative '../spec_helper'
require 'react/tailwind_mapper'

RSpec.describe RjuiTools::React::TailwindMapper do
  describe '.map_min_width' do
    it 'returns min-w-full for matchParent' do
      expect(described_class.map_min_width('matchParent')).to eq('min-w-full')
    end

    it 'returns min-w-[Npx] for numeric value' do
      expect(described_class.map_min_width(100)).to eq('min-w-[100px]')
    end

    it 'returns empty string for nil' do
      expect(described_class.map_min_width(nil)).to eq('')
    end

    it 'returns empty string for unknown value' do
      expect(described_class.map_min_width('unknown')).to eq('')
    end
  end

  describe '.map_max_width' do
    it 'returns max-w-full for matchParent' do
      expect(described_class.map_max_width('matchParent')).to eq('max-w-full')
    end

    it 'returns max-w-[Npx] for numeric value' do
      expect(described_class.map_max_width(200)).to eq('max-w-[200px]')
    end

    it 'returns empty string for nil' do
      expect(described_class.map_max_width(nil)).to eq('')
    end
  end

  describe '.map_min_height' do
    it 'returns min-h-full for matchParent' do
      expect(described_class.map_min_height('matchParent')).to eq('min-h-full')
    end

    it 'returns min-h-[Npx] for numeric value' do
      expect(described_class.map_min_height(50)).to eq('min-h-[50px]')
    end

    it 'returns empty string for nil' do
      expect(described_class.map_min_height(nil)).to eq('')
    end
  end

  describe '.map_max_height' do
    it 'returns max-h-full for matchParent' do
      expect(described_class.map_max_height('matchParent')).to eq('max-h-full')
    end

    it 'returns max-h-[Npx] for numeric value' do
      expect(described_class.map_max_height(300)).to eq('max-h-[300px]')
    end

    it 'returns empty string for nil' do
      expect(described_class.map_max_height(nil)).to eq('')
    end
  end

  describe '.map_rtl_paddings' do
    it 'maps paddingStart to ps- class' do
      expect(described_class.map_rtl_paddings(16, nil)).to eq('ps-4')
    end

    it 'maps paddingEnd to pe- class' do
      expect(described_class.map_rtl_paddings(nil, 8)).to eq('pe-2')
    end

    it 'maps both paddingStart and paddingEnd' do
      expect(described_class.map_rtl_paddings(16, 8)).to eq('ps-4 pe-2')
    end

    it 'returns empty string when both are nil' do
      expect(described_class.map_rtl_paddings(nil, nil)).to eq('')
    end
  end

  describe '.map_rtl_margins' do
    it 'maps startMargin to ms- class' do
      expect(described_class.map_rtl_margins(16, nil)).to eq('ms-4')
    end

    it 'maps endMargin to me- class' do
      expect(described_class.map_rtl_margins(nil, 8)).to eq('me-2')
    end

    it 'maps both startMargin and endMargin' do
      expect(described_class.map_rtl_margins(16, 8)).to eq('ms-4 me-2')
    end

    it 'returns empty string when both are nil' do
      expect(described_class.map_rtl_margins(nil, nil)).to eq('')
    end
  end

  describe '.map_insets' do
    it 'delegates to map_padding for array format' do
      expect(described_class.map_insets([16, 8])).to eq('py-4 px-2')
    end

    it 'delegates to map_padding for single value' do
      expect(described_class.map_insets(16)).to eq('p-4')
    end
  end

  describe '.map_inset_horizontal' do
    it 'maps to px- class' do
      expect(described_class.map_inset_horizontal(16)).to eq('px-4')
    end

    it 'returns empty string for nil' do
      expect(described_class.map_inset_horizontal(nil)).to eq('')
    end

    it 'finds closest Tailwind value' do
      expect(described_class.map_inset_horizontal(15)).to eq('px-3.5')  # 15 is closer to 14 (px-3.5)
    end
  end

  describe '.map_padding' do
    context 'with single value' do
      it 'maps to p- class' do
        expect(described_class.map_padding(16)).to eq('p-4')
      end
    end

    context 'with 2-element array' do
      it 'maps to py- and px- classes' do
        expect(described_class.map_padding([16, 8])).to eq('py-4 px-2')
      end
    end

    context 'with 4-element array' do
      it 'maps to individual padding classes' do
        result = described_class.map_padding([16, 8, 4, 12])
        expect(result).to include('pt-4')
        expect(result).to include('pr-2')
        expect(result).to include('pb-1')
        expect(result).to include('pl-3')
      end
    end
  end

  describe '.map_margin' do
    context 'with single value' do
      it 'maps to m- class' do
        expect(described_class.map_margin(16)).to eq('m-4')
      end
    end

    context 'with 2-element array' do
      it 'maps to my- and mx- classes' do
        expect(described_class.map_margin([16, 8])).to eq('my-4 mx-2')
      end
    end

    context 'with 4-element array' do
      it 'maps to individual margin classes' do
        result = described_class.map_margin([16, 8, 4, 12])
        expect(result).to include('mt-4')
        expect(result).to include('mr-2')
        expect(result).to include('mb-1')
        expect(result).to include('ml-3')
      end
    end
  end

  describe '.map_individual_paddings' do
    it 'maps individual padding values' do
      result = described_class.map_individual_paddings(16, 8, 4, 12)
      expect(result).to include('pt-4')
      expect(result).to include('pr-2')
      expect(result).to include('pb-1')
      expect(result).to include('pl-3')
    end

    it 'handles partial values' do
      result = described_class.map_individual_paddings(16, nil, nil, nil)
      expect(result).to eq('pt-4')
    end

    it 'returns empty string when all nil' do
      expect(described_class.map_individual_paddings(nil, nil, nil, nil)).to eq('')
    end
  end

  describe '.map_individual_margins' do
    it 'maps individual margin values' do
      result = described_class.map_individual_margins(16, 8, 4, 12)
      expect(result).to include('mt-4')
      expect(result).to include('mr-2')
      expect(result).to include('mb-1')
      expect(result).to include('ml-3')
    end

    it 'handles partial values' do
      result = described_class.map_individual_margins(nil, nil, 8, nil)
      expect(result).to eq('mb-2')
    end
  end

  describe '.map_opacity' do
    it 'maps opacity values to Tailwind classes' do
      expect(described_class.map_opacity(0.5)).to eq('opacity-50')
    end

    it 'finds closest Tailwind value' do
      expect(described_class.map_opacity(0.55)).to eq('opacity-60')  # 0.55 is closer to 0.6
    end

    it 'returns empty string for nil' do
      expect(described_class.map_opacity(nil)).to eq('')
    end
  end

  describe '.map_z_index' do
    it 'maps standard z-index values' do
      expect(described_class.map_z_index(10)).to eq('z-10')
      expect(described_class.map_z_index(50)).to eq('z-50')
    end

    it 'uses arbitrary value for non-standard z-index' do
      expect(described_class.map_z_index(15)).to eq('z-[15]')
    end

    it 'returns empty string for nil' do
      expect(described_class.map_z_index(nil)).to eq('')
    end
  end

  describe '.map_flex_grow' do
    it 'maps weight 0 to flex-none (no min-*-0 needed)' do
      expect(described_class.map_flex_grow(0)).to eq('flex-none')
    end

    it 'maps weight 1 to flex-1 min-w-0 min-h-0' do
      # min-w-0 / min-h-0 pair with flex-1 to neutralize CSS
      # `min-*-size: auto` so long descendants don't push the flex
      # container past its weight slice (rjui-flex-grow-missing-min-w-0).
      expect(described_class.map_flex_grow(1)).to eq('flex-1 min-w-0 min-h-0')
    end

    it 'uses arbitrary value for other weights with min-*-0 pair' do
      expect(described_class.map_flex_grow(2)).to eq('flex-[2] min-w-0 min-h-0')
    end

    it 'returns empty string for nil' do
      expect(described_class.map_flex_grow(nil)).to eq('')
    end
  end

  describe '.map_font' do
    context 'with weight names' do
      it 'maps bold to font-bold' do
        expect(described_class.map_font('bold')).to eq('font-bold')
      end

      it 'maps semibold to font-semibold' do
        expect(described_class.map_font('semibold')).to eq('font-semibold')
      end

      it 'maps medium to font-medium' do
        expect(described_class.map_font('medium')).to eq('font-medium')
      end

      it 'maps light to font-light' do
        expect(described_class.map_font('light')).to eq('font-light')
      end

      it 'is case insensitive' do
        expect(described_class.map_font('BOLD')).to eq('font-bold')
        expect(described_class.map_font('Bold')).to eq('font-bold')
      end
    end

    context 'with font family names' do
      it 'maps monospace to font-mono' do
        expect(described_class.map_font('monospace')).to eq('font-mono')
      end

      it 'maps mono to font-mono' do
        expect(described_class.map_font('mono')).to eq('font-mono')
      end

      it 'maps sans to font-sans' do
        expect(described_class.map_font('sans')).to eq('font-sans')
      end

      it 'maps serif to font-serif' do
        expect(described_class.map_font('serif')).to eq('font-serif')
      end
    end

    context 'with unknown font' do
      it 'returns empty string for custom font names' do
        expect(described_class.map_font('Helvetica')).to eq('')
      end
    end

    context 'with nil' do
      it 'returns empty string' do
        expect(described_class.map_font(nil)).to eq('')
      end
    end
  end
end

# rjui-offpalette-hex-dead-tailwind-class: only theme-safe (mode-complete)
# names may become `bg-<name>` classes; everything else resolves to its hex.
RSpec.describe RjuiTools::React::TailwindMapper, '.map_color (theme-safe policy)' do
  after { described_class.reset_palette! }

  it 'emits arbitrary value for hex' do
    expect(described_class.map_color('#DBEAFE')).to eq('bg-[#DBEAFE]')
  end

  it 'keeps legacy name behavior when no palette is configured' do
    expect(described_class.map_color('surface', 'text')).to eq('text-surface')
  end

  context 'with a configured palette' do
    before do
      described_class.configure_palette(
        theme_safe: ['surface'],
        fallbacks: { 'surface' => '#FFFFFF', 'white_2' => '#FFFBEB' }
      )
    end

    it 'emits the class for a theme-safe name' do
      expect(described_class.map_color('surface')).to eq('bg-surface')
    end

    it 'resolves an off-palette name back to its hex (visible, not dead)' do
      expect(described_class.map_color('white_2')).to eq('bg-[#FFFBEB]')
    end

    it 'resolves with the requested prefix' do
      expect(described_class.map_color('white_2', 'border')).to eq('border-[#FFFBEB]')
    end

    it 'passes through a name absent from colors.json entirely' do
      expect(described_class.map_color('some-custom-class')).to eq('bg-some-custom-class')
    end
  end
end
