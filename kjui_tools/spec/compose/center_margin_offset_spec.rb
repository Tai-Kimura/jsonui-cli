# frozen_string_literal: true

require 'json'
require 'set'
require_relative '../../lib/compose/compose_builder'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# A child centred on an axis (centerHorizontal / centerVertical /
# centerInParent) with margins on that axis (ticket kjui-align-to-view-in-
# visibility-wrapper-and-margin-sign). Its margins are drawn as padding, so
# the box it is centred by — and a wrapContent parent's size — includes them,
# as on iOS and the Android Dynamic renderer; the padding put the content off
# centre by half the difference of the two margins. Measured by triage
# support 2 on 2.5.26: a 20pt child with centerHorizontal + leftMargin 10 in
# a 100pt frame was at x=45, iOS and Dynamic at 40; with leftMargin 10 and
# rightMargin 30 in a wrapContent parent, the parent 60×20 on every face and
# the child at x=10 (iOS, Dynamic: 20). `.offset` moves it back by half the
# difference, on the axis the child centres on only.
RSpec.describe 'kjui: a centred child with margins on its axis' do
  def generate(children, frame: { 'width' => 100, 'height' => 100 })
    node = { 'type' => 'View', 'id' => 'frame', 'child' => children }.merge(frame)
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@required_imports, Set.new)
    builder.instance_variable_set(:@responsive_counter, 0)
    code = builder.send(:generate_component, JSON.parse(JSON.generate(node)), 1).to_s
    [code, builder.instance_variable_get(:@required_imports)]
  end

  def s(extra)
    { 'type' => 'View', 'id' => 's', 'width' => 20, 'height' => 20 }.merge(extra)
  end

  # The modifier chain of `s` (Box path) or its constrainAs block and what
  # follows it (ConstraintLayout path).
  def chain(code, id = 's')
    code[/modifier = Modifier[^\n]*\n(?:(?!\) \{).)*?\.testTag\("#{id}"\)/m] or raise "no chain for #{id} in:\n#{code}"
  end

  describe 'in a plain overlay (Box)' do
    {
      { 'centerHorizontal' => true, 'leftMargin' => 10 } => '.offset(x = -5.dp)',
      { 'centerHorizontal' => true, 'leftMargin' => 10, 'rightMargin' => 30 } => '.offset(x = 10.dp)',
      { 'centerVertical' => true, 'topMargin' => 10 } => '.offset(y = -5.dp)',
      { 'centerInParent' => true, 'leftMargin' => 10, 'bottomMargin' => 4 } => '.offset(x = -5.dp, y = 2.dp)',
      { 'centerInParent' => true, 'margins' => [10, 20, 30, 40] } => '.offset(x = -10.dp, y = 10.dp)'
    }.each do |attrs, offset|
      it "moves the content back by half the difference — #{attrs.keys.join(' ')}" do
        code, imports = generate([s(attrs)])
        expect(chain(code)).to include(offset)
        expect(imports).to include(:offset)
      end
    end

    it 'keeps the margins as padding (a wrapContent parent includes them)' do
      code, = generate([s('centerHorizontal' => true, 'leftMargin' => 10, 'rightMargin' => 30)],
                       frame: { 'width' => 'wrapContent', 'height' => 'wrapContent' })
      expect(chain(code)).to include('.padding(start = 10.dp)').and include('.padding(end = 30.dp)')
    end

    it 'moves nothing on an axis the child does not centre on, or with equal margins' do
      [{ 'centerHorizontal' => true, 'topMargin' => 10 },
       { 'centerHorizontal' => true, 'leftMargin' => 10, 'rightMargin' => 10 },
       { 'alignRight' => true, 'leftMargin' => 10 },
       { 'leftMargin' => 10 }].each do |attrs|
        code, = generate([s(attrs)])
        expect(chain(code)).not_to include('.offset('), attrs.inspect
      end
    end

    it 'moves a bound margin by an expression, and a bound centre only when it holds' do
      code, = generate([s('centerHorizontal' => '@{centred}', 'leftMargin' => '@{gap}')])
      expect(chain(code)).to include('.offset(x = (if ((data.centred ?: false)) ((0.dp - (data.gap?.dp ?: 0.dp)) / 2) else 0.dp))')
    end
  end

  describe 'in a ConstraintLayout (a sibling has a constraint)' do
    let(:anchor) { { 'type' => 'View', 'id' => 'a', 'width' => 6, 'height' => 6 } }

    it 'offsets a centred child that has no other constraint' do
      code, = generate([s('centerHorizontal' => true, 'leftMargin' => 10), anchor.merge('alignLeftOfView' => 's')])
      expect(code).to match(/constrainAs\(s\) \{\s*start\.linkTo\(parent\.start\)\s*end\.linkTo\(parent\.end\)\s*\}\.offset\(x = -5\.dp\)/)
    end

    it 'puts a positioned child’s margins in its centre links, and offsets it' do
      code, = generate([s('centerHorizontal' => true, 'alignTop' => true, 'leftMargin' => 10, 'rightMargin' => 30), anchor.merge('alignLeftOfView' => 's')])
      block = code[/constrainAs\(s\) \{.*?\}[^\n]*/m]
      expect(block).to include('start.linkTo(parent.start, margin = 10.dp)').and include('end.linkTo(parent.end, margin = 30.dp)')
      expect(block).to end_with('}.offset(x = 10.dp)')
    end

    # The offset moves what the child draws, not its ref box: a sibling
    # aligned to it adds the offset to reach the drawn edge.
    it 'links a sibling to the edge the centred child draws' do
      code, = generate([s('centerHorizontal' => true, 'leftMargin' => 10),
                        anchor.merge('alignLeftOfView' => 's'),
                        anchor.merge('id' => 'q', 'alignRightOfView' => 's')])
      expect(code).to include('end.linkTo(s.start, margin = ((-10.dp) + 5.dp))')
      expect(code).to include('start.linkTo(s.end, margin = (-5.dp))')
    end
  end

  it 'compiles' do
    shapes = [
      [s('centerInParent' => true, 'leftMargin' => 10, 'bottomMargin' => 4)],
      [s('centerHorizontal' => '@{centred}', 'leftMargin' => '@{gap}')],
      [s('centerHorizontal' => true, 'leftMargin' => 10), { 'type' => 'View', 'id' => 'a', 'width' => 6, 'height' => 6, 'alignLeftOfView' => 's' }],
      [s('centerVertical' => true, 'alignLeft' => true, 'topMargin' => 10), { 'type' => 'View', 'id' => 'a', 'width' => 6, 'height' => 6, 'alignTopOfView' => 's' }]
    ]
    emitted = shapes.each_with_index.map { |children, i| "@Composable\nfun emitted#{i}(data: Data) {\n#{generate(children).first}\n}" }.join("\n\n")
    expect(<<~KOTLIN).to compile_as_kotlin
      annotation class Composable
      #{ComposeStubUniverse.common_stages(emitted)}
      class Data { val centred: Boolean? = true; val gap: Int? = 10 }
      class BiasAlignment(val horizontalBias: Float, val verticalBias: Float) { class Horizontal(val bias: Float); class Vertical(val bias: Float) }
      fun Modifier.align(alignment: Any): Modifier = this
      fun Modifier.wrapContentWidth(align: BiasAlignment.Horizontal, unbounded: Boolean): Modifier = this
      fun Modifier.wrapContentHeight(align: BiasAlignment.Vertical, unbounded: Boolean): Modifier = this
      operator fun Dp.plus(o: Dp) = Dp(value + o.value)
      operator fun Dp.minus(o: Dp) = Dp(value - o.value)
      operator fun Dp.div(n: Int) = Dp(value / n)
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
      #{emitted}
    KOTLIN
  end
end
