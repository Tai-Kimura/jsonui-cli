# frozen_string_literal: true

require 'tmpdir'
require_relative 'kotlin_compiler'
require_relative 'compose_bounded_scroll_stubs'
require_relative '../../lib/compose/generators/cell_generator'

# The stub universe a Collection's emitted code is compiled and run against (Compose's timing transcribed, the
# scaffolded cell views and view models), shared by collection_cell_first_frame_spec.rb and collection_reorder_spec.rb
# (moved here from the former, unchanged).
module CollectionFirstFrame
  def scaffold(class_name, letter)
    generator = KjuiTools::Compose::Generators::CellGenerator.allocate
    view = generator.send(:main_cell_content, class_name, nil, 'com.example')
    model = generator.send(:cell_viewmodel_content, class_name, 'x_cell', 'com.example')
    params = view[/fun #{class_name}View\((.*?)\)\s*\{/m, 1] or raise "no #{class_name}View in the scaffold"
    update = model[/fun updateData\((.*?)\)/, 1] or raise 'no updateData in the scaffold'
    "class #{class_name}ViewModel : Model() { fun updateData(#{update}) { item = updates } }\n" \
      "@Composable fun #{class_name}View(#{params.strip}) { Frame.draw(\"#{letter}\" + (viewModel.item[\"id\"] ?: \"-\")) }\n"
  end

  FIRST_FRAME_STUBS = <<~KOTLIN
    annotation class Composable
    interface Modifier { companion object : Modifier }
    fun Modifier.testTag(tag: String): Modifier = this
    fun Modifier.fillMaxWidth(): Modifier = this
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
    interface Alignment {
        interface Vertical; interface Horizontal
        companion object {
            val TopStart = object : Alignment {}; val Top = object : Vertical {}
            val CenterHorizontally = object : Horizontal {}; val End = object : Horizontal {}
        }
    }
    class Arrangement { companion object { fun spacedBy(space: Dp): Arrangement = Arrangement(); fun spacedBy(space: Dp, alignment: Alignment.Horizontal): Arrangement = Arrangement() } }
    class BoxWithConstraintsScope { val constraints = Constraints() }
    fun BoxWithConstraints(modifier: Modifier = Modifier, content: BoxWithConstraintsScope.() -> Unit) { BoxWithConstraintsScope().content() }
    fun Box(modifier: Modifier = Modifier, contentAlignment: Alignment = Alignment.TopStart, content: () -> Unit) { content() }
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
        Frame.draw("/")
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
    class PagerState(val pageCount: () -> Int)
    fun rememberPagerState(pageCount: () -> Int): PagerState = PagerState(pageCount)
    fun HorizontalPager(state: PagerState, modifier: Modifier = Modifier, pageContent: (Int) -> Unit) {
        for (page in 0 until state.pageCount()) pageContent(page)
    }
    inline fun <T> key(vararg keys: Any?, block: () -> T): T = block()
    // KotlinJsonUI's CollectionReorder API, the signatures as the library declares them, drawing nothing of its own.
    class CollectionReorder(val isEnabled: Boolean, val usesHandle: Boolean = false, val onReorder: (Int, Int, Int) -> Unit)
    class CollectionReorderState
    fun rememberCollectionReorder(reorder: CollectionReorder?, scrollsItself: Boolean = true): CollectionReorderState = CollectionReorderState()
    fun Modifier.collectionReorderContainer(state: CollectionReorderState): Modifier = this
    fun CollectionReorderScope(state: CollectionReorderState, content: () -> Unit) { content() }
    fun CollectionReorderRow(state: CollectionReorderState?, section: Int, index: Int, count: Int, locked: Set<Int> = emptySet(), content: () -> Unit) { content() }
    fun Modifier.collectionReorderActions(): Modifier = this
    object com { object kotlinjsonui { object utils { object CellIdGenerator {
        fun enrichCellIds(data: List<Map<String, Any>>, property: String): List<Map<String, Any>> = data
    } } } }

    // Compose's timing, transcribed. A frame composes the body top to bottom;
    // `remember` and LaunchedEffect keep a slot per call position (the
    // routes' structure is the same from frame to frame here).
    object Frame {
        val drawn = mutableListOf<String>()
        val slots = mutableListOf<Pair<List<Any?>, Any?>>()
        var position = 0
        val effects = mutableListOf<suspend () -> Unit>()
        val models = mutableMapOf<String, Any>()
        fun draw(what: String) { drawn += what }
        fun reset() { slots.clear(); effects.clear(); models.clear() }
        // One frame: compose, print what it drew, then run the effects it
        // launched — after the frame, as Compose does.
        fun run(body: () -> Unit): String {
            drawn.clear(); position = 0
            body()
            val frame = drawn.joinToString(" ")
            val launched = effects.toList(); effects.clear()
            kotlinx.coroutines.runBlocking { launched.forEach { it() } }
            return frame
        }
        // The slot at this call position: (unchanged, its value).
        fun slot(keys: List<Any?>): Pair<Boolean, Any?> {
            val at = position++
            val held = slots.getOrNull(at)
            return if (held != null && held.first == keys) true to held.second else false to null
        }
        fun store(keys: List<Any?>, value: Any?) {
            val at = position - 1
            if (at < slots.size) slots[at] = keys to value else slots += keys to value
        }
    }
    @Suppress("UNCHECKED_CAST")
    fun <T> remembered(keys: List<Any?>, calculation: () -> T): T {
        val (unchanged, value) = Frame.slot(keys)
        if (unchanged) return value as T
        val made = calculation()
        Frame.store(keys, made)
        return made
    }
    fun <T> remember(key1: Any?, calculation: () -> T): T = remembered(listOf(key1), calculation)
    fun <T> remember(key1: Any?, key2: Any?, calculation: () -> T): T = remembered(listOf(key1, key2), calculation)
    fun LaunchedEffect(key1: Any?, block: suspend kotlinx.coroutines.CoroutineScope.() -> Unit) {
        val (unchanged, _) = Frame.slot(listOf(key1))
        if (unchanged) return
        Frame.store(listOf(key1), Unit)
        Frame.effects += { kotlinx.coroutines.coroutineScope { block() } }
    }
    // What the scaffolded ViewModel holds (its Data's `item`, here the map).
    open class Model { var item: Map<String, Any?> = emptyMap() }
    inline fun <reified T : Any> viewModel(key: String? = null): T =
        Frame.models.getOrPut(key!!) { T::class.java.getDeclaredConstructor().newInstance() } as T

    class CollectionDataSource(val sections: List<CollectionDataSection> = emptyList())
    class CollectionDataSection(val cells: CellData? = null, val header: HeaderFooterData? = null, val footer: HeaderFooterData? = null) {
        class CellData(val viewName: String, val data: List<Map<String, Any>>)
        class HeaderFooterData(val viewName: String, val data: Map<String, Any>)
    }
    class Data(val rows: CollectionDataSource? = null, val editing: Boolean = true, val onMove: ((Int, Int, Int) -> Unit)? = null)
    fun cells(name: String, n: Int, rev: String) = CollectionDataSection.CellData(name, List(n) { mapOf<String, Any>("id" to "$name$it$rev") })
    fun edge(name: String, rev: String) = CollectionDataSection.HeaderFooterData(name, mapOf<String, Any>("id" to "$name$rev"))
    fun rows(rev: String) = Data(CollectionDataSource(listOf(
        CollectionDataSection(cells("a", 2, rev), edge("h", rev), edge("f", rev)),
        CollectionDataSection(cells("b", 1, rev), edge("h", rev))
    )))
    #{ComposeBoundedScrollStubs::KOTLIN}
  KOTLIN

  def program(functions)
    calls = functions.keys.map do |fn|
      '    Frame.reset(); val screen = Any(); ' \
        "val f1 = Frame.run { #{fn}(rows(\"\"), screen) }; " \
        "val f2 = Frame.run { #{fn}(rows(\"\"), screen) }; " \
        'Frame.models.values.filterIsInstance<ACellViewModel>().forEach { it.item = mapOf("id" to "own") }; ' \
        "val f3 = Frame.run { #{fn}(rows(\"\"), screen) }; " \
        "val f4 = Frame.run { #{fn}(rows(\"'\"), screen) }; " \
        "println(\"#{fn} => \" + listOf(f1, f2, f3, f4).joinToString(\" | \"))"
    end
    [FIRST_FRAME_STUBS, scaffold('ACell', 'A'), scaffold('BCell', 'B'), scaffold('HCell', 'H'), scaffold('FCell', 'F'),
     functions.map { |fn, body| "@Composable fun #{fn}(data: Data, viewModel: Any) {\n#{body}\n}" }.join("\n\n"),
     "fun main() {\n#{calls.map { |c| "    run {\n#{c}\n    }" }.join("\n")}\n}"].join("\n")
  end

  def run(functions)
    skip "compile: #{KotlinCompiler.unavailable_reason}" if KotlinCompiler.unavailable_reason

    Dir.mktmpdir('kjui_first_frame') do |dir|
      File.write(File.join(dir, 'Emitted.kt'), program(functions))
      stdlib = KotlinCompiler.jar('org.jetbrains.kotlin', 'kotlin-stdlib')
      coroutines = KotlinCompiler.jar('org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm')
      reflect = KotlinCompiler.jar('org.jetbrains.kotlin', 'kotlin-reflect')
      annotations = KotlinCompiler.jar('org.jetbrains', 'annotations')
      compiler_cp = KotlinCompiler.compiler_classpath
      out, = KotlinCompiler.java_capture2e('-cp', compiler_cp, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
                                           '-no-stdlib', '-cp', [stdlib, reflect, annotations, coroutines].join(':'),
                                           '-d', File.join(dir, 'out'), File.join(dir, 'Emitted.kt'))
      raise "did not compile:\n#{out}" if out.include?('error:')

      ran, status = KotlinCompiler.java_capture2e('-cp', [File.join(dir, 'out'), stdlib, reflect, coroutines].join(':'), 'EmittedKt')
      raise "did not run:\n#{ran}" unless status.success?

      ran.lines.to_h { |l| l.chomp.split(' => ', 2) }
    end
  end
end
