# frozen_string_literal: true

# What the codegen hands SwiftJsonUI for a FACING link (alignTopOfView /
# alignBottomOfView / alignLeftOfView / alignRightOfView) against an anchor
# with margins.
#
# The defect these links had on iOS was not in this tool: the codegen emits
# a RelativePositionContainer, and SwiftJsonUI's RelativePositionLayout
# applied the anchor's margin a second time on the four facing links (ticket
# sjui-relative-facing-link-measures-the-anchor-with-its-margin; fixed in
# SwiftJsonUI 10.29.6, measured on both the Dynamic and the codegen
# conformance hosts). The library's arm for the codegen route
# (RelativeFacingLinkAnchorMarginTests#testCodegenContainerFacingLinksMeetTheAnchorsDrawnBox)
# draws a container built by hand in the shape below. This spec pins that
# shape from the producer's side — so the library arm keeps describing what
# the codegen actually emits:
#   * the anchor's margins travel on its RelativeChildConfig, as an
#     EdgeInsets, not as padding on the view (padding would grow the box the
#     anchor draws);
#   * an unconstrained anchor gets parentTop + parentLeft, which is what
#     places it at its margin;
#   * each facing link is a RelativePositionConstraint of its own type.
# It does not turn red when the library fix is removed — there is nothing in
# this tool to remove. It turns red when the emit stops being the shape the
# library arm measures.
require_relative '../../spec_helper'
require_relative '../../support/swift_compiler'
require_relative '../../support/emitted_swift'
require 'swiftui/views/color_helper'
require 'swiftui/converter_factory'

RSpec.describe 'codegen of a facing link against a margined anchor' do
  include EmittedSwift

  # SwiftJsonUI's relative-positioning surface, mirrored from the declarations
  # (Classes/SwiftUI/RelativePosition/RelativePositionConstraint.swift and
  # RelativePositionContainer.swift, SwiftJsonUI 10.29.6) — every case and
  # every defaulted parameter, so an argument the library does not take
  # fails here as it would in a consumer build. The bodies draw nothing; the
  # arm checks that the emit type-checks against the library's signatures.
  RELATIVE_STUBS = <<~SWIFT
    struct RelativePositionConstraint {
        enum ConstraintType: String {
            case alignTop = "alignTopView"
            case alignBottom = "alignBottomView"
            case alignLeft = "alignLeftView"
            case alignRight = "alignRightView"
            case above = "alignTopOfView"
            case below = "alignBottomOfView"
            case leftOf = "alignLeftOfView"
            case rightOf = "alignRightOfView"
            case centerVertical = "alignCenterVerticalView"
            case centerHorizontal = "alignCenterHorizontalView"
            case parentTop = "alignTop"
            case parentBottom = "alignBottom"
            case parentLeft = "alignLeft"
            case parentRight = "alignRight"
            case parentCenterHorizontal = "centerHorizontal"
            case parentCenterVertical = "centerVertical"
            case parentCenter = "centerInParent"
        }
        let type: ConstraintType
        let targetId: String
        init(type: ConstraintType, targetId: String) { self.type = type; self.targetId = targetId }
    }
    enum RelativeSizeMode { case matchParent, wrapContent, fixed(CGFloat) }
    struct RelativeChildConfig: Identifiable {
        let id: String
        let view: AnyView
        init(id: String, view: AnyView, constraints: [RelativePositionConstraint] = [],
             margins: EdgeInsets = .init(), size: CGSize? = nil,
             widthMode: RelativeSizeMode = .wrapContent, heightMode: RelativeSizeMode = .wrapContent) {
            self.id = id
            self.view = view
        }
    }
    struct RelativePositionContainer: View {
        init(children: [RelativeChildConfig], alignment: Alignment = .topLeading,
             backgroundColor: Color? = nil, parentPadding: EdgeInsets = .init(),
             containerWidthMode: RelativeSizeMode = .wrapContent,
             containerHeightMode: RelativeSizeMode = .wrapContent) {}
        var body: some View { EmptyView() }
    }
  SWIFT

  before { SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {} }

  let(:layout) do
    {
      'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
      'child' => [
        { 'type' => 'View', 'id' => 'anchor', 'width' => 50, 'height' => 50,
          'topMargin' => 120, 'leftMargin' => 120, 'bottomMargin' => 30, 'rightMargin' => 30 },
        { 'type' => 'View', 'id' => 't_above', 'width' => 40, 'height' => 40, 'alignTopOfView' => 'anchor' },
        { 'type' => 'View', 'id' => 't_below', 'width' => 40, 'height' => 40, 'alignBottomOfView' => 'anchor' },
        { 'type' => 'View', 'id' => 't_left', 'width' => 40, 'height' => 40, 'alignLeftOfView' => 'anchor' },
        { 'type' => 'View', 'id' => 't_right', 'width' => 40, 'height' => 40, 'alignRightOfView' => 'anchor' }
      ]
    }
  end

  let(:swift) do
    factory = SjuiTools::SwiftUI::ConverterFactory.new
    factory.create_converter(layout, 0, nil, factory, nil).convert.to_s
  end

  # The text of one child's RelativeChildConfig(...) block.
  def config_of(id)
    start = swift.index("id: \"#{id}\"")
    raise "no RelativeChildConfig for #{id}" unless start

    rest = swift[start..]
    stop = rest.index('RelativeChildConfig(', 1) || rest.length
    rest[0...stop]
  end

  it 'routes the children through RelativePositionContainer' do
    expect(swift).to include('RelativePositionContainer(')
  end

  it "carries the anchor's four margins on its config, and places it with parentTop + parentLeft" do
    anchor = config_of('anchor')
    expect(anchor).to include('margins: EdgeInsets(top: 120, leading: 120, bottom: 30, trailing: 30)')
    expect(anchor).to include('RelativePositionConstraint(type: .parentTop, targetId: "")')
    expect(anchor).to include('RelativePositionConstraint(type: .parentLeft, targetId: "")')
    expect(anchor).not_to match(/\.padding\(\.(top|leading|bottom|trailing), 120\)/)
  end

  it 'type-checks against the library surface it names' do
    skip("swiftc: #{SwiftCompiler.unavailable_reason}") if SwiftCompiler.unavailable_reason

    expect(compilable_view(swift, stubs: RELATIVE_STUBS)).to compile_as_swift.with_imports('SwiftUI')
  end

  {
    't_above' => '.above', 't_below' => '.below', 't_left' => '.leftOf', 't_right' => '.rightOf'
  }.each do |id, type|
    it "emits #{id} as a #{type} constraint on the anchor" do
      expect(config_of(id)).to include("RelativePositionConstraint(type: #{type}, targetId: \"anchor\")")
    end
  end
end
