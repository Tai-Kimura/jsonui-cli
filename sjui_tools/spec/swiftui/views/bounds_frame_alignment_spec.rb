# frozen_string_literal: true

require 'swiftui/views/view_converter'
require 'swiftui/views/image_converter'
require 'swiftui/views/label_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

# A container's min / max bounds frame puts content smaller than it at
# top | start — the unnamed axis of a partial gravity, and both axes when
# gravity is omitted — as the frames that size it do (gravity_to_frame_
# alignment, the canon's gravityDefaults). Until jsonui-cli 1.9.0
# ResponsiveHelper.inner_frame_alignment filled the unnamed axis with centre
# and emitted no alignment for an omitted gravity, so SwiftUI centred the
# content: a 20pt label 40pt down a `minHeight: 100` box, 86pt in along a
# `minWidth: 200` one (ConformanceHost, iOS 26.5). A leaf keeps centre on the
# unnamed axis and no argument when gravity is omitted; an omitted gravity
# with a responsive align / center flag keeps `.center`.
#
# The drawn arm is BoundsAlignmentProbeUITests in SwiftJsonUI's
# ConformanceHost; the Dynamic half is DynamicModifierHelper's
# applyFrameConstraints.
RSpec.describe SjuiTools::SwiftUI::Views::ResponsiveHelper do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emit(node)
    factory = SjuiTools::SwiftUI::ConverterFactory.new
    factory.create_converter(node, 0, nil, factory).convert.to_s
  end

  def box(attrs)
    emit({ 'type' => 'View', 'orientation' => 'vertical', 'child' => [{ 'type' => 'Label', 'text' => 'a' }] }.merge(attrs))
  end

  it "a container's bounds frame with gravity omitted: top | start" do
    expect(box('width' => 300, 'minHeight' => 100)).to include('.frame(minHeight: 100, alignment: .topLeading)')
    expect(box('minWidth' => 200, 'height' => 40)).to include('.frame(minWidth: 200, alignment: .topLeading)')
    expect(box('width' => 'matchParent', 'maxWidth' => 200)).to include('.frame(maxWidth: 200, alignment: .topLeading)')
  end

  it "a container's partial gravity: the unnamed axis at top | start" do
    expect(box('width' => 300, 'minHeight' => 100, 'gravity' => 'centerVertical')).to include('.frame(minHeight: 100, alignment: .leading)')
    expect(box('width' => 300, 'minHeight' => 100, 'gravity' => 'centerHorizontal')).to include('.frame(minHeight: 100, alignment: .top)')
  end

  it 'control: a leaf, a gravity naming both axes, and a responsive flag are as before' do
    image = emit({ 'type' => 'Image', 'srcName' => 'a', 'minHeight' => 100, 'gravity' => 'left' })
    expect(image).to include('.frame(minHeight: 100, alignment: .leading)')
    expect(emit({ 'type' => 'Image', 'srcName' => 'a', 'minHeight' => 100 })).to include('.frame(minHeight: 100)')
    expect(box('width' => 300, 'minHeight' => 100, 'gravity' => 'center')).to include('.frame(minHeight: 100, alignment: .center)')
    expect(described_class.inner_frame_alignment({ 'alignLeft' => true }, true)).to eq('.center')
    expect(described_class.inner_frame_alignment({ 'gravity' => 'left' })).to eq('.leading')
  end

  it 'type-checks the alignments it emits', :swift_compile do
    codes = [box('width' => 300, 'minHeight' => 100), box('width' => 300, 'minHeight' => 100, 'gravity' => 'centerVertical'),
             box('width' => 300, 'minHeight' => 100, 'gravity' => 'centerHorizontal')]
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}")).to compile_as_swift
  end
end
