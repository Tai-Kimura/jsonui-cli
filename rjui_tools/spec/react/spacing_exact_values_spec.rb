# frozen_string_literal: true

require_relative '../spec_helper'
require_relative '../support/typescript_compiler'
require 'react/converters/view_converter'
require 'react/converters/button_converter'
require 'react/converters/segment_converter'
require 'react/responsive_helper'

# A declared spacing is drawn at its declared length (ticket
# rjui-spacing-rounds-to-the-tailwind-scale). Until jsonui-cli 1.9.14 every
# padding, margin and gap went through TailwindMapper.closest_padding, which
# rounded to the NEAREST step of Tailwind's spacing scale: paddingLeft 22 drew
# 20px (pl-5), 3 drew 2px (0.5), 5 and 7 drew 4px and 6px — on web only; iOS
# and Android draw the declared value. A spelling that missed the map
# (`PADDING_MAP[v] || v`: the View's gap, the responsive overrides, the
# Segment) wrote `gap-22`, which Tailwind v4 reads as 22 x 0.25rem = 88px.
# Every length is an arbitrary px value (16 -> p-[16px]), never a scale step
# (a rem, which follows the viewer's root font size), as the Collection's
# insets have been since 1.9.0.
RSpec.describe 'rjui spacing is the declared length' do
  C = RjuiTools::React::Converters
  TM = RjuiTools::React::TailwindMapper

  def spacing_classes(converter, extra, type, base = {})
    jsx = converter.new({ 'type' => type, 'id' => 'x' }.merge(base).merge(extra), { 'use_tailwind' => true }).convert
    jsx.scan(/className="([^"]*)"/).flatten.flat_map(&:split)
       .select { |c| c.match?(/\A-?(p[trblxyse]?|m[trblxyse]?|gap)-/) }
  end

  describe 'TailwindMapper.spacing_value' do
    it 'every length is its px value — a step of the old scale too' do
      expect(TM.spacing_value(16)).to eq('[16px]')
      expect(TM.spacing_value(16.0)).to eq('[16px]')
      expect(TM.spacing_value(1)).to eq('[1px]')
      expect(TM.spacing_value(0)).to eq('[0px]')
      expect(TM.spacing_value(22)).to eq('[22px]')
      expect(TM.spacing_value(3)).to eq('[3px]')
      expect(TM.spacing_value(2.5)).to eq('[2.5px]')
      expect(TM.spacing_value(100)).to eq('[100px]')
      expect(TM.spacing_value(nil)).to eq('[0px]')
    end
  end

  [['View', C::ViewConverter, {}], ['Button', C::ButtonConverter, { 'text' => 'B' }]].each do |type, converter, base|
    describe type do
      it 'paddings and margins, odd values and a four-element array, are exact' do
        expect(spacing_classes(converter, { 'padding' => 3 }, type, base)).to eq(%w[p-[3px]])
        expect(spacing_classes(converter, { 'paddingLeft' => 22, 'paddingTop' => 3 }, type, base))
          .to contain_exactly('pt-[3px]', 'pl-[22px]')
        expect(spacing_classes(converter, { 'paddings' => [1, 2, 3, 4] }, type, base))
          .to eq(%w[pt-[1px] pr-[2px] pb-[3px] pl-[4px]])
        expect(spacing_classes(converter, { 'margins' => [3, 22, 5, 7] }, type, base))
          .to eq(%w[mt-[3px] mr-[22px] mb-[5px] ml-[7px]])
      end

      it 'a step of the old scale is its px value too' do
        expect(spacing_classes(converter, { 'paddings' => [16, 8] }, type, base)).to eq(%w[py-[16px] px-[8px]])
      end
    end
  end

  it "the View's spacing is a gap of that length, not a step count" do
    expect(spacing_classes(C::ViewConverter, { 'orientation' => 'horizontal', 'spacing' => 22 }, 'View'))
      .to include('gap-[22px]')
    expect(spacing_classes(C::ViewConverter, { 'orientation' => 'horizontal', 'spacing' => 8 }, 'View'))
      .to include('gap-[8px]')
  end

  it 'the responsive overrides spell spacing the same way' do
    mappers = RjuiTools::React::ResponsiveHelper::ATTRIBUTE_MAPPERS
    expect(mappers['padding'].call(22, 'md:')).to eq('md:p-[22px]')
    expect(mappers['padding'].call([1, 2, 3, 22], 'md:')).to eq('md:pt-[1px] md:pr-[2px] md:pb-[3px] md:pl-[22px]')
    expect(mappers['padding'].call([3, 16], 'md:')).to eq('md:py-[3px] md:px-[16px]')
    expect(mappers['spacing'].call(22, 'md:')).to eq('md:gap-[22px]')
  end

  it "the Segment's vertical padding from its height is exact" do
    # The per-item button class is built in a template literal, so read the
    # whole emit: height 30 -> 30 / 4 = 7 -> py-[7px] (it wrote `py-7`, 28px).
    jsx = C::SegmentConverter.new({ 'type' => 'Segment', 'id' => 's', 'height' => 30, 'items' => %w[a b] },
                                  { 'use_tailwind' => true }).convert
    expect(jsx).to include('py-[7px]')
    expect(jsx).not_to match(/\bpy-7\b/)
  end

  it 'the emitted Views and Buttons type-check' do
    elements = [{ 'paddings' => [1, 2, 3, 22], 'margins' => [3, 22, 5, 7], 'spacing' => 22, 'orientation' => 'horizontal' }]
               .map { |e| C::ViewConverter.new({ 'type' => 'View', 'id' => 'v' }.merge(e), { 'use_tailwind' => true, 'typescript' => true }).convert } +
               [C::ButtonConverter.new({ 'type' => 'Button', 'id' => 'b', 'text' => 'B', 'paddings' => [3, 22] },
                                       { 'use_tailwind' => true, 'typescript' => true }).convert]
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript
  end
end
