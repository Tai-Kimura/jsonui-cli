# frozen_string_literal: true

require 'swiftui/views/collection_converter'
require_relative '../../support/emitted_swift'

# A wrapContent Collection sizes to its content (4f ruling 2026-09-27, the
# user's "size to content"): the SSoT's wrapContent is "size to content, up to
# the parent's bound, then scroll", as web and Compose draw it. A SwiftUI
# ScrollView takes every point it is offered, so until jsonui-cli 1.9.0 a
# Collection whose scroll-axis size was wrapContent — or undeclared, which
# sjui emits the same — filled its parent (120 of a 120pt parent) and pushed
# the views after it to the parent's end; inside a ScrollView it filled the
# visible height. The route's scroll container now sits in SwiftJsonUI's
# CollectionContentFit, which gives it its content's size along the axis, up
# to the parent's bound.
#
# Not the pager (its TabView is its pages) and not a List: a List reports no
# content height to size to (measured: CollectionContentFit drew it 0pt tall),
# so a wrapContent List still fills its parent.
#
# And a Collection is a container for its frame's alignment (the canon's
# gravityDefaults, top | start): its frame fell to SwiftUI's `.center`, so a
# `lazy: none` column narrower than a matchParent Collection stood in the
# middle, where the lazy route's cells start at the leading edge.
#
# The drawn arm is CollectionFitProbeUITests in SwiftJsonUI's ConformanceHost.
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  include EmittedSwift

  before(:all) { described_class.superclass.validation_enabled = false }
  after(:all) { described_class.superclass.validation_enabled = true }

  def emit(extra)
    described_class.new({ 'type' => 'Collection', 'id' => 'list', 'width' => 'matchParent', 'items' => '@{rows}' }.merge(extra).compact).convert.to_s
  end

  SECTIONS = { 'sections' => [{ 'cell' => 'ACell' }] }.freeze
  FIT_ROUTES = {
    'list' => SECTIONS, 'eager list' => SECTIONS.merge('lazy' => 'eager'), 'grid' => SECTIONS.merge('columns' => 2),
    'flow' => SECTIONS.merge('layout' => 'flow'), 'class-list grid' => { 'cellClasses' => ['ACell'], 'columns' => 2 }
  }.freeze

  it 'a vertical Collection of wrapContent or undeclared height: its scroll container in CollectionContentFit(axis: .vertical)' do
    FIT_ROUTES.each do |route, node|
      [{ 'height' => 'wrapContent' }, {}].each do |height|
        code = emit(node.merge(height))
        expect(code).to start_with("CollectionContentFit(axis: .vertical) {\n"), "#{route} #{height}"
        expect(code).to match(/\ACollectionContentFit\(axis: \.vertical\) \{\n    (CollectionStackView\(|ScrollView\(\.vertical)/), "#{route} #{height}"
      end
    end
  end

  it 'a horizontal Collection of wrapContent or undeclared width: CollectionContentFit(axis: .horizontal)' do
    [{ 'width' => 'wrapContent' }, { 'width' => nil }].each do |width|
      code = emit(SECTIONS.merge('layout' => 'horizontal', 'height' => 40).merge(width))
      expect(code).to start_with("CollectionContentFit(axis: .horizontal) {\n    CollectionStackView(\n"), width.inspect
    end
  end

  it 'control: a bound or weighted axis, the pager, a List and lazy: none keep their container as it was' do
    shapes = {
      'height 120' => SECTIONS.merge('height' => 120), 'matchParent' => SECTIONS.merge('height' => 'matchParent'),
      'weight' => SECTIONS.merge('weight' => 1), 'bound horizontal' => SECTIONS.merge('layout' => 'horizontal', 'width' => 'matchParent'),
      'pager' => SECTIONS.merge('layout' => 'horizontal', 'paging' => true, 'width' => nil),
      'class-list List' => { 'cellClasses' => ['ACell'] }, 'sectioned List' => SECTIONS.merge('listStyle' => 'plain'),
      'lazy none' => SECTIONS.merge('lazy' => 'none')
    }
    shapes.each do |name, node|
      expect(emit(node)).not_to include('CollectionContentFit'), name
    end
  end

  it "a Collection's frame aligns its content top leading, as a container's does; lazy: none included" do
    none = emit(SECTIONS.merge('lazy' => 'none'))
    expect(none).to include('.frame(maxWidth: .infinity, alignment: .topLeading)')
    bounded = emit(SECTIONS.merge('lazy' => 'none', 'width' => 180, 'height' => 80, 'layout' => 'horizontal'))
    expect(bounded).to include('.frame(width: 180, height: 80, alignment: .topLeading)')
    expect(emit(SECTIONS)).to include('.frame(maxWidth: .infinity, alignment: .topLeading)')
    expect(emit(SECTIONS.merge('gravity' => 'centerHorizontal', 'lazy' => 'none'))).to include('.frame(maxWidth: .infinity, alignment: .top)')
  end

  it 'type-checks on every fitted route', :swift_compile do
    stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + EmittedSwift::COLLECTION_STACK_VIEW_STUB + cell_view_stub('ACellView') +
            "struct FlowLayout<Content: View>: View { let content: () -> Content\n" \
            "  init(alignment: HorizontalAlignment, horizontalSpacing: CGFloat, verticalSpacing: CGFloat, @ViewBuilder content: @escaping () -> Content) { self.content = content }\n" \
            "  var body: some View { VStack { content() } } }\n"
    codes = FIT_ROUTES.values.map { |node| emit(node) } + [emit(SECTIONS.merge('layout' => 'horizontal', 'height' => 40, 'width' => nil))]
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}", data: ['var rows: CollectionDataSource? = nil'], stubs: stubs)).to compile_as_swift
  end
end
