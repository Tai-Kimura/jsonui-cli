# frozen_string_literal: true

require_relative '../spec_helper'
require_relative '../support/typescript_compiler'
require 'react/converters/collection_converter'

# A Collection's insets are padding around the cells, inside its scroll — its
# own box, the scroll container (the SSoT's Collection.insets): 1, 2 or 4
# values, an array or a `|` string, read as `paddings` reads them; any other
# value pads nothing. insetHorizontal and insetVertical are ADDED per edge, as
# iOS and both Compose paths draw them, and the values are exact (4f round 6,
# jsonui-cli 1.9.0). Measured in Chromium (300 x 60 Collections): until then
# rjui rounded them to Tailwind's spacing scale (insets [0, 0, 0, 30] put the
# first cell at 28), four values replaced insetHorizontal / insetVertical, two
# lost to insetHorizontal ([4, 20] with insetHorizontal 10: 20), the string
# form padded nothing, a bound value in the array stopped the whole layout,
# and a pager rested scrolled past its leading inset (its snap point was the
# box's edge).
#
# The drawn arm is conformance/hosts/web/scripts/collection_insets_probe.mjs
# (`npm run collection-insets-probe`).
RSpec.describe RjuiTools::React::Converters::CollectionConverter do
  def convert(extra, config = {})
    described_class.new({ 'type' => 'Collection', 'id' => 'c', 'width' => 300, 'height' => 60, 'items' => '@{rows}',
                          'sections' => [{ 'cell' => 'ACell' }] }.merge(extra), { 'use_tailwind' => true }.merge(config)).convert
  end

  def padding(extra)
    convert(extra)[/className="([^"]*)"/, 1].split.select { |c| c.match?(/\A(p[trbl]?|p[xy]|scroll-p[trbl]?)-/) }
  end

  it 'four values are [top, right, bottom, left], exact' do
    expect(padding('insets' => [0, 0, 0, 30])).to eq(%w[pl-[30px]])
    expect(padding('insets' => [1, 2, 3, 4])).to eq(%w[pt-[1px] pr-[2px] pb-[3px] pl-[4px]])
    expect(padding('insets' => [2.5, 0, 0, 0])).to eq(%w[pt-[2.5px]])
  end

  it 'the string form, one value and two values' do
    expect(padding('insets' => '1|2|3|4')).to eq(%w[pt-[1px] pr-[2px] pb-[3px] pl-[4px]])
    expect(padding('insets' => '6|30')).to eq(%w[pt-[6px] pr-[30px] pb-[6px] pl-[30px]])
    expect(padding('insets' => [10])).to eq(%w[pt-[10px] pr-[10px] pb-[10px] pl-[10px]])
  end

  it 'insetHorizontal and insetVertical are added per edge' do
    expect(padding('insets' => [4, 20], 'insetHorizontal' => 10)).to eq(%w[pt-[4px] pr-[30px] pb-[4px] pl-[30px]])
    expect(padding('insets' => [2, 0, 0, 30], 'insetHorizontal' => 4, 'insetVertical' => 8))
      .to eq(%w[pt-[10px] pr-[4px] pb-[8px] pl-[34px]])
    expect(padding('insetHorizontal' => 13)).to eq(%w[pr-[13px] pl-[13px]])
  end

  it 'any other value pads nothing' do
    [[1, 2, 3], 'a|b', '1|x|2|3', [], ''].each do |value|
      expect(padding('insets' => value)).to eq([]), value.inspect
    end
  end

  it 'a pager keeps its snap points inside the insets' do
    expect(padding('layout' => 'horizontal', 'paging' => true, 'insets' => [0, 0, 0, 30])).to eq(%w[pl-[30px] scroll-pl-[30px]])
  end

  it 'a bound value in the array: the four edges inline' do
    jsx = convert('insets' => ['@{top}', 0, 0, 30], 'insetVertical' => 2)
    expect(jsx).to include('paddingTop: `${((Number(data.top) || 0) + 2)}px`')
    expect(jsx).to include("paddingLeft: '30px'")
    expect(jsx).to include("paddingBottom: '2px'")
  end

  it 'the Collections it emits type-check' do
    ambient = <<~TS
      declare const data: { top?: number; rows?: { sections?: { cells?: { data: Record<string, unknown>[] } }[] } };
      type ACellData = Record<string, unknown>;
      declare const ACell: (props: { key?: string | number; id?: string; data: ACellData }) => JSX.Element;
    TS
    elements = [{ 'insets' => ['@{top}', 0, 0, 30], 'insetVertical' => 2 }, { 'insets' => '6|30', 'insetHorizontal' => 4 },
                { 'layout' => 'horizontal', 'paging' => true, 'insets' => [0, 0, 0, 30] }].map { |e| convert(e, 'typescript' => true) }
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(ambient)
  end
end
