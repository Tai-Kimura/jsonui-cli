# frozen_string_literal: true

require 'swiftui/json_to_swiftui_converter'

# A child placed by a RelativePositionContainer (alignLeft, alignBottom, …) is wrapped in a VisibilityWrapper for a
# literal visibility too, as every other parent wraps it (ResponsiveHelper.visibility_declared?). Through 2.5.22 the
# container wrapped a binding only: a literal "gone" / "invisible" was drawn — Android does not draw it — and an
# include's `data` turns a bound visibility into a literal one, which is how it was met (ticket
# sjui-relative-child-literal-visibility-dropped).
#
# Measured on an iPhone 17 (iOS 27.2) simulator when the ticket was fixed, a 40×40 red child at parentLeft +
# parentBottom of a 100×100 container: the 2.5.22 shape (no wrapper) drew 1600 red pixels, VisibilityWrapper("gone")
# and ("invisible") 0, ("visible") 1600 — and Dynamic, which wraps any spelling, the same 0 / 0 / 1600.
RSpec.describe SjuiTools::SwiftUI::JsonToSwiftUIConverter, 'a relative child with a literal visibility' do
  let(:converter) { described_class.new }
  let(:temp_dir) { File.realpath(Dir.mktmpdir('relative_child_literal_visibility')) }

  before do
    allow(SjuiTools::SwiftUI::StyleLoader).to receive(:load_and_merge) { |data| data }
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
    FileUtils.rm_rf(temp_dir)
  end

  def swift(child, parent = {})
    file = File.join(temp_dir, "l#{rand(1 << 30)}.json")
    badge = { 'type' => 'Label', 'id' => 'badge', 'text' => 'x', 'width' => 'wrapContent', 'height' => 'wrapContent' }
    File.write(file, JSON.generate({ 'type' => 'View', 'id' => 'frame', 'width' => 100, 'height' => 100,
                                     'child' => [badge.merge(child), { 'type' => 'Label', 'id' => 'sib', 'text' => 'y' }] }
                                     .merge(parent)))
    code, _actions, _state, _children, funcs = converter.convert_json_to_view(file)
    ([code] + Array(funcs)).join("\n")
  end

  def wrappers(code)
    code.scan(/VisibilityWrapper\((.*)\) \{/).flatten
  end

  relative = { 'alignLeft' => true, 'alignBottom' => true }.freeze
  # the container's other branch: a child with padding and a background has them drawn outside its function
  padded = { 'alignLeft' => true, 'paddings' => 4, 'background' => '#FF0000' }.freeze

  { 'gone' => '"gone"', 'invisible' => '"invisible"', 'visible' => '"visible"', '@{v}' => 'data.v' }.each do |value, param|
    [['relative', relative], ['relative with padding and background', padded]].each do |name, placement|
      it "wraps #{value} under a #{name} placement as a column does" do
        code = swift(placement.merge('visibility' => value))
        expect(code).to include('RelativePositionContainer')
        expect(wrappers(code)).to eq([param])
        # the control: the same child in a column is wrapped with the same argument
        column = swift({ 'visibility' => value }, { 'orientation' => 'vertical' })
        expect(column).not_to include('RelativePositionContainer')
        expect(wrappers(column)).to eq(wrappers(code))
      end
    end
  end

  it 'wraps the child inside its RelativeChildConfig, around the child' do
    code = swift(relative.merge('visibility' => 'gone'))
    config = code[/RelativeChildConfig\(\s*id: "badge",.*?\n\s*constraints:/m]
    expect(config).to match(/view: AnyView\(\s*VisibilityWrapper\("gone"\) \{\s*PartialAttributedText\(.*accessibilityIdentifier\("badge"\)\s*\}\s*\),/m)
  end

  it 'leaves a child that declares none unwrapped' do
    expect(wrappers(swift(relative))).to eq([])
  end

  # SwiftJsonUI 10.35.0 RelativePositionContainer.swift, RelativePositionConstraint.swift and VisibilityWrapper.swift,
  # transcribed: the signatures, not the behaviour (as responsive_parent_drawn_attributes_spec's).
  def relative_stubs
    <<~SWIFT
      struct RelativePositionConstraint {
          enum ConstraintType: String {
              case alignTop, alignBottom, alignLeft, alignRight, above, below, leftOf, rightOf, centerVertical, centerHorizontal
              case parentTop, parentBottom, parentLeft, parentRight, parentCenterHorizontal, parentCenterVertical, parentCenter
          }
          init(type: ConstraintType, targetId: String) {}
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
    SWIFT
  end

  it 'type-checks, every spelling on both branches' do
    file = File.join(temp_dir, 'all.json')
    children = %w[gone invisible visible @{v}].each_with_index.flat_map do |value, i|
      [{ 'type' => 'Label', 'id' => "plain#{i}", 'text' => 'x', 'visibility' => value }.merge(relative),
       { 'type' => 'Label', 'id' => "padded#{i}", 'text' => 'x', 'visibility' => value }.merge(padded)]
    end
    File.write(file, JSON.generate({ 'type' => 'View', 'width' => 100, 'height' => 100, 'child' => children }))
    code, _actions, _state, _children, funcs = converter.convert_json_to_view(file)
    expect(funcs.to_a).to be_empty
    expect(wrappers(code).size).to eq(8)
    expect(compilable_view(code, data: ['var v: String? = nil'], stubs: relative_stubs))
      .to compile_as_swift.with_imports('SwiftUI')
  end

  it 'still takes a size class override per size class' do
    code = swift(relative.merge('visibility' => 'gone', 'responsive' => { 'regular' => { 'visibility' => 'visible' } }))
    expect(wrappers(code).size).to eq(1)
    expect(wrappers(code).first).to include('horizontalSizeClass == .regular', '"visible"', '"gone"')
  end
end
