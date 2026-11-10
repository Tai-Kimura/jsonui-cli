# frozen_string_literal: true

require 'json'
require 'set'
require_relative '../../lib/compose/compose_builder'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# A ConstraintLayout child with a visibility is constrained on its
# VisibilityWrapper (ticket kjui-align-to-view-in-visibility-wrapper-and-
# margin-sign). VisibilityHelper wraps the child in `VisibilityWrapper(...) {
# ... }`, whose content lambda is a BoxScope; constrainAs is the
# ConstraintLayout scope's, and inside that lambda it "cannot be called in
# this context with an implicit receiver". Measured on jsonui-cli 2.5.26 in a
# sample-app copy with Gradle: every such child failed to compile — the six
# align*View keys, align*OfView, a parent alignment, an anchor with no
# constraint, a literal "gone" — and on the SafeAreaView path a View dropped
# its visibility altogether (always drawn). The wrapper is the
# ConstraintLayout's child; constrainAs now goes on its modifier.
RSpec.describe 'kjui: a ConstraintLayout child with a visibility' do
  def generate(children, root: 'View')
    node = { 'type' => root, 'id' => 'frame', 'width' => 100, 'height' => 100, 'child' => children }
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@required_imports, Set.new)
    builder.instance_variable_set(:@responsive_counter, 0)
    builder.send(:generate_component, JSON.parse(JSON.generate(node)), 1).to_s
  end

  def box(id, extra = {})
    { 'type' => 'View', 'id' => id, 'width' => 20, 'height' => 20 }.merge(extra)
  end

  VIS_ANCHOR = { 'type' => 'View', 'id' => 'a', 'width' => 40, 'height' => 40, 'leftMargin' => 30, 'topMargin' => 30 }.freeze

  # The VisibilityWrapper call of *ref*: its argument list and its content.
  def wrapper(code, ref)
    m = code.match(/VisibilityWrapper\((?<args>(?:(?!\) \{).)*?constrainAs\(#{ref}\)(?:(?!\) \{).)*?)\n\s*\) \{(?<body>.*?)\n\s*\}\n\s*\}/m)
    raise "no VisibilityWrapper constrained to #{ref} in:\n#{code}" unless m

    m
  end

  VIS_CASES = {
    'alignTopView' => [VIS_ANCHOR, { 'type' => 'View', 'id' => 's', 'width' => 10, 'height' => 10, 'alignTopView' => 'a', 'visibility' => '@{vis}' }],
    'alignTopOfView' => [VIS_ANCHOR, { 'type' => 'View', 'id' => 's', 'width' => 10, 'height' => 10, 'alignTopOfView' => 'a', 'visibility' => '@{vis}' }],
    'a literal gone' => [VIS_ANCHOR, { 'type' => 'View', 'id' => 's', 'width' => 10, 'height' => 10, 'alignLeftView' => 'a', 'visibility' => 'gone' }],
    'hidden' => [VIS_ANCHOR, { 'type' => 'View', 'id' => 's', 'width' => 10, 'height' => 10, 'alignLeftView' => 'a', 'hidden' => '@{h}' }],
    'a Label' => [VIS_ANCHOR, { 'type' => 'Label', 'id' => 's', 'text' => 'x', 'alignTopView' => 'a', 'visibility' => '@{vis}' }]
  }.freeze

  VIS_CASES.each do |name, children|
    it "constrains the wrapper, not what it wraps — #{name}" do
      [nil, 'SafeAreaView'].each do |root|
        code = root ? generate(children, root: root) : generate(children)
        m = wrapper(code, 's')
        expect(m[:args]).to include('modifier = Modifier.constrainAs(s) {'), root.to_s
        expect(m[:body]).not_to include('constrainAs'), root.to_s
      end
    end
  end

  it 'constrains an anchor that has a visibility, and links the others to it' do
    code = generate([VIS_ANCHOR.merge('visibility' => '@{vis}'), box('s', 'alignTopView' => 'a')])
    expect(wrapper(code, 'a')[:args]).to include('modifier = Modifier.constrainAs(a) {')
    expect(code).to include('top.linkTo(a.top')
  end

  it 'leaves a child with no visibility as it was' do
    code = generate([VIS_ANCHOR, box('s', 'alignTopView' => 'a')])
    expect(code).not_to include('VisibilityWrapper')
    expect(code).to match(/Box\(\s*\n\s*modifier = Modifier\.constrainAs\(s\)/)
  end

  # Against stubs whose scopes carry a DslMarker, as Compose's do: inside the
  # wrapper's BoxScope content the ConstraintLayout scope's constrainAs is not
  # callable — what Gradle stopped on — and on the wrapper it is.
  it 'compiles, on both paths' do
    emitted = VIS_CASES.values.flat_map do |children|
      [generate(children), generate(children, root: 'SafeAreaView')]
    end.each_with_index.map { |code, i| "@Composable\nfun emitted#{i}(data: Data) {\n#{code}\n}" }.join("\n\n")
    expect(<<~KOTLIN).to compile_as_kotlin
      annotation class Composable
      @DslMarker annotation class LayoutScopeMarker
      #{ComposeStubUniverse.common_stages(emitted)}
      class Data { val vis: String = "visible"; val h: Boolean = false }
      class HorizontalAnchor
      class VerticalAnchor
      operator fun Dp.plus(o: Dp) = Dp(value + o.value)
      operator fun Dp.unaryMinus() = Dp(-value)
      class HorizontalAnchorable { fun linkTo(anchor: HorizontalAnchor, margin: Dp = 0.dp) {} }
      class VerticalAnchorable { fun linkTo(anchor: VerticalAnchor, margin: Dp = 0.dp) {} }
      class ConstrainedLayoutReference { val top = HorizontalAnchor(); val bottom = HorizontalAnchor(); val start = VerticalAnchor(); val end = VerticalAnchor() }
      class ConstrainScope { val top = HorizontalAnchorable(); val bottom = HorizontalAnchorable(); val start = VerticalAnchorable(); val end = VerticalAnchorable(); val parent = ConstrainedLayoutReference() }
      @LayoutScopeMarker interface ConstraintLayoutScope {
          fun createRef(): ConstrainedLayoutReference = ConstrainedLayoutReference()
          fun Modifier.constrainAs(ref: ConstrainedLayoutReference, constrainBlock: ConstrainScope.() -> Unit): Modifier = this
      }
      // The wrapper's content scope, marked as Compose's layout scopes are.
      @LayoutScopeMarker interface WrapperScope : BoxScope
      fun ConstraintLayout(modifier: Modifier = Modifier, content: ConstraintLayoutScope.() -> Unit) {}
      fun VisibilityWrapper(visibility: String, modifier: Modifier = Modifier, content: WrapperScope.() -> Unit) {}
      fun VisibilityWrapper(hidden: Boolean, modifier: Modifier = Modifier, content: WrapperScope.() -> Unit) {}
      #{emitted}
    KOTLIN
  end
end
