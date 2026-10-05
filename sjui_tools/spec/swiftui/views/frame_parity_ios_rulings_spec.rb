# frozen_string_literal: true

require 'swiftui/views/view_converter'
require 'swiftui/views/safeareaview_converter'
require 'swiftui/views/label_converter'
require 'swiftui/views/indicator_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

# Five iOS families the 3-face frame-parity inventory of 2026-10-05 found
# away from Android and web, on both iOS faces. SwiftJsonUI's Dynamic face
# makes the same five changes (10.29.6).
RSpec.describe 'iOS codegen: the frame-parity families of 2026-10-05' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  let(:factory) { SjuiTools::SwiftUI::ConverterFactory.new }
  let(:box) { { 'type' => 'View', 'id' => 'a', 'width' => 40, 'height' => 40 } }

  def view(json)
    SjuiTools::SwiftUI::Views::ViewConverter.new(json, 0, nil, factory).convert
  end

  # SwiftJsonUI 10.29.6's two new layouts, by their public signatures. A
  # transcription, not the library: the arm checks that the emit calls them
  # the way they are declared, not that they draw anything.
  let(:new_api) do
    <<~SWIFT
      struct DistributionFillLayout: Layout {
          var axis: Axis; var spacing: CGFloat; var crossBias: CGFloat
          init(axis: Axis, spacing: CGFloat = 0, crossBias: CGFloat = 0) { self.axis = axis; self.spacing = spacing; self.crossBias = crossBias }
          func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize { .zero }
          func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {}
      }
      extension View { func scaledWithFootprint(_ scale: CGFloat) -> some View { self } }
    SWIFT
  end

  describe '1. alignment places the children of a View, as gravity does' do
    # `alignment` is the declared string alternative to gravity. Only the
    # ZStack's own `alignment:` read it, inside a frame that pinned the
    # content top-left: every value drew the children at 0, 0.
    {
      'bottom' => '.bottom', 'center' => '.center', 'topTrailing' => '.topTrailing',
      'leading' => '.leading', 'bottomTrailing' => '.bottomTrailing'
    }.each do |alignment, frame|
      it "puts #{alignment} in the frame alignment" do
        code = view('type' => 'View', 'width' => 200, 'height' => 200, 'alignment' => alignment, 'child' => [box])
        expect(code).to include(".frame(width: 200, height: 200, alignment: #{frame})")
      end
    end

    it 'lets a declared gravity win (control)' do
      code = view('type' => 'View', 'width' => 200, 'height' => 200, 'alignment' => 'bottom', 'gravity' => 'top', 'child' => [box])
      expect(code).to include('.frame(width: 200, height: 200, alignment: .topLeading)')
    end

    it 'leaves a View without alignment top-leading (control)' do
      expect(view('type' => 'View', 'width' => 200, 'height' => 200, 'child' => [box]))
        .to include('.frame(width: 200, height: 200, alignment: .topLeading)')
    end
  end

  describe '2. distribution fill grows each child from its content' do
    let(:fill_row) do
      { 'type' => 'View', 'id' => 'target', 'width' => 300, 'height' => 200, 'orientation' => 'horizontal',
        'distribution' => 'fill',
        'child' => [{ 'type' => 'View', 'id' => 'box_a', 'width' => 60, 'height' => 40 },
                    { 'type' => 'Label', 'id' => 'box_b', 'text' => 'BBBB' },
                    { 'type' => 'Label', 'id' => 'box_c', 'text' => 'CCCCCCCC' }] }
    end

    it 'lays the row out with DistributionFillLayout, not an HStack' do
      code = view(fill_row)
      expect(code).to include('DistributionFillLayout(axis: .horizontal, spacing: 0, crossBias: 0) {')
      expect(code).to include('// Requires SwiftJsonUI >= 10.29.6 (DistributionFillLayout)')
      expect(code).not_to include('HStack(')
    end

    it 'puts no gravity spacer inside it (a Spacer would be a child)' do
      code = view(fill_row.merge('width' => 'matchParent', 'gravity' => 'right'))
      expect(code).not_to include('Spacer(')
    end

    it 'lays a column out on the vertical axis, across at the gravity' do
      code = view(fill_row.merge('orientation' => 'vertical', 'gravity' => 'centerHorizontal'))
      expect(code).to include('DistributionFillLayout(axis: .vertical, spacing: 0, crossBias: 0.5) {')
    end

    it 'keeps fillEqually on the weighted stack (control)' do
      code = view(fill_row.merge('distribution' => 'fillEqually'))
      expect(code).not_to include('DistributionFillLayout')
    end

    it 'emits Swift a compiler reads' do
      expect(compilable_view(view(fill_row), stubs: new_api)).to compile_as_swift
    end
  end

  describe '3. a styled Indicator lays out at its scaled size' do
    def indicator(style)
      SjuiTools::SwiftUI::Views::IndicatorConverter.new('type' => 'Indicator', 'indicatorStyle' => style).convert
    end

    it 'scales large and small with their footprint' do
      expect(indicator('large')).to include('.scaledWithFootprint(1.5)')
      expect(indicator('small')).to include('.scaledWithFootprint(0.8)')
    end

    it 'leaves medium, the platform size, unscaled (control)' do
      expect(indicator('medium')).not_to include('scaledWithFootprint')
    end

    it 'emits Swift a compiler reads' do
      expect(compilable_view(indicator('large'), stubs: new_api)).to compile_as_swift
    end
  end

  describe '4. a reversed SafeAreaView starts at its start edge' do
    # The codegen SafeAreaView is a ViewConverter, so the View's start-edge
    # rule (direction_start_edge_spec) already reached it; this pins it, as
    # SwiftJsonUI Dynamic had to be fixed separately.
    def safe(extra)
      SjuiTools::SwiftUI::Views::SafeAreaViewConverter.new(
        { 'type' => 'SafeAreaView', 'width' => 'matchParent', 'height' => 'matchParent',
          'child' => [box, box.merge('id' => 'b')] }.merge(extra), 0, nil, factory
      ).convert
    end

    it 'starts bottomToTop at the bottom' do
      code = safe('orientation' => 'vertical', 'direction' => 'bottomToTop')
      expect(code).to include('alignment: .bottomLeading)')
      expect(code.lines.map(&:strip).each_cons(2).any? { |a, b| a.start_with?('VStack(') && b == 'Spacer(minLength: 0)' }).to be(true)
    end

    it 'starts rightToLeft at the right' do
      expect(safe('orientation' => 'horizontal', 'direction' => 'rightToLeft')).to include('alignment: .topTrailing)')
    end
  end

  describe "5. a showing hint is drawn in hintAttributes' font" do
    def label(extra)
      SjuiTools::SwiftUI::Views::LabelConverter.new(
        { 'type' => 'Label', 'id' => 't', 'width' => 200, 'hint' => 'Conformance Hint' }.merge(extra)
      ).convert
    end

    it 'takes the weight from hintAttributes.font' do
      expect(label('hintAttributes' => { 'font' => 'bold', 'fontSize' => 24 })).to include('fontWeight: "bold"')
    end

    it 'draws a hint without a font at the regular weight (control)' do
      expect(label('hintAttributes' => { 'fontSize' => 24 })).not_to include('fontWeight')
    end

    # The hint's lineHeightMultiple was read by nothing on this face. It goes
    # to the library as the Label's does (each line m x the line of the
    # hint's own size; the iOS first line stays L, ruling B's iOS limit).
    it 'takes the line height multiple from hintAttributes' do
      expect(label('hintAttributes' => { 'fontSize' => 24, 'lineHeightMultiple' => 1.5 }))
        .to include('lineHeightMultiple: 1.5,')
    end

    it "lets the hint's multiple win over the Label's while it shows" do
      code = label('lineHeightMultiple' => 2.0, 'hintAttributes' => { 'lineHeightMultiple' => 1.5 })
      expect(code).to include('lineHeightMultiple: 1.5,')
      expect(code).not_to include('lineHeightMultiple: 2.0,')
    end

    it "keeps the Label's own multiple when the hint declares none (control)" do
      expect(label('lineHeightMultiple' => 2.0, 'hintAttributes' => { 'fontSize' => 24 }))
        .to include('lineHeightMultiple: 2.0,')
    end
  end
end
