# frozen_string_literal: true

require 'swiftui/json_to_swiftui_converter'

# What a PARENT draws from its child's attributes — a RelativePositionContainer's constraints, margins and size modes,
# a stack's Spacers and alignment wrapper — is drawn outside the child's own function (responsive0), so a size class
# that overrides one must be drawn there, per size class (ticket sjui-responsive-align-center-overrides-are-not-drawn).
# Written only under `responsive`, alignTop … centerInParent drew nothing on 112 of 112 drawn pairs (16 types × 7
# keys), and a margin override under a RelativePositionContainer was ADDED to the base margin (the container's inset
# plus the function's padding).
#
# The Swift these arms pin was also built against SwiftJsonUI 10.30.8 and drawn on an iPhone 17 (iOS 27.2) simulator,
# compact and regular, when the ticket was fixed. Here it is type-checked against the library's declarations,
# transcribed (relative_stubs): the conditional constraints, the per-size-class EdgeInsets and size modes, the
# conditional Spacer and frame.
RSpec.describe SjuiTools::SwiftUI::JsonToSwiftUIConverter, 'responsive attributes the parent draws' do
  let(:converter) { described_class.new }
  let(:temp_dir) { File.realpath(Dir.mktmpdir('responsive_parent_drawn')) }
  let(:regular) { 'horizontalSizeClass == .regular' }

  before do
    allow(SjuiTools::SwiftUI::StyleLoader).to receive(:load_and_merge) { |data| data }
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
    FileUtils.rm_rf(temp_dir)
  end

  def swift(parent_extra, child)
    file = File.join(temp_dir, "l#{rand(1 << 30)}.json")
    File.write(file, JSON.generate({ 'type' => 'View', 'width' => 200, 'height' => 100,
                                     'child' => [{ 'type' => 'Label', 'id' => 'x', 'text' => 'X' }.merge(child)] }.merge(parent_extra)))
    code, _actions, _state, _children, funcs = converter.convert_json_to_view(file)
    ([code] + funcs).join("\n")
  end

  # SwiftJsonUI 10.30.8 RelativePositionConstraint.swift, RelativePositionContainer.swift and VisibilityWrapper.swift,
  # transcribed: the signatures, not the behaviour. The compiler reads a macOS SDK, which has no horizontalSizeClass:
  # the host declares the two size classes as plain properties of a type with the same cases.
  # A method, not a constant: a constant here is a top-level one, and relative_facing_link_emit_spec defines its own
  # RELATIVE_STUBS (spec_constants_are_scoped_spec).
  def relative_stubs
    <<~SWIFT
    struct RelativePositionConstraint {
        enum ConstraintType: String {
            case alignTop, alignBottom, alignLeft, alignRight, above, below, leftOf, rightOf, centerVertical, centerHorizontal
            case parentTop, parentBottom, parentLeft, parentRight, parentCenterHorizontal, parentCenterVertical, parentCenter
        }
        let type: ConstraintType
        let targetId: String
        init(type: ConstraintType, targetId: String) { self.type = type; self.targetId = targetId }
    }
    enum RelativeSizeMode { case matchParent, wrapContent, fixed(CGFloat) }
    struct RelativeChildConfig {
        init(id: String, view: AnyView, constraints: [RelativePositionConstraint] = [], margins: EdgeInsets = .init(),
             size: CGSize? = nil, widthMode: RelativeSizeMode = .wrapContent, heightMode: RelativeSizeMode = .wrapContent) {}
    }
    struct RelativePositionContainer: View {
        init(children: [RelativeChildConfig], alignment: Alignment = .topLeading, backgroundColor: Color? = nil,
             parentPadding: EdgeInsets = .init(), containerWidthMode: RelativeSizeMode = .wrapContent,
             containerHeightMode: RelativeSizeMode = .wrapContent) {}
        var body: some View { EmptyView() }
    }
    struct VisibilityWrapper<Content: View>: View {
        init(_ visibilityString: String?, @ViewBuilder content: () -> Content) {}
        var body: some View { EmptyView() }
    }
    enum SizeClassStub { case compact, regular }
  SWIFT
  end

  it 'type-checks: constraints, margins, size modes, visibility, Spacers and the wrapper, per size class' do
    file = File.join(temp_dir, 'all.json')
    relative = { 'type' => 'View', 'width' => 200, 'height' => 100, 'child' => [
      { 'type' => 'Label', 'id' => 'a', 'text' => 'A', 'alignTop' => true, 'topMargin' => 10,
        'responsive' => { 'regular' => { 'alignTop' => false, 'alignBottom' => true, 'alignRightView' => 'b', 'topMargin' => 30,
                                          'width' => 80, 'visibility' => 'gone' } } },
      { 'type' => 'Label', 'id' => 'b', 'text' => 'B', 'responsive' => { 'regular' => { 'centerInParent' => true } } }
    ] }
    stack = ->(o) { { 'type' => 'View', 'orientation' => o, 'width' => 200, 'height' => 60, 'child' => [
      { 'type' => 'Label', 'id' => "s#{o[0]}", 'text' => 'S', 'responsive' => { 'regular' => { 'alignRight' => true, 'alignBottom' => true } } }
    ] } }
    File.write(file, JSON.generate({ 'type' => 'View', 'orientation' => 'vertical', 'child' => [relative, stack.('horizontal'), stack.('vertical')] }))
    code, _actions, _state, _children, funcs = converter.convert_json_to_view(file)
    swift = <<~SWIFT
      #{relative_stubs}
      struct EmittedHost: View {
          var horizontalSizeClass: SizeClassStub? = .regular
          var verticalSizeClass: SizeClassStub? = .regular
          var body: some View {
      #{code}
          }
      #{funcs.join("\n")}
      }
    SWIFT
    expect(swift).to include('compactMap { $0 }').and include('if (horizontalSizeClass == .regular ? true : false) { Spacer() }')
    expect(swift).to compile_as_swift.with_imports('SwiftUI')
  end

  describe 'under a RelativePositionContainer' do
    it 'makes the parent relative and draws an align flag written only in a size class' do
      code = swift({}, 'responsive' => { 'regular' => { 'alignRight' => true } })
      expect(code).to include('RelativePositionContainer(')
      expect(code).to include("(#{regular} ? true : false) ? RelativePositionConstraint(type: .parentRight, targetId: \"\") : nil")
      # the default branch keeps its default placement
      expect(code).to include("(#{regular} ? false : true) ? RelativePositionConstraint(type: .parentTop, targetId: \"\") : nil")
      expect(code).to include('] as [RelativePositionConstraint?]).compactMap { $0 },')
    end

    it 'switches a base flag off and another on per size class' do
      code = swift({}, 'alignTop' => true, 'responsive' => { 'regular' => { 'alignTop' => false, 'alignBottom' => true } })
      expect(code).to include("(#{regular} ? false : true) ? RelativePositionConstraint(type: .parentTop, targetId: \"\") : nil")
      expect(code).to include("(#{regular} ? true : false) ? RelativePositionConstraint(type: .parentBottom, targetId: \"\") : nil")
    end

    it 'keeps a constraint every size class declares unconditional' do
      code = swift({}, 'alignLeft' => true, 'responsive' => { 'regular' => { 'centerVertical' => true } })
      expect(code).to include("RelativePositionConstraint(type: .parentLeft, targetId: \"\"),\n")
      expect(code).not_to include('? RelativePositionConstraint(type: .parentLeft')
    end

    it 'draws a view-relative target per size class' do
      code = swift({}, 'alignTop' => true, 'responsive' => { 'regular' => { 'alignLeftView' => 'x' } })
      expect(code).to include("(#{regular} ? true : false) ? RelativePositionConstraint(type: .alignLeft, targetId: \"x\") : nil")
    end

    it 'takes a margin override instead of the base margin, once' do
      code = swift({}, 'alignTop' => true, 'topMargin' => 10, 'responsive' => { 'regular' => { 'topMargin' => 30 } })
      expect(code).to include("margins: EdgeInsets(top: (#{regular} ? 30 : 10), leading: 0, bottom: 0, trailing: 0),")
      expect(code).not_to include('.padding(.top, 30)')   # the function no longer adds it as padding
    end

    it 'draws a size override as the container sees it' do
      code = swift({}, 'alignTop' => true, 'responsive' => { 'regular' => { 'width' => 80 } })
      expect(code).to include("widthMode: (#{regular} ? RelativeSizeMode.fixed(80) : RelativeSizeMode.wrapContent),")
    end

    it 'wraps a visibility override as outside the container' do
      code = swift({}, 'alignTop' => true, 'responsive' => { 'regular' => { 'visibility' => 'gone' } })
      expect(code).to match(/VisibilityWrapper\(\(#{Regexp.escape(regular)} \? /)
    end

    it 'leaves a child without overrides as it was' do
      code = swift({}, 'alignTop' => true, 'topMargin' => 10)
      expect(code).to include("constraints: [\n")
      expect(code).to include('margins: EdgeInsets(top: 10, leading: 0, bottom: 0, trailing: 0),')
      expect(code).to include('widthMode: .wrapContent,')
      expect(code).not_to include('horizontalSizeClass')
    end
  end

  describe 'in a stack' do
    it 'draws the Spacer and the wrapper of a horizontal stack per size class' do
      code = swift({ 'orientation' => 'horizontal' }, 'responsive' => { 'regular' => { 'alignRight' => true, 'alignBottom' => true } })
      expect(code).to include("if (#{regular} ? true : false) { Spacer() }")
      expect(code).to include(".frame(maxHeight: ((#{regular} ? true : false) ? CGFloat.infinity : nil), " \
                              "alignment: (#{regular} ? Alignment.bottom : Alignment.center))")
    end

    it 'draws the vertical stack the other way round' do
      code = swift({ 'orientation' => 'vertical' }, 'alignLeft' => true, 'responsive' => { 'regular' => { 'alignLeft' => false, 'alignRight' => true } })
      expect(code).to include('}.frame(maxWidth: .infinity, alignment: ' \
                              "(#{regular} ? Alignment.trailing : Alignment.leading))")
    end

    it 'takes the flags out of the child, base and size classes, as the stack draws them' do
      code = swift({ 'orientation' => 'horizontal' }, 'responsive' => { 'regular' => { 'alignBottom' => true } })
      function = code[/private func responsive0.*/m]
      expect(function).not_to include('alignment: .bottom')
      expect(function).not_to include('maxHeight: .infinity')
    end
  end
end
