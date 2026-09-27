# frozen_string_literal: true

require 'swiftui/views/collection_converter'
require_relative '../../support/emitted_swift'

# A Collection's insets are padding around the cells, inside its scroll (the
# SSoT's Collection.insets) — on the List routes and the pager too, from
# jsonui-cli 1.9.0 (4f round 6). A List pads its rows with safe-area padding
# on the List, which stays the Collection's size, on top of its own row insets;
# a pager pads the cell on every page (a page is the pager's size). With
# insetHorizontal / insetVertical added, per edge. Until jsonui-cli 1.9.0
# neither List route read the insets, and the pager padded its TabView from
# outside: measured on the ConformanceHost (iOS 26.5), a 300-wide pager with
# insets [0, 0, 0, 30] turned its pages in a 270-wide scroll 30pt in.
#
# The drawn arm is InsetsOrderProbeUITests (the list_*, listclass_* and
# pager_* rows) in SwiftJsonUI's ConformanceHost; the Dynamic half is
# CollectionConverter.applyListContentInsets and
# PagingCollectionWrapperView.pageInsets.
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  include EmittedSwift

  before(:all) { described_class.superclass.validation_enabled = false }
  after(:all) { described_class.superclass.validation_enabled = true }

  def emit(extra)
    described_class.new({ 'type' => 'Collection', 'id' => 'list', 'width' => 300, 'height' => 80, 'items' => '@{rows}' }.merge(extra)).convert.to_s
  end

  def padding_lines(extra)
    emit(extra).lines.map(&:strip).grep(/\A\.(padding|safeAreaPadding)/)
  end

  # Methods, not constants: a constant in a describe block is top-level, and
  # other specs name theirs PAGER too.
  def sectioned_list = { 'sections' => [{ 'cell' => 'ACell' }], 'listStyle' => 'plain' }
  def class_list = { 'cellClasses' => ['ACell'] }
  def pager = { 'sections' => [{ 'cell' => 'ACell' }], 'layout' => 'horizontal', 'paging' => true }

  it 'a sectioned List pads its rows inside the List, insetHorizontal / insetVertical added' do
    expect(padding_lines(sectioned_list.merge('insets' => [0, 0, 0, 30])))
      .to eq(['.safeAreaPadding(EdgeInsets(top: 0, leading: 30, bottom: 0, trailing: 0))'])
    expect(padding_lines(sectioned_list.merge('insets' => '4|20', 'insetHorizontal' => 2, 'insetVertical' => 1)))
      .to eq(['.safeAreaPadding(EdgeInsets(top: 5, leading: 22, bottom: 5, trailing: 22))'])
  end

  it 'the class-list List pads its rows inside the List' do
    expect(padding_lines(class_list.merge('insets' => [10]))).to eq(['.safeAreaPadding(EdgeInsets(top: 10, leading: 10, bottom: 10, trailing: 10))'])
  end

  it 'a pager pads the cell on every page, after its address, and not its TabView' do
    code = emit(pager.merge('insets' => [0, 0, 0, 30], 'insetVertical' => 2))
    expect(padding_lines(pager.merge('insets' => [0, 0, 0, 30], 'insetVertical' => 2)))
      .to eq(['.padding(EdgeInsets(top: 2, leading: 30, bottom: 2, trailing: 0))'])
    lines = code.lines.map(&:strip)
    expect(lines.index('.padding(EdgeInsets(top: 2, leading: 30, bottom: 2, trailing: 0))'))
      .to eq(lines.index { |l| l.start_with?('.accessibilityIdentifier("list_item_') } + 1)
  end

  it 'control: no insets, no padding' do
    [sectioned_list, class_list, pager].each do |shape|
      expect(padding_lines(shape)).to eq([]), shape.inspect
    end
  end

  # The pager without its iOS-only page style, as collection_paging_pages_spec
  # type-checks it (the suite's compile arm runs on the macOS SDK).
  it 'type-checks the padding it emits, the page style aside', :swift_compile do
    stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + cell_view_stub('ACellView')
    codes = [emit(sectioned_list.merge('insets' => [0, 0, 0, 30])), emit(class_list.merge('insets' => [10])),
             emit(pager.merge('insets' => [0, 0, 0, 30], 'insetVertical' => 2))]
    codes = codes.map { |code| code.lines.reject { |l| l.include?('.tabViewStyle(.page(') }.join }
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}", data: ['var rows: CollectionDataSource? = nil'], stubs: stubs))
      .to compile_as_swift
  end
end
