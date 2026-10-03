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

  # The scrollTo's first-section-wins key set (earlierKeys) is the keyed
  # loop's: a pager reads none of it, so it is not emitted there — an unread
  # `let` is a warning in a consumer's build and a pass over every earlier
  # section's cells on each redraw.
  it 'emits no earlier-section key set for a pager with a scrollTo' do
    expect(convert(sections.merge('scrollTo' => '@{target}'))).not_to include('earlierKeys')
    expect(convert(sections.merge('scrollTo' => '@{target}', 'paging' => false))).to include('let earlierKeys =')
  end

  # The page style aside (the macOS SDK the suite type-checks against has no
  # `.page`), as in collection_paging_pages_spec.
  def compilable(codes)
    styled = codes.map { |code| code.lines.reject { |l| l.include?('.tabViewStyle(.page(') }.join }
    expect(styled.join).not_to include('.page(')
    <<~SWIFT
      #{EmittedSwift::COLLECTION_DATA_SOURCE_STUB}
      #{cell_view_stub('ACellView', 'BCellView')}
      extension Array where Element == [String: Any] {
          func reconfigured(cellIdProperty: String?, autoChangeTrackingId: Bool) -> [[String: Any]] { self }
      }
      struct TestData { var rows: CollectionDataSource? = nil; var page: Int = 0; var target: String = "" }
      struct EmittedHost: View {
          @State var data = TestData()
          var body: some View {
              VStack {
      #{styled.join("\n")}
              }
          }
      }
    SWIFT
  end

  def pager_codes
    [convert(sections), convert(sections.merge('scrollTo' => '@{target}')), convert('cellClasses' => ['ACell'])]
  end

  it 'the emitted Swift type-checks: sections, sections with a scrollTo, the class list', :swift_compile do
    expect(compilable(pager_codes)).to compile_as_swift
  end

  # compile_as_swift reads the exit status only; an unread value is a warning.
  it 'and leaves no value unread', :swift_compile do
    reason = SwiftCompiler.unavailable_reason
    skip reason if reason
    result = SwiftCompiler.type_check(compilable(pager_codes))
    expect(result).to be_success, result.output
    expect(result.output.lines.grep(/warning:.*never used/)).to be_empty, result.output
  end
end
