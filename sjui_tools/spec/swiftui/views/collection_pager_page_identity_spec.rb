# frozen_string_literal: true

require 'swiftui/views/collection_converter'

# A pager's page is known by its place, not by the change-tracking cellId
# (ticket sjui-paging-collection-uses-change-tracking-cellid-as-page-identity-
# and-stops-mid-swipe). With cellIdProperty + autoChangeTrackingId the
# enriched cellId ("<key>_<hash of the content>") was the ForEach id: when any
# page's content changed during a swipe — even a page off screen — SwiftUI
# removed and re-inserted it, and the paging TabView ended between two pages
# (16 of 41 swipes on a consumer's book screen; 0 of 41 with the ids fixed).
# KotlinJsonUI's HorizontalPager is positional. The cellId still reaches the
# cell, which redraws on it (`.equatable()`, the scaffold's onChange).
# The drawn arm is SwiftJsonUI's PagerIdentityProbeUITests.
RSpec.describe 'sjui: a pager page is known by its place' do
  before(:all) { SjuiTools::SwiftUI::Views::CollectionConverter.superclass.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::CollectionConverter.superclass.validation_enabled = true }

  def convert(extra)
    SjuiTools::SwiftUI::Views::CollectionConverter.new(
      { 'type' => 'Collection', 'id' => 'pager', 'layout' => 'horizontal', 'paging' => true,
        'items' => '@{rows}', 'currentPage' => '@{page}', 'cellIdProperty' => 'key',
        'autoChangeTrackingId' => true }.merge(extra)
    ).convert.to_s
  end

  def sections
    { 'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell' }] }
  end

  it 'loops over the pages by their index, in every section' do
    code = convert(sections)
    expect(code.scan('ForEach(items, id: \\.index) { cell in').size).to eq(2), code
    expect(code).not_to include('keyed_loop', 'let ids: [AnyHashable]', 'id: \\.id) { item in')
  end

  it 'keeps the change-tracking cellId on the cell, and the tag on the page' do
    code = convert(sections)
    expect(code).to include('reconfigured(cellIdProperty: "key", autoChangeTrackingId: true)')
    expect(code).to include('ACellView(data: cell.data).equatable()', '.tag(cell.index)')
  end

  it 'the class-list pager too' do
    code = convert('cellClasses' => ['ACell'])
    expect(code).to include('ForEach(items, id: \\.index) { cell in')
  end

  it 'control: a non-paging horizontal Collection keeps its keyed ids' do
    code = convert(sections.merge('paging' => false))
    expect(code).not_to include('ForEach(items, id: \\.index)')
  end

  it 'with a scrollTo too: the loop is by index, and the scrollTo turns the selection' do
    code = convert(sections.merge('scrollTo' => '@{target}'))
    expect(code.scan('ForEach(items, id: \\.index) { cell in').size).to eq(2), code
    expect(code).not_to include('let targets: [AnyHashable]')
    expect(code).to include('.onChange(of: data.target)', 'data.page = found')
  end
end
