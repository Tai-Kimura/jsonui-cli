# frozen_string_literal: true

require 'json'
require 'set'
require_relative '../../lib/compose/compose_builder'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# A child of a SafeAreaView whose children are laid out in a ConstraintLayout
# (a sibling uses align*View & co.) is drawn as ConstraintLayoutComponent
# draws one (ticket kjui-align-to-view-in-visibility-wrapper-and-margin-sign).
# Measured on an emulator on 90 SafeAreaView variants of the margin and
# centre fixtures, 2.5.26 + the ConstraintLayout fixes: a View there was drawn
# by a local generator that put its margins as padding INSIDE its declared
# size — a 10pt child with a 10pt margin drew nothing, a 20pt centred child
# with leftMargin 10 drew 10pt wide — and left out its testTag (the child had
# no id on screen) and every other common stage; an align*View margin pulled
# outward. 70 of the 90 differed from the same fixtures in a View.
RSpec.describe 'kjui: a child of a SafeAreaView laid out with constraints' do
  def generate(children)
    node = { 'type' => 'SafeAreaView', 'id' => 'frame', 'width' => 100, 'height' => 100,
             'safeAreaInsetPositions' => [], 'child' => children }
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@required_imports, Set.new)
    builder.instance_variable_set(:@responsive_counter, 0)
    builder.send(:generate_component, JSON.parse(JSON.generate(node)), 1).to_s
  end

  ANCHOR40 = { 'type' => 'View', 'id' => 'a', 'width' => 40, 'height' => 40, 'leftMargin' => 30, 'topMargin' => 30 }.freeze

  # The modifier chain of the child *id*, from its constrainAs to its testTag.
  def chain(code, id)
    code[/constrainAs\(#{id}\) \{.*?\.testTag\("#{id}"\)/m] or raise "no chain for #{id} in:\n#{code}"
  end

  it 'draws a margined anchor’s margins outside its size, with its testTag' do
    c = chain(generate([ANCHOR40, { 'type' => 'View', 'id' => 's', 'width' => 10, 'height' => 10, 'alignTopView' => 'a' }]), 'a')
    expect(c.index('.padding(top = 30.dp)')).to be < c.index('.requiredWidth(40.dp)')
  end

  it 'pushes an align*View margin inward, in the link, and draws the child at its size' do
    code = generate([ANCHOR40, { 'type' => 'View', 'id' => 's', 'width' => 10, 'height' => 10, 'alignTopView' => 'a', 'topMargin' => 4,
                                 'leftMargin' => 7 }])
    c = chain(code, 's')
    expect(c).to include('top.linkTo(a.top, margin = (30.dp + 4.dp))').and include('start.linkTo(parent.start, margin = 7.dp)')
    expect(c).not_to include('.padding(')
  end

  it 'moves a centred child back to the centre, and links a sibling to what it draws' do
    code = generate([{ 'type' => 'View', 'id' => 'c', 'width' => 20, 'height' => 20, 'centerHorizontal' => true, 'leftMargin' => 10 },
                     { 'type' => 'View', 'id' => 'k', 'width' => 6, 'height' => 6, 'alignLeftOfView' => 'c' }])
    expect(chain(code, 'c')).to include('}.offset(x = -5.dp)')
    expect(chain(code, 'k')).to include('end.linkTo(c.start, margin = ((-10.dp) + 5.dp))')
  end

  it 'gives a data-only child no ref and draws nothing for it' do
    code = generate([{ 'data' => [{ 'name' => 'title', 'class' => 'String' }] }, ANCHOR40,
                     { 'type' => 'View', 'id' => 's', 'width' => 10, 'height' => 10, 'alignTopView' => 'a' }])
    expect(code.scan('createRef()').size).to eq(2)
    expect(code.scan(/^\s*Box\(/).size).to eq(2)
  end

  it 'compiles' do
    shapes = [
      [ANCHOR40, { 'type' => 'View', 'id' => 's', 'width' => 10, 'height' => 10, 'alignTopView' => 'a', 'topMargin' => 4, 'leftMargin' => 7 }],
      [{ 'type' => 'View', 'id' => 'c', 'width' => 20, 'height' => 20, 'centerHorizontal' => true, 'leftMargin' => 10 },
       { 'type' => 'View', 'id' => 'k', 'width' => 6, 'height' => 6, 'alignLeftOfView' => 'c', 'visibility' => '@{vis}' }]
    ]
    emitted = shapes.each_with_index.map { |children, i| "@Composable\nfun emitted#{i}(data: Data) {\n#{generate(children)}\n}" }.join("\n\n")
    expect(<<~KOTLIN).to compile_as_kotlin
      annotation class Composable
      #{ComposeStubUniverse.common_stages(emitted)}
      class Data { val vis: String = "visible" }
      operator fun Dp.plus(o: Dp) = Dp(value + o.value)
      operator fun Dp.unaryMinus() = Dp(-value)
      fun Modifier.offset(x: Dp = 0.dp, y: Dp = 0.dp): Modifier = this
      class HorizontalAnchor
      class VerticalAnchor
      class HorizontalAnchorable { fun linkTo(anchor: HorizontalAnchor, margin: Dp = 0.dp) {} }
      class VerticalAnchorable { fun linkTo(anchor: VerticalAnchor, margin: Dp = 0.dp) {} }
      class ConstrainedLayoutReference { val top = HorizontalAnchor(); val bottom = HorizontalAnchor(); val start = VerticalAnchor(); val end = VerticalAnchor() }
      class ConstrainScope { val top = HorizontalAnchorable(); val bottom = HorizontalAnchorable(); val start = VerticalAnchorable(); val end = VerticalAnchorable(); val parent = ConstrainedLayoutReference() }
      interface ConstraintLayoutScope {
          fun createRef(): ConstrainedLayoutReference = ConstrainedLayoutReference()
          fun Modifier.constrainAs(ref: ConstrainedLayoutReference, constrainBlock: ConstrainScope.() -> Unit): Modifier = this
      }
      fun ConstraintLayout(modifier: Modifier = Modifier, content: ConstraintLayoutScope.() -> Unit) {}
      fun VisibilityWrapper(visibility: String, modifier: Modifier = Modifier, content: BoxScope.() -> Unit) {}
      #{emitted}
    KOTLIN
  end
end
