# frozen_string_literal: true

require 'swiftui/views/collection_converter'
require_relative '../../support/emitted_swift'

# A horizontal scrolling Collection of wrapContent (or undeclared) height is
# its cells' height, capped by its parent — across its scroll axis, as
# CollectionContentFit sizes it along (4f 2026-09-27; the SSoT's wrapContent
# is "size to content"). A LazyHStack takes the height it is offered, so until
# jsonui-cli 1.9.0 a lazy row filled its parent (99 of a 120pt View whose label
# took the rest) where the eager row was its cells' 28 (ConformanceHost,
# generated and Dynamic alike). CollectionContentFit(axis:along:across:) is
# SwiftJsonUI 10.29.0's.
#
# The drawn arm is RowCrossFitProbeUITests in SwiftJsonUI's ConformanceHost.
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  include EmittedSwift

  before(:all) { described_class.superclass.validation_enabled = false }
  after(:all) { described_class.superclass.validation_enabled = true }

  def emit(extra)
    described_class.new({ 'type' => 'Collection', 'id' => 'list', 'layout' => 'horizontal', 'items' => '@{rows}',
                          'sections' => [{ 'cell' => 'ACell' }] }.merge(extra).compact).convert.to_s
  end

  it 'a row of wrapContent or undeclared height fits across; of wrapContent width, along too' do
    expect(emit('width' => 'matchParent')).to include('CollectionContentFit(axis: .horizontal, along: false, across: true) {')
    expect(emit('width' => 'matchParent', 'height' => 'wrapContent')).to include('CollectionContentFit(axis: .horizontal, along: false, across: true) {')
    expect(emit('width' => 'wrapContent')).to include('CollectionContentFit(axis: .horizontal, across: true) {')
  end

  it 'control: a declared height, the pager and a vertical column are as before' do
    expect(emit('width' => 'wrapContent', 'height' => 40)).to include('CollectionContentFit(axis: .horizontal) {')
    expect(emit('width' => 'matchParent', 'height' => 40)).not_to include('CollectionContentFit')
    expect(emit('width' => 'matchParent', 'paging' => true)).not_to include('CollectionContentFit')
    expect(emit('layout' => 'vertical', 'width' => 'matchParent', 'height' => 'wrapContent', 'columns' => 2))
      .to include('CollectionContentFit(axis: .vertical) {')
  end

  it 'type-checks the arguments against the library signature', :swift_compile do
    stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + EmittedSwift::COLLECTION_STACK_VIEW_STUB + cell_view_stub('ACellView')
    codes = [emit('width' => 'matchParent'), emit('width' => 'wrapContent')]
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}", data: ['var rows: CollectionDataSource? = nil'], stubs: stubs))
      .to compile_as_swift
  end
end
