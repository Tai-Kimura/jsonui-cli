# frozen_string_literal: true

require 'json'
require 'set'
require 'compose/compose_builder'
require_relative '../support/kotlin_compiler'

# kjui-label-with-visibility-and-parent-alignment-does-not-compile: a Label
# was wrapped in VisibilityWrapper twice — by its own component and by the
# exit that draws it. Its own wrapper took the alignment (written on one line,
# `modifier = Modifier.align(Alignment.Start)`) and sat inside the outer one,
# whose content is a BoxScope, so a Column child's alignment did not compile
# ("actual type is 'Alignment.Horizontal', but 'Alignment' was expected" —
# measured on a sample app at jsonui-cli v1.9.7, responsive and plain alike).
# An Image had one wrapper and compiled. A Label is now wrapped once, by the
# exit, as an Image is.
RSpec.describe 'kjui codegen: a Label with a visibility and an alignment in its parent' do
  before { allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({}) }

  def emit(node)
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@required_imports, Set.new)
    builder.instance_variable_set(:@responsive_counter, 0)
    builder.instance_variable_set(:@responsive_functions, [])
    builder.send(:generate_component, JSON.parse(JSON.generate(node)), 0).to_s
  end

  # Compose's scopes as Compose types them, each @LayoutScopeMarker (a
  # DslMarker: an outer scope's members are not reachable implicitly inside a
  # nested one), VisibilityWrapper's content a BoxScope, and what a Label
  # emits.
  def kotlin(code)
    <<~KT
      open class Modifier { companion object : Modifier() }
      class Dp(val value: Float)
      val Int.dp: Dp get() = Dp(toFloat())
      fun Modifier.testTag(tag: String): Modifier = this
      class SemanticsScope { var testTagsAsResourceId: Boolean = false }
      fun Modifier.semantics(block: SemanticsScope.() -> Unit): Modifier = this
      interface Alignment {
          interface Vertical
          interface Horizontal
          companion object {
              val Top: Vertical = object : Vertical {}
              val Bottom: Vertical = object : Vertical {}
              val CenterVertically: Vertical = object : Vertical {}
              val Start: Horizontal = object : Horizontal {}
              val End: Horizontal = object : Horizontal {}
              val CenterHorizontally: Horizontal = object : Horizontal {}
              val TopStart: Alignment = object : Alignment {}
          }
      }
      @DslMarker annotation class LayoutScopeMarker
      @LayoutScopeMarker interface RowScope {
          fun Modifier.weight(weight: Float, fill: Boolean = true): Modifier = this
          fun Modifier.align(alignment: Alignment.Vertical): Modifier = this
      }
      @LayoutScopeMarker interface ColumnScope {
          fun Modifier.weight(weight: Float, fill: Boolean = true): Modifier = this
          fun Modifier.align(alignment: Alignment.Horizontal): Modifier = this
      }
      @LayoutScopeMarker interface BoxScope { fun Modifier.align(alignment: Alignment): Modifier = this }
      fun Row(modifier: Modifier = Modifier, content: RowScope.() -> Unit) { object : RowScope {}.content() }
      fun Column(modifier: Modifier = Modifier, content: ColumnScope.() -> Unit) { object : ColumnScope {}.content() }
      fun VisibilityWrapper(visibility: String? = null, hidden: Boolean = false, modifier: Modifier = Modifier,
                            content: BoxScope.() -> Unit) { object : BoxScope {}.content() }
      class IntSize(val width: Int)
      class WindowInfo(val containerSize: IntSize)
      object LocalWindowInfo { val current = WindowInfo(IntSize(0)) }
      class Density { fun Int.toDp(): Dp = Dp(toFloat()) }
      object LocalDensity { val current = Density() }
      class TextUnit { companion object { val Unspecified = TextUnit() } }
      class FontFamily
      class FontWeight
      class FontStyle { companion object { val Normal = FontStyle() } }
      class FontSpec(val family: String?, val weight: String?, val size: Int?, val italic: Boolean)
      class ResolvedFont(val family: FontFamily?, val weight: FontWeight?, val size: TextUnit?, val style: FontStyle?)
      object Configuration { object Font { fun resolve(spec: FontSpec): ResolvedFont = ResolvedFont(null, null, null, null) } }
      fun Text(text: String, fontFamily: FontFamily? = null, fontWeight: FontWeight? = null, fontSize: TextUnit = TextUnit(),
               fontStyle: FontStyle? = null, modifier: Modifier = Modifier) {}
      class Data(val v: String? = null)
      fun emitted(data: Data) {
      #{code}
      }
    KT
  end

  responsive = { 'regular' => { 'alignLeft' => true }, 'compact' => { 'alignLeft' => true } }
  shapes = {
    'a Column child, alignLeft, bound visibility' =>
      { 'type' => 'View', 'orientation' => 'vertical', 'child' => [{ 'type' => 'Label', 'id' => 'p', 'text' => 'b', 'visibility' => '@{v}', 'alignLeft' => true }] },
    'a Column child, a responsive alignLeft, bound visibility' =>
      { 'type' => 'View', 'orientation' => 'vertical', 'child' => [{ 'type' => 'Label', 'id' => 'r', 'text' => 'a', 'visibility' => '@{v}', 'responsive' => responsive }] },
    'a Row child, alignTop, bound visibility' =>
      { 'type' => 'View', 'orientation' => 'horizontal', 'child' => [{ 'type' => 'Label', 'id' => 't', 'text' => 'c', 'visibility' => '@{v}', 'alignTop' => true }] }
  }

  shapes.each do |shape, node|
    it "is wrapped once, the wrapper carrying the alignment: #{shape}" do
      code = emit(node)
      branches = node['child'][0]['responsive'] ? 3 : 1
      expect(code.scan('VisibilityWrapper(').size).to eq(branches), code
      expect(code.scan(/VisibilityWrapper\(\n[^)]*modifier = Modifier\.align\(/).size).to eq(node['child'][0]['responsive'] ? 2 : 1), code
    end

    it "emits Kotlin that compiles: #{shape}" do
      code = emit(node)
      expect(code).to include('.align(Alignment.') # the alignment is in the code compiled (control)
      expect(kotlin(code)).to compile_as_kotlin
    end
  end
end
