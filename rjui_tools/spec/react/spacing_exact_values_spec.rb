# frozen_string_literal: true

require_relative '../spec_helper'
require 'bigdecimal'
require_relative '../support/typescript_compiler'
require 'react/converters/view_converter'
require 'react/converters/button_converter'
require 'react/converters/segment_converter'
require 'react/converters/collection_converter'
require 'react/responsive_helper'

# A declared spacing is drawn at its declared length (ticket
# rjui-spacing-rounds-to-the-tailwind-scale). Until jsonui-cli 1.9.14 every
# padding, margin and gap went through TailwindMapper.closest_padding, which
# rounded to the NEAREST step of Tailwind's spacing scale: paddingLeft 22 drew
# 20px (pl-5), 3 drew 2px (0.5), 5 and 7 drew 4px and 6px — on web only; iOS
# and Android draw the declared value. A spelling that missed the map
# (`PADDING_MAP[v] || v`: the View's gap, the responsive overrides, the
# Segment) wrote `gap-22`, which Tailwind v4 reads as 22 x 0.25rem = 88px.
# 1.9.14 wrote the exact length in px; 1.9.15 writes it in rem, N / 16
# (16 -> p-[1rem], 26 -> ml-[1.625rem]), so spacing follows the browser's
# default font size as the text's own rem classes do — the same pixels at the
# default 16px root (ticket rjui-spacing-px-does-not-follow-the-browser-font-
# size). Never a step of the scale, never rounded.
RSpec.describe 'rjui spacing is the declared length' do
  C = RjuiTools::React::Converters
  TM = RjuiTools::React::TailwindMapper

  def spacing_classes(converter, extra, type, base = {})
    jsx = converter.new({ 'type' => type, 'id' => 'x' }.merge(base).merge(extra), { 'use_tailwind' => true }).convert
    jsx.scan(/className="([^"]*)"/).flatten.flat_map(&:split)
       .select { |c| c.match?(/\A-?(p[trblxyse]?|m[trblxyse]?|gap)-/) }
  end

  describe 'TailwindMapper.spacing_value' do
    it 'every length is its rem value, N / 16 — a step of the old scale too' do
      expect(TM.spacing_value(16)).to eq('[1rem]')
      expect(TM.spacing_value(16.0)).to eq('[1rem]')
      expect(TM.spacing_value(26)).to eq('[1.625rem]')
      expect(TM.spacing_value(12)).to eq('[0.75rem]')
      expect(TM.spacing_value(1)).to eq('[0.0625rem]')
      expect(TM.spacing_value(0)).to eq('[0rem]')
      expect(TM.spacing_value(22)).to eq('[1.375rem]')
      expect(TM.spacing_value(3)).to eq('[0.1875rem]')
      expect(TM.spacing_value(2.5)).to eq('[0.15625rem]')
      expect(TM.spacing_value(100)).to eq('[6.25rem]')
      expect(TM.spacing_value(nil)).to eq('[0rem]')
    end

    # 1/16 terminates in decimal, and the division is done in BigDecimal, so
    # no length picks up a rounding tail: every rem written, times 16, is the
    # declared length exactly — integers and halves, 0..400.
    it 'is exact for every value, the odd ones too: rem x 16 == the declared px' do
      values = (0..400).to_a + (0..400).map { |n| n + 0.5 } + [0.25, 1.75, 33.3, 99.9]
      values.each do |v|
        written = TM.spacing_value(v)[/\A\[(-?[\d.]+)rem\]\z/, 1]
        expect(written).not_to be_nil, v.inspect
        expect(BigDecimal(written) * 16).to eq(BigDecimal(v.to_s)), "#{v} -> #{written}"
        expect(written).not_to match(/\d{12,}/), "#{v} -> #{written}: a float tail"
      end
    end

    it 'rem() writes the same value for CSS, and leaves a non-number as it was' do
      expect(TM.rem(26)).to eq('1.625rem')
      expect(TM.rem('10')).to eq('0.625rem')
      expect(TM.rem('auto')).to eq('autopx')
    end
  end

  [['View', C::ViewConverter, {}], ['Button', C::ButtonConverter, { 'text' => 'B' }]].each do |type, converter, base|
    describe type do
      it 'paddings and margins, odd values and a four-element array, are exact' do
        expect(spacing_classes(converter, { 'padding' => 3 }, type, base)).to eq(%w[p-[0.1875rem]])
        expect(spacing_classes(converter, { 'paddingLeft' => 22, 'paddingTop' => 3 }, type, base))
          .to contain_exactly('pt-[0.1875rem]', 'pl-[1.375rem]')
        expect(spacing_classes(converter, { 'paddings' => [1, 2, 3, 4] }, type, base))
          .to eq(%w[pt-[0.0625rem] pr-[0.125rem] pb-[0.1875rem] pl-[0.25rem]])
        expect(spacing_classes(converter, { 'margins' => [3, 22, 5, 7] }, type, base))
          .to eq(%w[mt-[0.1875rem] mr-[1.375rem] mb-[0.3125rem] ml-[0.4375rem]])
      end

      it 'a step of the old scale is its rem value too' do
        expect(spacing_classes(converter, { 'paddings' => [16, 8] }, type, base)).to eq(%w[py-[1rem] px-[0.5rem]])
      end
    end
  end

  it "the View's spacing is a gap of that length, not a step count" do
    expect(spacing_classes(C::ViewConverter, { 'orientation' => 'horizontal', 'spacing' => 22 }, 'View'))
      .to include('gap-[1.375rem]')
    expect(spacing_classes(C::ViewConverter, { 'orientation' => 'horizontal', 'spacing' => 8 }, 'View'))
      .to include('gap-[0.5rem]')
  end

  it 'the responsive overrides spell spacing the same way' do
    mappers = RjuiTools::React::ResponsiveHelper::ATTRIBUTE_MAPPERS
    expect(mappers['padding'].call(22, 'md:')).to eq('md:p-[1.375rem]')
    expect(mappers['padding'].call([1, 2, 3, 22], 'md:')).to eq('md:pt-[0.0625rem] md:pr-[0.125rem] md:pb-[0.1875rem] md:pl-[1.375rem]')
    expect(mappers['padding'].call([3, 16], 'md:')).to eq('md:py-[0.1875rem] md:px-[1rem]')
    expect(mappers['spacing'].call(22, 'md:')).to eq('md:gap-[1.375rem]')
  end

  it "the Segment's vertical padding from its height is exact" do
    # The per-item button class is built in a template literal, so read the
    # whole emit: height 30 -> 30 / 4 = 7 -> py-[0.4375rem] (it wrote `py-7`, 28px).
    jsx = C::SegmentConverter.new({ 'type' => 'Segment', 'id' => 's', 'height' => 30, 'items' => %w[a b] },
                                  { 'use_tailwind' => true }).convert
    expect(jsx).to include('py-[0.4375rem]')
    expect(jsx).not_to match(/\bpy-7\b/)
  end

  it "the Collection's list-style chrome spaces in rem too" do
    chrome = RjuiTools::React::Converters::CollectionConverter::LIST_STYLE_CHROME
    expect(chrome['insetgrouped']).to include('px-[1rem]', '[clip-path:inset(0_1rem_round_10px)]')
    expect(chrome['sidebar']).to include('px-[0.5rem]')
    expect(chrome.values.flatten.grep(/\A-?(p[trblxyse]?|m[trblxyse]?|gap)-\[[\d.]+px\]\z/)).to eq([])
  end

  # The chrome is drawn inside the declared box. insetGrouped's inset was a
  # margin, which moved the box: x 16 on web where the declaration and
  # Android put it at x 0 (frame-parity inventory 2026-10-05; ticket
  # rjui-insetgrouped-collection-moves-its-own-box).
  it "no list-style chrome moves the Collection's own box" do
    chrome = RjuiTools::React::Converters::CollectionConverter::LIST_STYLE_CHROME
    expect(chrome.values.flatten.grep(/\A-?m[trblxyse]?-/)).to eq([])
  end

  it 'the emitted Views and Buttons type-check' do
    elements = [{ 'paddings' => [1, 2, 3, 22], 'margins' => [3, 22, 5, 7], 'spacing' => 22, 'orientation' => 'horizontal' }]
               .map { |e| C::ViewConverter.new({ 'type' => 'View', 'id' => 'v' }.merge(e), { 'use_tailwind' => true, 'typescript' => true }).convert } +
               [C::ButtonConverter.new({ 'type' => 'Button', 'id' => 'b', 'text' => 'B', 'paddings' => [3, 22] },
                                       { 'use_tailwind' => true, 'typescript' => true }).convert]
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript
  end
end
