# frozen_string_literal: true

require 'swiftui/views/view_converter'
require 'swiftui/views/collection_converter'
require 'swiftui/views/label_converter'
require 'swiftui/views/image_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

# A frame that sizes ONE axis of a container puts content smaller than it at
# top | start (the user's ruling of 2026-09-27; the canon's gravityDefaults),
# as Compose (Column / Box: Arrangement.Top, Alignment.TopStart) and the web
# (flex-start) do; a declared center* gravity still centres. Until jsonui-cli
# 1.9.0 these frames carried no alignment and SwiftUI centred the content on
# that axis — measured on the ConformanceHost (iOS 26.5): a 20pt label 19pt
# down a 60pt-tall matchParent View, 85pt in along a 200pt-wide one, a
# `lazy: none` Collection's cell 20pt down. The frames that size both axes,
# or fill, already carried it.
#
# The drawn arm is FrameAlignmentProbeUITests in SwiftJsonUI's ConformanceHost.
RSpec.describe SjuiTools::SwiftUI::Views::ViewConverter do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  LABEL = { 'type' => 'Label', 'text' => 'abc', 'width' => 'wrapContent', 'height' => 'wrapContent' }.freeze

  def view(attrs)
    described_class.new({ 'type' => 'View', 'child' => [LABEL] }.merge(attrs), 0).convert.to_s
  end

  HEIGHT_60 = '.frame(minHeight: 60, idealHeight: 60, maxHeight: 60, alignment: .topLeading)'

  it 'a matchParent-wide View of a fixed height: its content at the top' do
    expect(view('orientation' => 'vertical', 'width' => 'matchParent', 'height' => 60)).to include(HEIGHT_60)
    expect(view('width' => 'matchParent', 'height' => 60)).to include(HEIGHT_60)
  end

  it 'a wrapContent-wide View of a fixed height: at the top' do
    expect(view('orientation' => 'vertical', 'width' => 'wrapContent', 'height' => 60)).to include(HEIGHT_60)
  end

  it 'a fixed-width View, wrapContent or matchParent high: at the start, and at the top when it fills' do
    expect(view('orientation' => 'vertical', 'width' => 200, 'height' => 'wrapContent')).to include('.frame(width: 200, alignment: .topLeading)')
    tall = view('orientation' => 'vertical', 'width' => 200, 'height' => 'matchParent')
    expect(tall).to include('.frame(width: 200, alignment: .topLeading)')
    expect(tall).to include('.frame(maxHeight: .infinity, alignment: .topLeading)')
  end

  it 'a lazy: none Collection of a fixed height: its cells at the top' do
    code = SjuiTools::SwiftUI::Views::CollectionConverter.new({ 'type' => 'Collection', 'id' => 'list', 'width' => 'matchParent', 'height' => 60,
                                                               'lazy' => 'none', 'items' => '@{rows}', 'sections' => [{ 'cell' => 'ACell' }] }).convert.to_s
    expect(code).to include(HEIGHT_60)
  end

  it 'control: a declared centerVertical gravity still centres; both axes fixed are as before' do
    expect(view('orientation' => 'vertical', 'width' => 'matchParent', 'height' => 60, 'gravity' => 'centerVertical'))
      .to include('.frame(minHeight: 60, idealHeight: 60, maxHeight: 60, alignment: .leading)')
    expect(view('orientation' => 'vertical', 'width' => 200, 'height' => 60)).to include('.frame(width: 200, height: 60, alignment: .topLeading)')
  end

  it 'control: a Label keeps its text alignment, and a leaf with no gravity its own content channel' do
    label = SjuiTools::SwiftUI::Views::LabelConverter.new({ 'type' => 'Label', 'text' => 'abc', 'width' => 'matchParent', 'height' => 60 }, 0).convert.to_s
    expect(label).to include('.frame(minHeight: 60, idealHeight: 60, maxHeight: 60)')
    image = SjuiTools::SwiftUI::Views::ImageConverter.new({ 'type' => 'Image', 'srcName' => 'a', 'width' => 'matchParent', 'height' => 60 }, 0).convert.to_s
    expect(image).not_to include('maxHeight: 60, alignment:')
  end

  it 'type-checks on every one-axis frame it aligns', :swift_compile do
    views = [
      { 'orientation' => 'vertical', 'width' => 'matchParent', 'height' => 60 }, { 'width' => 'matchParent', 'height' => 60 },
      { 'orientation' => 'vertical', 'width' => 'wrapContent', 'height' => 60 },
      { 'orientation' => 'vertical', 'width' => 200, 'height' => 'wrapContent' },
      { 'orientation' => 'vertical', 'width' => 200, 'height' => 'matchParent' },
      { 'orientation' => 'vertical', 'height' => 'matchParent' },
      { 'orientation' => 'vertical', 'width' => 'matchParent', 'height' => 60, 'gravity' => 'centerVertical' }
    ].map { |attrs| view(attrs) }
    collection = SjuiTools::SwiftUI::Views::CollectionConverter.new({ 'type' => 'Collection', 'id' => 'list', 'width' => 'matchParent', 'height' => 60,
                                                                     'lazy' => 'none', 'items' => '@{rows}', 'sections' => [{ 'cell' => 'ACell' }] }).convert.to_s
    stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + EmittedSwift::COLLECTION_STACK_VIEW_STUB + cell_view_stub('ACellView')
    expect(compilable_view("VStack {\n#{(views + [collection]).join("\n")}\n}", data: ['var rows: CollectionDataSource? = nil'], stubs: stubs))
      .to compile_as_swift
  end
end
