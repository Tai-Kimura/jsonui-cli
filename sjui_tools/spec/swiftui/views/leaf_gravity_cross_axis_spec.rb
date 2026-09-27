# frozen_string_literal: true

require 'swiftui/views/view_converter'
require 'swiftui/views/label_converter'
require 'swiftui/views/image_converter'
require 'swiftui/views/textfield_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

# A LEAF's partial gravity fixes only its own axis: the axis it does not name
# stays centred. Measured 2026-09-27: Compose (kjui's emit, the same for
# gravity left / right / center / none) and the web (rjui's) centre a
# TextField's and a Button's text vertically in a 44pt frame whatever the
# gravity. Until jsonui-cli 1.9.0 gravity_to_frame_alignment filled a leaf's
# unnamed axis with the container default (top | start), so a TextField with
# gravity left sat at the top of its 44pt frame on iOS — 5pt down, 27pt up
# from the bottom (ConformanceHost, iOS 26.5, generated and Dynamic alike).
# A container keeps top | start; a Label keeps its own text channel.
#
# The drawn arm is LeafGravityProbeUITests in SwiftJsonUI's ConformanceHost.
RSpec.describe SjuiTools::SwiftUI::Views::FrameHelper do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emit(node)
    factory = SjuiTools::SwiftUI::ConverterFactory.new
    factory.create_converter(node, 0, nil, factory).convert.to_s
  end

  TEXT_FIELD = { 'type' => 'TextField', 'id' => 'tf', 'text' => '@{value}', 'height' => 44 }.freeze

  it 'a TextField with gravity left: its text centred vertically, on a frame of one axis or of both' do
    one = emit(TEXT_FIELD.merge('width' => 'matchParent', 'gravity' => 'left'))
    expect(one).to include('.frame(minHeight: 44, idealHeight: 44, maxHeight: 44, alignment: .leading)')
    expect(one).to include('.frame(maxWidth: .infinity, alignment: .leading)')
    both = emit(TEXT_FIELD.merge('width' => 200, 'gravity' => 'left'))
    expect(both).to include('.frame(width: 200, height: 44, alignment: .leading)')
  end

  it 'a leaf gravity naming the vertical axis alone centres the horizontal one' do
    expect(emit(TEXT_FIELD.merge('width' => 'matchParent', 'gravity' => 'top')))
      .to include('.frame(minHeight: 44, idealHeight: 44, maxHeight: 44, alignment: .top)')
    expect(emit({ 'type' => 'Image', 'srcName' => 'a', 'width' => 200, 'height' => 44, 'gravity' => 'centerVertical' }))
      .to include('.frame(width: 200, height: 44, alignment: .center)')
  end

  it 'control: a leaf naming both axes, and a leaf with no gravity, are as before' do
    expect(emit(TEXT_FIELD.merge('width' => 200, 'gravity' => 'right|bottom'))).to include('alignment: .bottomTrailing)')
    expect(emit({ 'type' => 'Image', 'srcName' => 'a', 'width' => 200, 'height' => 44 })).to include('.frame(width: 200, height: 44)')
  end

  it 'control: a container keeps top | start for the axis the gravity does not name' do
    view = emit({ 'type' => 'View', 'orientation' => 'vertical', 'width' => 'matchParent', 'height' => 44, 'gravity' => 'left',
                  'child' => [{ 'type' => 'Label', 'text' => 'a' }] })
    expect(view).to include('.frame(minHeight: 44, idealHeight: 44, maxHeight: 44, alignment: .topLeading)')
    # A Label follows its own vertical rule (label_vertical_spec.rb): centred
    # unless its gravity names the vertical, and start across.
    label = emit({ 'type' => 'Label', 'text' => 'a', 'width' => 200, 'height' => 44, 'gravity' => 'left' })
    expect(label).to include('.frame(width: 200, height: 44, alignment: .leading)')
  end

  it 'type-checks the leaf alignments it emits', :swift_compile do
    images = [
      { 'width' => 'matchParent', 'gravity' => 'left' }, { 'width' => 200, 'gravity' => 'left' },
      { 'width' => 'matchParent', 'gravity' => 'top' }, { 'width' => 200, 'gravity' => 'centerVertical' },
      { 'width' => 200, 'gravity' => 'right' }
    ].map { |attrs| emit({ 'type' => 'Image', 'srcName' => 'a', 'height' => 44 }.merge(attrs)) }
    expect(compilable_view("VStack {\n#{images.join("\n")}\n}")).to compile_as_swift
  end
end
