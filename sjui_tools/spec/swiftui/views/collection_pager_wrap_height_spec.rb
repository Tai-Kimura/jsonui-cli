# frozen_string_literal: true

require 'swiftui/views/collection_converter'
require_relative '../../support/emitted_swift'

# A pager (horizontal, paging) with height wrapContent is as tall as the page it
# shows, as KotlinJsonUI's HorizontalPager(...wrapContentHeight()) is. A
# page-style TabView has no height of its own: in a vertical ScrollView it took
# the height the ScrollView had left (309 of 420 on SwiftJsonUI's
# ConformanceHost) and asked its ideal size it is 0 — 378pt of cards measured
# 40.7pt with the label above and below (ticket
# 2026-10-23-sjui-paging-collection-wrapcontent-height-collapses-in-scrollview).
# Each page is measured at its own height (fixedSize, onGeometryChange) into a
# state of the view's, and the TabView is framed at the shown page's height;
# a pager with no page state of its own gets one (the frame needs the page).
#
# The drawn arm is PagerHeightProbeUITests in SwiftJsonUI's ConformanceHost
# (the codegen half: this emission; the Dynamic half: CollectionConverter's
# paging route).
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  include EmittedSwift

  before(:all) { described_class.superclass.validation_enabled = false }
  after(:all) { described_class.superclass.validation_enabled = true }

  def converter(extra)
    described_class.new({ 'type' => 'Collection', 'id' => 'cards', 'width' => 'matchParent', 'items' => '@{rows}',
                          'sections' => [{ 'cell' => 'ACell' }], 'layout' => 'horizontal', 'paging' => true }.merge(extra))
  end

  def lines(conv)
    conv.convert.to_s.lines.map(&:strip)
  end

  it 'height wrapContent: each page measured, the pager framed at the shown page, a page state of its own' do
    conv = converter('height' => 'wrapContent')
    got = lines(conv)
    expect(conv.state_variables).to include('@State private var cardsPageHeights: [Int: CGFloat] = [:]', '@State private var cardsScrollPage: Int = 0')
    expect(got).to include('TabView(selection: $cardsScrollPage) {')
    expect(got).to include('.fixedSize(horizontal: false, vertical: true)',
                           '.onGeometryChange(for: CGFloat.self) { $0.size.height } action: { cardsPageHeights[cellIndex] = $0 }',
                           '.frame(maxHeight: .infinity, alignment: .top)')
    expect(got).to include('.frame(height: cardsPageHeights[cardsScrollPage] ?? cardsPageHeights.values.max())')
    # the page measured before it is tagged; the pager framed after its page style
    expect(got.index { |l| l.start_with?('.onGeometryChange') }).to be < got.index(".tag(cellIndex)")
    expect(got.index { |l| l.start_with?('.frame(height: cardsPageHeights') }).to be > got.index('.tabViewStyle(.page(indexDisplayMode: .never))')
  end

  it 'a bound currentPage is the shown page: no page state of its own' do
    conv = converter('height' => 'wrapContent', 'currentPage' => '@{page}')
    expect(conv.state_variables.grep(/ScrollPage/)).to eq([])
    expect(lines(conv)).to include('.frame(height: cardsPageHeights[data.page] ?? cardsPageHeights.values.max())')
  end

  it 'control: any other height draws as before — no measure, no frame, no state' do
    [{}, { 'height' => 'matchParent' }, { 'height' => 200 }].each do |extra|
      conv = converter(extra)
      code = conv.convert.to_s
      expect(code).not_to include('onGeometryChange'), extra.inspect
      expect(code).not_to include('PageHeights'), extra.inspect
      expect(conv.state_variables).to eq([]), extra.inspect
    end
  end

  # The pager without its iOS-only page style (the suite's compile arm runs on
  # the macOS SDK), in a view that holds the emitted states.
  it 'type-checks what it emits, the page style aside', :swift_compile do
    conv = converter('height' => 'wrapContent')
    code = conv.convert.to_s.lines.reject { |l| l.include?('.tabViewStyle(.page(') }.join
    states = conv.state_variables.map { |s| "    #{s}" }.join("\n")
    swift = compilable_view("VStack {\n#{code}\n}", data: ['var rows: CollectionDataSource? = nil'],
                                                     stubs: EmittedSwift::COLLECTION_DATA_SOURCE_STUB + cell_view_stub('ACellView'))
    swift = swift.sub("    let data = TestData()\n", "    let data = TestData()\n#{states}\n")
    expect(swift).to compile_as_swift
  end
end
