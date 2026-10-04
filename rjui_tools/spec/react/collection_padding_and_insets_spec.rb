# frozen_string_literal: true

require_relative '../spec_helper'
require_relative '../support/typescript_compiler'
require 'react/converters/collection_converter'

# A Collection's own padding is OUTSIDE its scroll and its insets are INSIDE
# (user ruling 2026-09-28, as iOS and both Compose paths draw them): with a
# padding declared, the node's box is a padding box around the scroll
# container. The box carries BaseConverter's classes (size, padding,
# background, visibility, …); the scroll container carries the cells' layout,
# the insets, and the id / test id / ref, so what scrolls is still the element
# the id names. Until jsonui-cli 1.9.0 both sat on the one scroll container and
# an inset's side class replaced the padding on that edge (padding 16 with
# insets [0, 0, 0, 30]: the first cell at x 30, not 46), and a bound inset's
# four inline edges replaced it on every edge.
#
# The drawn arm is conformance/hosts/web/scripts/collection_padding_probe.mjs
# (`npm run collection-padding-probe`): red on 47315eef for every shape that
# declares a padding, green with this change.
RSpec.describe RjuiTools::React::Converters::CollectionConverter do
  def convert(extra, config = {})
    described_class.new({ 'type' => 'Collection', 'id' => 'c', 'testId' => 't', 'width' => 300, 'height' => 100,
                          'background' => '#EEEEEE', 'items' => '@{rows}',
                          'sections' => [{ 'cell' => 'ACell' }] }.merge(extra),
                        { 'use_tailwind' => true }.merge(config)).convert_node
  end

  # The opening tags of the emitted elements that are not a cell, in order.
  def boxes(jsx)
    jsx.lines.map(&:strip).select { |l| l.start_with?('<div') }
  end

  def classes(tag)
    (tag[/className="([^"]*)"/, 1] || tag[/className=\{`([^`]*)`\}/, 1]).split
  end

  def padding(tag)
    classes(tag).select { |c| c.match?(/\A(p[trblxy]?|scroll-p[trbl]?)-/) }
  end

  it 'padding only: a padding box around the scroll container' do
    box, scroller = boxes(convert('padding' => 16))
    expect(padding(box)).to eq(%w[p-[1rem]])
    expect(classes(box)).to include('w-[300px]', 'h-[100px]', 'bg-[#EEEEEE]', 'flex', 'flex-col')
    expect(box).not_to include('id=')
    expect(padding(scroller)).to eq([])
    expect(classes(scroller)).to include('flex-1', 'min-h-0', 'min-w-0', 'overflow-y-auto')
    expect(scroller).to include('id="c"', 'data-testid="t"')
  end

  it 'insets only: one box, as before' do
    jsx = convert('insets' => [0, 0, 0, 30])
    expect(boxes(jsx).size).to eq(1)
    expect(padding(boxes(jsx).first)).to eq(%w[pl-[1.875rem]])
    expect(classes(boxes(jsx).first)).to include('w-[300px]', 'bg-[#EEEEEE]', 'overflow-y-auto')
  end

  it 'both, static: the padding on the box, the insets on the scroll container' do
    box, scroller = boxes(convert('padding' => 16, 'insets' => [0, 0, 0, 30]))
    expect(padding(box)).to eq(%w[p-[1rem]])
    expect(padding(scroller)).to eq(%w[pl-[1.875rem]])
  end

  it 'a bound inset writes its four edges on the scroll container, not over the padding' do
    box, scroller = boxes(convert('padding' => 16, 'insets' => ['@{top}', 0, 0, 30]))
    expect(padding(box)).to eq(%w[p-[1rem]])
    expect(box).not_to include('style=')
    expect(scroller).to include('paddingTop: `${Number((Number(data.top) || 0)) / 16}rem`', "paddingLeft: '1.875rem'")
  end

  it 'per-edge padding with insets, and paddings with insetHorizontal' do
    box, scroller = boxes(convert('paddingLeft' => 12, 'insets' => [0, 0, 0, 30]))
    expect(padding(box)).to eq(%w[pl-[0.75rem]])
    expect(padding(scroller)).to eq(%w[pl-[1.875rem]])

    box, scroller = boxes(convert('paddings' => [8, 16], 'insetHorizontal' => 10))
    expect(padding(box)).to eq(%w[py-[0.5rem] px-[1rem]])
    expect(padding(scroller)).to eq(%w[pr-[0.625rem] pl-[0.625rem]])
  end

  it 'a bound padding is the box\'s inline style' do
    box, scroller = boxes(convert('padding' => '@{pad}', 'insets' => [0, 0, 0, 30]))
    expect(box).to include('style={{ padding: `${Number(data.pad) / 16}rem` }}')
    expect(scroller).not_to include('style=')
    expect(padding(scroller)).to eq(%w[pl-[1.875rem]])
  end

  it 'a padding that pads nothing keeps one box' do
    [0, [0, 0], '0|0'].each do |value|
      expect(boxes(convert('padding' => value)).size).to eq(1), value.inspect
    end
  end

  it 'the cells\' layout, the ref and the scroll handler stay on the scroll container' do
    jsx = convert('padding' => 8, 'orientation' => 'horizontal', 'gravity' => 'center', 'direction' => 'rightToLeft',
                  'paging' => true, 'currentPage' => '@{page}')
    box, scroller = boxes(jsx)
    expect(classes(box)).not_to include('items-center', 'justify-center', 'flex-row', 'flex-row-reverse')
    expect(classes(scroller)).to include('items-center', 'flex-row-reverse', 'snap-x', 'overflow-x-auto')
    expect(scroller).to include('ref={cRef}', 'onScroll=')
  end

  it 'visibility, enabled and hidden bindings go on the padding box' do
    jsx = convert('padding' => 8, 'visibility' => '@{vis}', 'enabled' => '@{on}', 'hidden' => '@{off}')
    expect(jsx).to start_with('  {data.vis !== "gone" && (')
    box, scroller = boxes(jsx)
    expect(box).to include('invisible', 'opacity-50')
    expect(scroller).not_to include('invisible', 'opacity-50')
    gone = classes(boxes(convert('padding' => 8, 'visibility' => 'gone')).first)
    expect(gone).to include('hidden')
    expect(gone).not_to include('flex')
  end

  it 'the Collections it emits type-check' do
    ambient = <<~TS
      declare const data: { top?: number; pad?: number; page?: number; onPageChange?: (page: number) => void;
                            rows?: { sections?: { cells?: { data: Record<string, unknown>[] } }[] } };
      declare const cRef: React.RefObject<HTMLDivElement | null>;
      declare function currentCollectionPage(el: HTMLElement | null, horizontal: boolean): number;
      type ACellData = Record<string, unknown>;
      declare const ACell: (props: { key?: string | number; id?: string; data: ACellData }) => JSX.Element;
    TS
    elements = [{ 'padding' => 16, 'insets' => ['@{top}', 0, 0, 30] }, { 'padding' => '@{pad}', 'insetHorizontal' => 4 },
                { 'paddingLeft' => 12, 'layout' => 'horizontal', 'paging' => true, 'currentPage' => '@{page}' }]
               .map { |e| convert(e, 'typescript' => true) }
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(ambient)
  end
end
