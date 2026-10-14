# frozen_string_literal: true

require 'json'
require 'set'
require_relative '../../lib/compose/compose_builder'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# A ScrollView that is a child of a SafeAreaView laid out in a ConstraintLayout
# (a sibling uses alignTopOfView & co.) is drawn by
# ComposeBuilder#generate_scroll_with_constraints, not ScrollViewComponent.
# That path wrote LazyColumn for every ScrollView, so a horizontal one there
# scrolled vertically (kjui-scroll-with-constraints-always-vertical). It now
# takes the axis from ScrollViewComponent.horizontal? — horizontalScroll true or
# orientation horizontal, never a child (jui-scrollview-axis-from-child-web-
# disagrees) — and registers the import it uses.
RSpec.describe 'kjui: a ScrollView in a ConstraintLayout scrolls on its own axis' do
  def generate(scroll)
    node = { 'type' => 'SafeAreaView', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent', 'child' => [
      { 'type' => 'Label', 'id' => 'title', 'text' => 'Title' },
      scroll.merge('id' => 'rail', 'alignTopOfView' => 'title',
                   'child' => [{ 'type' => 'View', 'orientation' => 'horizontal', 'child' => [{ 'type' => 'Label', 'text' => 'a' }] }])
    ] }
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@required_imports, Set.new)
    builder.instance_variable_set(:@responsive_counter, 0)
    code = builder.send(:generate_component, JSON.parse(JSON.generate(node)), 1).to_s
    [code, builder.instance_variable_get(:@required_imports)]
  end

  it 'reaches the ConstraintLayout path (the specimen)' do
    code, = generate({ 'type' => 'ScrollView' })
    expect(code).to include('ConstraintLayout(')
    expect(code).to include('.constrainAs(rail)')
  end

  it 'draws orientation horizontal as a LazyRow, with its import' do
    code, imports = generate({ 'type' => 'ScrollView', 'orientation' => 'horizontal' })
    expect(code).to match(/LazyRow\(\s*\n\s*modifier = Modifier[\s\S]*?\.constrainAs\(rail\)/)
    expect(code).not_to include('LazyColumn(')
    expect(imports).to include(:lazy_row)
  end

  it 'draws horizontalScroll true as a LazyRow' do
    code, = generate({ 'type' => 'ScrollView', 'horizontalScroll' => true })
    expect(code).to include('LazyRow(')
  end

  # ⚠️ Against stubs (spec/support/compose_stub_universe.rb `common_stages`
  # plus the ConstraintLayout names and the LazyRow this path calls): "well-typed
  # Kotlin", not "valid Compose" — LazyRow and LazyColumn are distinct stubs,
  # so the emit has to name the one its import set brought in.
  it 'compiles both axes' do
    emitted = [{ 'type' => 'ScrollView', 'orientation' => 'horizontal' }, { 'type' => 'ScrollView' }]
              .each_with_index.map { |scroll, i| "@Composable\nfun emitted#{i}() {\n#{generate(scroll).first}\n}" }.join("\n\n")
    expect(emitted).to include('LazyRow(').and include('LazyColumn(')
    expect(<<~KOTLIN).to compile_as_kotlin
      annotation class Composable
      #{ComposeStubUniverse.common_stages(emitted)}
      fun Modifier.fillMaxHeight(): Modifier = this
      class HorizontalAnchor { fun linkTo(anchor: HorizontalAnchor) {} }
      class VerticalAnchor { fun linkTo(anchor: VerticalAnchor) {} }
      class ConstrainedLayoutReference { val top = HorizontalAnchor(); val bottom = HorizontalAnchor(); val start = VerticalAnchor(); val end = VerticalAnchor() }
      class ConstrainScope { val top = HorizontalAnchor(); val bottom = HorizontalAnchor(); val start = VerticalAnchor(); val end = VerticalAnchor() }
      interface ConstraintLayoutScope {
          fun createRef(): ConstrainedLayoutReference = ConstrainedLayoutReference()
          fun Modifier.constrainAs(ref: ConstrainedLayoutReference, constrainBlock: ConstrainScope.() -> Unit): Modifier = this
      }
      fun ConstraintLayout(modifier: Modifier = Modifier, content: ConstraintLayoutScope.() -> Unit) {}
      fun LazyRow(modifier: Modifier = Modifier, content: LazyListScope.() -> Unit) {}
      #{emitted}
    KOTLIN
  end

  it 'keeps a ScrollView with no axis key vertical, whatever its child' do
    code, imports = generate({ 'type' => 'ScrollView' })
    expect(code).to include('LazyColumn(')
    expect(code).not_to include('LazyRow(')
    expect(imports).to include(:lazy_column)
  end
end
