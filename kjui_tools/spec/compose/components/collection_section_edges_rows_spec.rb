# frozen_string_literal: true

require 'open3'
require 'set'
require 'tmpdir'
require_relative '../../../lib/compose/components/collection_component'
require_relative '../../../lib/compose/generators/cell_generator'
require_relative '../../support/kotlin_compiler'

# A Collection's header or footer view sits in a row of its own: the ROW is
# full width and the view keeps its own size at the row's start (4f ruling
# 2026-09-26, round 8) — as KotlinJsonUI Dynamic draws it (the view in its
# row, no fill of its own) and sjui (`.frame(maxWidth: .infinity, alignment:
# .leading)`). Until jsonui-cli 1.9.0 the list, grid, non-lazy and class-list
# routes handed the view itself `Modifier.fillMaxWidth()`, and a fixed-width
# root (`requiredWidth`) answers a fill constraint by centring itself in the
# row. Measured on the Android codegen conformance host (my emulator, conf_ci
# read-only), the 60dp header of Collection/sections__headerFooter: at 45-105dp
# of its 150dp row before, at 0-60dp after — where KotlinJsonUI Dynamic draws
# it; the fixture and four probes of the other routes (grid, lazy none,
# wrapContent, the class-list shape) pixel-identical to Dynamic after, and
# different from it before on exactly those five.
#
# The arm RUNS the emitted code: compiled by kotlinc and run on the JVM
# against stubs in which `fillMaxWidth()` marks a modifier, a Box records
# whether it is a full-width row, and each header / footer view prints its
# letter with `~` when it was handed the fill itself and `!` when it is not
# in a full-width row. The marks are what Compose would do with the chain,
# transcribed: a green says the emitted code puts each view in a full-width
# row without a fill of its own, not how Compose measures it.
RSpec.describe 'kjui codegen: a header or footer is a full-width row, the view at its own size' do
  EDGE_ROWS_SECTIONS = [{ 'cell' => 'ACell', 'header' => 'HCell', 'footer' => 'FCell' }, { 'cell' => 'BCell', 'header' => 'HCell' }].freeze

  def emit(extra)
    %i[info debug warn].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    node = { 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'sections' => EDGE_ROWS_SECTIONS }.merge(extra).compact
    KjuiTools::Compose::Components::CollectionComponent.generate(node, 1, Set.new, nil)
  end

  EDGE_ROWS_ROUTES = {
    'list' => {},
    'lazyNone' => { 'lazy' => 'none' },
    'wrapContent' => { 'height' => 'wrapContent' },
    'grid' => { 'columns' => 2 },
    'gridLazyNone' => { 'columns' => 2, 'lazy' => 'none' },
    'tracked' => { 'cellIdProperty' => 'id', 'autoChangeTrackingId' => true },
    'flow' => { 'layout' => 'flow' },
    'classList' => { 'sections' => nil, 'cellClasses' => ['ACell'], 'headerClasses' => ['HCell'], 'footerClasses' => ['FCell'] }
  }.freeze

  def scaffold(class_name, letter, edge: false)
    generator = KjuiTools::Compose::Generators::CellGenerator.allocate
    view = generator.send(:main_cell_content, class_name, nil, 'com.example')
    model = generator.send(:cell_viewmodel_content, class_name, 'x_cell', 'com.example')
    params = view[/fun #{class_name}View\((.*?)\)\s*\{/m, 1] or raise "no #{class_name}View in the scaffold"
    update = model[/fun updateData\((.*?)\)/, 1] or raise 'no updateData in the scaffold'
    mark = edge ? '"' + letter + '" + (if (modifier is Wide) "~" else "") + (if (Layout.fullRow) "" else "!")' : "\"#{letter}\""
    "class #{class_name}ViewModel { fun updateData(#{update}) {} }\n" \
      "@Composable fun #{class_name}View(#{params.strip}) { Layout.draw(#{mark}) }\n"
  end

  EDGE_ROWS_STUBS = <<~KOTLIN
    annotation class Composable
    interface Modifier { companion object : Modifier }
    class Tagged(val tag: String) : Modifier
    class Wide(val inner: Modifier) : Modifier
    fun Modifier.testTag(tag: String): Modifier = Tagged(tag)
    fun Modifier.fillMaxWidth(): Modifier = Wide(this)
    fun Modifier.fillMaxSize(): Modifier = this
    fun Modifier.wrapContentHeight(): Modifier = this
    fun Modifier.height(value: Dp): Modifier = this
    fun Modifier.requiredHeight(value: Dp): Modifier = this
    fun Modifier.fillMaxHeight(): Modifier = this
    fun Modifier.wrapContentHeight(align: Alignment.Vertical, unbounded: Boolean = false): Modifier = this
    class ScrollState
    fun rememberScrollState(): ScrollState = ScrollState()
    fun Modifier.verticalScroll(state: ScrollState): Modifier = this
    class SemanticsPropertyReceiver { var testTagsAsResourceId: Boolean = false }
    fun Modifier.semantics(properties: SemanticsPropertyReceiver.() -> Unit): Modifier = this
    class Dp
    val Int.dp: Dp get() = Dp()
    interface Alignment { interface Vertical; companion object { val TopStart = object : Alignment {}; val Top = object : Vertical {} } }
    class Arrangement { companion object { fun spacedBy(space: Dp): Arrangement = Arrangement() } }
    class Constraints(val hasBoundedHeight: Boolean)
    class BoxWithConstraintsScope { val constraints = Constraints(true) }
    fun BoxWithConstraints(modifier: Modifier = Modifier, content: BoxWithConstraintsScope.() -> Unit) { BoxWithConstraintsScope().content() }
    object Layout {
        val drawn = mutableListOf<String>()
        var fullRow = false
        fun draw(what: String) { drawn += what }
    }
    // A Box is a full-width row when its modifier is filled; its content is
    // placed at its start.
    fun Box(modifier: Modifier = Modifier, contentAlignment: Alignment = Alignment.TopStart, content: () -> Unit) {
        val outer = Layout.fullRow
        Layout.fullRow = modifier is Wide
        content()
        Layout.fullRow = outer
    }
    class ColumnScope
    fun Column(modifier: Modifier = Modifier, verticalArrangement: Arrangement? = null, content: ColumnScope.() -> Unit) { ColumnScope().content() }
    fun FlowRow(modifier: Modifier = Modifier, horizontalArrangement: Arrangement, verticalArrangement: Arrangement, content: () -> Unit) { content() }
    class LazyListScope {
        fun item(key: Any? = null, content: () -> Unit) { content() }
        fun items(count: Int, key: ((Int) -> Any)? = null, itemContent: (Int) -> Unit) { repeat(count) { itemContent(it) } }
    }
    enum class CollectionStackMode { LAZY, EAGER, NONE }
    enum class CollectionStackAxis { VERTICAL, HORIZONTAL }
    // Both bodies run, the lazy one first: an emit carries both and the mode
    // picks one at run time.
    fun CollectionStack(mode: CollectionStackMode, axis: CollectionStackAxis, modifier: Modifier = Modifier,
                        lazyContent: LazyListScope.() -> Unit, eagerContent: () -> Unit) {
        LazyListScope().lazyContent()
        Layout.draw("/")
        eagerContent()
    }
    object GridCells { class Fixed(val count: Int) }
    class GridItemSpan(val span: Int)
    class LazyGridItemSpanScope(val maxLineSpan: Int, val maxCurrentLineSpan: Int)
    class LazyGridScope {
        fun item(span: (LazyGridItemSpanScope.() -> GridItemSpan)? = null, content: () -> Unit) { content() }
        fun items(count: Int, key: ((Int) -> Any)? = null, span: (LazyGridItemSpanScope.(Int) -> GridItemSpan)? = null, itemContent: (Int) -> Unit) {
            repeat(count) { itemContent(it) }
        }
    }
    fun LazyVerticalGrid(columns: GridCells.Fixed, modifier: Modifier = Modifier, content: LazyGridScope.() -> Unit) { LazyGridScope().content() }
    class RowScope { fun Modifier.weight(weight: Float): Modifier = this }
    fun Row(modifier: Modifier = Modifier, horizontalArrangement: Arrangement? = null, content: RowScope.() -> Unit) { RowScope().content() }
    fun Spacer(modifier: Modifier) {}
    fun LaunchedEffect(key1: Any?, block: suspend kotlinx.coroutines.CoroutineScope.() -> Unit) {}
    inline fun <T> key(vararg keys: Any?, block: () -> T): T = block()
    inline fun <T> remember(key1: Any?, calculation: () -> T): T = calculation()
    object com { object kotlinjsonui { object utils { object CellIdGenerator {
        fun enrichCellIds(data: List<Map<String, Any>>, property: String): List<Map<String, Any>> = data
    } } } }
    inline fun <reified T : Any> viewModel(key: String? = null): T = T::class.java.getDeclaredConstructor().newInstance()
    class CollectionDataSource(val sections: List<CollectionDataSection> = emptyList())
    class CollectionDataSection(val cells: CellData? = null, val header: HeaderFooterData? = null, val footer: HeaderFooterData? = null) {
        class CellData(val viewName: String, val data: List<Map<String, Any>>)
        class HeaderFooterData(val viewName: String, val data: Map<String, Any>)
    }
    class Data(val rows: CollectionDataSource? = null)
    fun cells(name: String, n: Int) = CollectionDataSection.CellData(name, List(n) { mapOf<String, Any>("id" to "$name$it") })
    fun edge(name: String) = CollectionDataSection.HeaderFooterData(name, emptyMap())
  KOTLIN

  def program(functions)
    data = 'Data(CollectionDataSource(listOf(CollectionDataSection(cells("A", 2), edge("H"), edge("F")), ' \
           'CollectionDataSection(cells("B", 1), edge("H")))))'
    calls = functions.keys.map do |fn|
      "    Layout.drawn.clear(); #{fn}(#{data}, Any()); println(\"#{fn} => \" + Layout.drawn.joinToString(\" \"))"
    end
    [EDGE_ROWS_STUBS, scaffold('ACell', 'A'), scaffold('BCell', 'B'), scaffold('HCell', 'H', edge: true), scaffold('FCell', 'F', edge: true),
     functions.map { |fn, body| "@Composable fun #{fn}(data: Data, viewModel: Any) {\n#{body}\n}" }.join("\n\n"),
     "fun main() {\n#{calls.join("\n")}\n}"].join("\n")
  end

  def run(functions)
    skip "compile: #{KotlinCompiler.unavailable_reason}" if KotlinCompiler.unavailable_reason

    Dir.mktmpdir('kjui_edges') do |dir|
      File.write(File.join(dir, 'Emitted.kt'), program(functions))
      stdlib = KotlinCompiler.newest('org.jetbrains.kotlin', 'kotlin-stdlib')
      coroutines = KotlinCompiler.newest('org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm')
      reflect = KotlinCompiler.newest('org.jetbrains.kotlin', 'kotlin-reflect')
      annotations = KotlinCompiler.newest('org.jetbrains', 'annotations')
      compiler_cp = [KotlinCompiler.compiler_jar, stdlib, reflect, coroutines, annotations,
                     KotlinCompiler.newest('org.jetbrains.intellij.deps', 'trove4j')].compact.join(':')
      out, = Open3.capture2e(KotlinCompiler.java_bin, '-cp', compiler_cp, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
                             '-no-stdlib', '-cp', [stdlib, reflect, annotations, coroutines].join(':'),
                             '-d', File.join(dir, 'out'), File.join(dir, 'Emitted.kt'))
      raise "did not compile:\n#{out}" if out.include?('error:')

      ran, status = Open3.capture2e(KotlinCompiler.java_bin, '-cp', [File.join(dir, 'out'), stdlib, coroutines].join(':'), 'EmittedKt')
      raise "did not run:\n#{ran}" unless status.success?

      ran.lines.to_h { |l| l.chomp.split(' => ', 2) }
    end
  end

  it 'on every route that draws a header or footer: each in a full-width row, the view not filled' do
    drawn = run(EDGE_ROWS_ROUTES.transform_values { |extra| emit(extra) })
    # The lazy body, then (after `/`) the eager one.
    %w[list tracked].each { |route| expect(drawn[route]).to eq('H A A F H B / H A A F H B'), drawn.inspect }
    %w[lazyNone wrapContent grid gridLazyNone flow].each { |route| expect(drawn[route]).to eq('H A A F H B'), drawn.inspect }
    # The class-list shape: its header and footer once, around every data
    # section's cells, each drawn with cellClasses[0].
    expect(drawn['classList']).to eq('H A A A F'), drawn.inspect
  end

  it "control: a cell is not a row — it is drawn where the route places it, and the marks are the edges' alone" do
    drawn = run('list' => emit({}))
    expect(drawn['list'].split.grep(/\A[AB]/).uniq).to eq(%w[A B])
  end
end
