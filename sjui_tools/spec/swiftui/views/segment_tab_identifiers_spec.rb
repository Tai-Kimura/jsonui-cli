# frozen_string_literal: true

require 'swiftui/views/segment_converter'
require_relative '../../support/emitted_swift'

# Each segment carries `<id>_tab_<n>`, the id every driver's selectTab looks
# for; the segments were id-less, so a Segment could not be selected from a UI
# test on iOS (ticket jui-segment-tabs-carry-no-tab-ids-so-selecttab-cannot-
# reach-them). Measured 2026-10-03 (iOS 26.5 simulator, Xcode 26.6): the
# identifier on a segment's Text reaches XCUITest as that segment's button,
# and a tap on it selects the segment. This spec cannot measure that; it
# holds the emission.
RSpec.describe 'Segment tab identifiers' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emit(component)
    SjuiTools::SwiftUI::Views::SegmentConverter.new(component).convert
  end

  def segment_lines(code)
    code.lines.map(&:strip).select { |l| l.start_with?('Text(') }
  end

  it 'gives each segment <id>_tab_<n>, in item order' do
    code = emit('type' => 'Segment', 'id' => 'style_segment', 'items' => %w[App Book Plain])
    expect(segment_lines(code)).to eq([
      'Text("App").tag(0).accessibilityIdentifier("style_segment_tab_0")',
      'Text("Book").tag(1).accessibilityIdentifier("style_segment_tab_1")',
      'Text("Plain").tag(2).accessibilityIdentifier("style_segment_tab_2")'
    ])
  end

  it 'numbers the segments as the tags do when an object item is dropped' do
    code = emit('type' => 'Segment', 'id' => 's', 'items' => ['A', { 'label' => 'x' }, 'B'])
    expect(segment_lines(code)).to eq([
      'Text("A").tag(0).accessibilityIdentifier("s_tab_0")',
      'Text("B").tag(1).accessibilityIdentifier("s_tab_1")'
    ])
  end

  it 'gives none without an id, as the Segment itself gets none' do
    code = emit('type' => 'Segment', 'items' => %w[A B])
    expect(segment_lines(code)).to eq(['Text("A").tag(0)', 'Text("B").tag(1)'])
    expect(code).not_to include('accessibilityIdentifier')
  end

  it 'escapes the id as a Swift string' do
    code = emit('type' => 'Segment', 'id' => 'a"b', 'items' => %w[A])
    expect(segment_lines(code)).to eq(['Text("A").tag(0).accessibilityIdentifier("a\\"b_tab_0")'])
  end

  it 'the emitted segments compile inside a segmented Picker' do
    lines = segment_lines(emit('type' => 'Segment', 'id' => 'style_segment', 'items' => %w[App Book]))
    fragment = "Picker(\"\", selection: .constant(0)) {\n#{lines.map { |l| "    #{l}" }.join("\n")}\n}\n.pickerStyle(.segmented)"
    expect(compilable_view(fragment)).to compile_as_swift.with_imports('SwiftUI')
  end
end
