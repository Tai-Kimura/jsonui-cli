# frozen_string_literal: true

require 'swiftui/views/scrollview_converter'
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

# A horizontal ScrollView of height wrapContent is as tall as its content, as
# KotlinJsonUI's horizontalScroll row is. Its view, AdvancedKeyboardAvoidingScrollView,
# is a GeometryReader framing the scroll at the reader's height, and in a
# vertical ScrollView the reader is offered none: it took the height the outer
# ScrollView had left — a 28pt row drew 386pt tall in a 420pt ScrollView on
# SwiftJsonUI's ConformanceHost (ticket
# 2026-10-23-sjui-geometryreader-in-vertical-scroll-collapses). The content
# stack is measured at its own height (fixedSize, onGeometryChange) into a
# state of the view's, and the ScrollView framed at it.
#
# The drawn arm is ScrollHeightProbeUITests in SwiftJsonUI's ConformanceHost
# (the codegen half: this emission; the Dynamic half: DynamicScrollViewContainer).
RSpec.describe SjuiTools::SwiftUI::Views::ScrollViewConverter do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def converter(extra)
    described_class.new({ 'type' => 'ScrollView', 'id' => 'chips', 'orientation' => 'horizontal', 'width' => 'matchParent',
                          'child' => [{ 'type' => 'View', 'width' => 100, 'height' => 28 }] }.merge(extra))
  end

  def lines(conv)
    conv.convert.to_s.lines.map(&:strip)
  end

  it 'horizontal, height wrapContent: the content measured at its own height, the ScrollView framed at it' do
    conv = converter('height' => 'wrapContent')
    got = lines(conv)
    expect(conv.state_variables).to include('@State private var chipsContentHeight: CGFloat? = nil')
    expect(got).to include('.fixedSize(horizontal: false, vertical: true)',
                           '.onGeometryChange(for: CGFloat.self) { $0.size.height } action: { chipsContentHeight = $0 }',
                           '.frame(height: chipsContentHeight)')
    # measured before the frame that stretches the content to the viewport; the ScrollView framed after it closes
    stretch = got.index { |l| l.start_with?('.frame(maxWidth: .infinity, maxHeight: .infinity') }
    expect(got.index { |l| l.start_with?('.onGeometryChange') }).to be < stretch
    expect(got.index('.frame(height: chipsContentHeight)')).to be > stretch
  end

  it 'control: a vertical one, or another height, draws as before' do
    [{ 'height' => 200 }, { 'height' => 'matchParent' }, {}, { 'orientation' => 'vertical', 'height' => 'wrapContent' }].each do |extra|
      conv = converter(extra)
      code = conv.convert.to_s
      expect(code).not_to include('ContentHeight'), extra.inspect
      expect(code).not_to include('onGeometryChange'), extra.inspect
      expect(conv.state_variables).to eq([]), extra.inspect
    end
  end

  it 'type-checks what it emits', :swift_compile do
    conv = converter('height' => 'wrapContent')
    code = conv.convert
    states = conv.state_variables.map { |s| "    #{s}" }.join("\n")
    # the library's view as the emission calls it (SwiftJsonUI's AdvancedKeyboardAvoidingScrollView)
    stub = <<~SWIFT
      struct AdvancedKeyboardAvoidingScrollView<Content: View>: View {
          init(_ axes: Axis.Set, showsIndicators: Bool = true, @ViewBuilder content: () -> Content) { self.content = content() }
          let content: Content
          var body: some View { ScrollView { content } }
      }
    SWIFT
    swift = compilable_view("VStack {\n#{code}\n}", stubs: stub)
    swift = swift.sub("    let data = TestData()\n", "    let data = TestData()\n#{states}\n")
    expect(swift).to compile_as_swift
  end
end
