# frozen_string_literal: true

require 'compose/helpers/section_extractor'
require 'compose/compose_builder'
require 'json'
require 'set'
require_relative '../../support/kotlin_compiler'
require_relative '../../support/compose_stub_universe'

# A ConstraintLayout's content is never split (ticket kjui-align-to-view-in-
# visibility-wrapper-and-margin-sign). `val x = createRef()` and
# `Modifier.constrainAs(x) { ... }` are ConstraintLayoutScope's. A client cell
# big enough to split — a card and, beside it, an include aligned to it — had
# its ConstraintLayout's children lifted into SectionN helpers: Gradle said
# "Unresolved reference 'createRef'", then 'constrainAs', 'top', 'end' (20
# errors in three cells, built on jsonui-cli with the visibility and margin
# fixes; 0 after). A data-only child got a ref of its own too, a line that
# drew nothing and was lifted alone.
RSpec.describe KjuiTools::Compose::Helpers::SectionExtractor do
  let(:opts) { { view_name: 'Probe', data_type: 'ProbeData', viewmodel_type: 'ProbeViewModel' } }

  def label(i)
    { 'type' => 'Label', 'id' => "l#{i}", 'text' => "t#{i}", 'width' => 'matchParent' }
  end

  # A card (a Row of two Columns of five Labels, enough to split) and a
  # sibling aligned to it, in a ConstraintLayout; a data-only child first, as
  # the client cells have.
  def tree
    card = { 'type' => 'View', 'id' => 'card', 'orientation' => 'horizontal', 'width' => 'matchParent', 'height' => 'wrapContent',
             'onClick' => '@{onTap}',
             'child' => (0...2).map { |r| { 'type' => 'View', 'orientation' => 'vertical', 'width' => 'wrapContent', 'child' => (0...5).map { |i| label(r * 100 + i) } } } }
    { 'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'wrapContent', 'child' => [
      { 'data' => [{ 'name' => 'title', 'class' => 'String' }] }, card,
      { 'type' => 'View', 'id' => 'badge', 'width' => 16, 'height' => 16, 'alignTopView' => 'card', 'alignRightView' => 'card',
        'topMargin' => 4, 'rightMargin' => 4, 'visibility' => '@{badgeVisibility}' }
    ] }
  end

  def body
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@required_imports, Set.new)
    builder.instance_variable_set(:@responsive_counter, 0)
    builder.send(:generate_component, JSON.parse(JSON.generate(tree)), 1).to_s
  end

  # The lifted functions that hold ConstraintLayoutScope's calls without the
  # ConstraintLayout that provides it.
  def stranded(fns)
    fns.map(&:to_s).reject { |fn| fn.include?('ConstraintLayout(') }
       .select { |fn| fn.include?('createRef(') || fn.include?('.constrainAs(') }
  end

  it 'gives a data-only child no ref' do
    expect(body.scan('createRef()').size).to eq(2)
    expect(body).not_to include('val view_0 = createRef()')
  end

  # The extractor's half on its own: the ref line a data-only child had —
  # one that nothing references, so no sibling holds it — put back by hand.
  it 'splits the cell, and lifts no ConstraintLayout child without its ConstraintLayout' do
    code = body.sub(/^(\s*)val card = createRef\(\)/) { "#{$1}val view_0 = createRef()\n#{$1}val card = createRef()" }
    expect(code).to include('val view_0 = createRef()')
    new_body, fns = described_class.extract(code, **opts, line_threshold: 40)
    expect(fns).not_to be_empty, 'the specimen must be big enough to split'
    expect(stranded(fns)).to eq([])
    outside = ([new_body] + fns.map(&:to_s)).find { |text| text.include?('ConstraintLayout(') }
    expect(outside).to include('val badge = createRef()').and include('top.linkTo(card.top, margin = 4.dp)')
  end

  # ⚠️ Against stubs (spec/support/compose_stub_universe.rb `common_stages`
  # plus ConstraintLayoutScope): "well-typed Kotlin", not "valid Compose" —
  # a createRef / constrainAs / linkTo lifted out of the ConstraintLayout's
  # content is an unresolved reference here, as in Gradle.
  it 'compiles the split cell' do
    new_body, fns = described_class.extract(body, **opts, line_threshold: 40)
    emitted = "@Composable\nfun Probe(data: ProbeData, viewModel: ProbeViewModel) {\n#{new_body}\n}\n\n#{fns.map(&:to_s).join("\n\n")}"
    expect(<<~KOTLIN).to compile_as_kotlin
      annotation class Composable
      #{ComposeStubUniverse.common_stages(emitted)}
      class ProbeData { val badgeVisibility: String = "visible"; val onTap: (() -> Unit)? = null }
      class ProbeViewModel
      fun Modifier.wrapContentHeight(): Modifier = this
      enum class IntrinsicSize { Min, Max }
      fun Modifier.height(intrinsicSize: IntrinsicSize): Modifier = this
      fun Modifier.width(intrinsicSize: IntrinsicSize): Modifier = this
      operator fun Dp.plus(o: Dp) = Dp(value + o.value)
      operator fun Dp.unaryMinus() = Dp(-value)
      class HorizontalAnchor
      class VerticalAnchor
      class HorizontalAnchorable { fun linkTo(anchor: HorizontalAnchor, margin: Dp = 0.dp) {} }
      class VerticalAnchorable { fun linkTo(anchor: VerticalAnchor, margin: Dp = 0.dp) {} }
      class ConstrainedLayoutReference { val top = HorizontalAnchor(); val bottom = HorizontalAnchor(); val start = VerticalAnchor(); val end = VerticalAnchor() }
      class ConstrainScope { val top = HorizontalAnchorable(); val bottom = HorizontalAnchorable(); val start = VerticalAnchorable(); val end = VerticalAnchorable(); val parent = ConstrainedLayoutReference() }
      @DslMarker annotation class LayoutScopeMarker
      @LayoutScopeMarker interface ConstraintLayoutScope {
          fun createRef(): ConstrainedLayoutReference = ConstrainedLayoutReference()
          fun Modifier.constrainAs(ref: ConstrainedLayoutReference, constrainBlock: ConstrainScope.() -> Unit): Modifier = this
      }
      fun ConstraintLayout(modifier: Modifier = Modifier, content: ConstraintLayoutScope.() -> Unit) {}
      fun VisibilityWrapper(visibility: String, modifier: Modifier = Modifier, content: BoxScope.() -> Unit) {}
      #{emitted}
    KOTLIN
  end
end
