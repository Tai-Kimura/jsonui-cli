# frozen_string_literal: true

require 'open3'
require 'set'
require 'tmpdir'
require_relative '../../../lib/compose/components/collection_component'
require_relative '../../../lib/compose/generators/cell_generator'
require_relative '../../support/kotlin_compiler'

# What a Collection's `scrollTo` names across sections (4f ruling 2026-09-27;
# the SSoT's Collection.scrollTo description, jsonui-cli 1.9.0): an Int is the
# index of a CELL counted across the drawn sections in order — a section's
# header or footer item, and a grid's filler item, is not counted; a String
# (cellIdProperty) is the FIRST cell, in section order, whose key (its
# cellId, else its cellIdProperty value) it is — and a key two sections share
# is two items' key no more (a later section's is "<section>:<key>"). On the Kotlin paths a String
# no cell has as its key is read, as before, as the lazy item index
# ("0#<time>" — a consuming screen's bottom-most item under reverseLayout).
#
# Until jsonui-cli 1.9.0 the value was the lazy item index itself — every
# header, footer and filler item counted — and a String was read as that
# index, so a key scrolled nowhere.
#
# The arm RUNS the emitted code: compiled with kotlinc and run on the JVM
# against stubs whose lazy scopes record the items the builder emits, in
# order, each as what its content draws (a cell its letter and the index its
# test tag carries, a header H, a footer F, an empty item `_`), and whose
# LaunchedEffect runs the effect after the content is built, as Compose does.
# The answer is the item the scroll asked for. The stubs are a transcription
# of the builder's API, not Compose: a green says the emitted effect asks for
# the item that holds the cell.
RSpec.describe 'kjui codegen: scrollTo names a cell' do
  def emit(node)
    %i[info debug warn].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    KjuiTools::Compose::Components::CollectionComponent.generate(JSON.parse(JSON.generate(node)), 1, Set.new, nil)
  end

  def scaffold(class_name, letter)
    generator = KjuiTools::Compose::Generators::CellGenerator.allocate
    view = generator.send(:main_cell_content, class_name, nil, 'com.example')
    model = generator.send(:cell_viewmodel_content, class_name, 'x_cell', 'com.example')
    params = view[/fun #{class_name}View\((.*?)\)\s*\{/m, 1] or raise "no #{class_name}View in the scaffold"
    update = model[/fun updateData\((.*?)\)/, 1] or raise "no updateData in the scaffold"
    "class #{class_name}ViewModel { fun updateData(#{update}) {} }\n" \
      "@Composable fun #{class_name}View(#{params.strip}) { Drawn.draw(\"#{letter}\" + ((modifier as? Tagged)?.tag?.substringAfterLast('_') ?: \"\")) }\n"
  end

  KJ_SCROLL_STUBS = <<~KOTLIN
    package stubs

    annotation class Composable
    interface Modifier { companion object : Modifier }
    class Tagged(val tag: String) : Modifier
    fun Modifier.testTag(tag: String): Modifier = Tagged(tag)
    fun Modifier.fillMaxWidth(): Modifier = this
    fun Modifier.fillMaxSize(): Modifier = this
    class SemanticsPropertyReceiver { var testTagsAsResourceId: Boolean = false }
    fun Modifier.semantics(properties: SemanticsPropertyReceiver.() -> Unit): Modifier = this
    class Dp
    val Int.dp: Dp get() = Dp()
    interface Alignment { companion object { val TopStart = object : Alignment {}; val Top = object : Alignment {} } }
    class Arrangement { companion object { fun spacedBy(space: Dp): Arrangement = Arrangement() } }
    object GridCells { class Fixed(val count: Int) }
    class GridItemSpan(val span: Int)
    class LazyGridItemSpanScope(val maxLineSpan: Int, val maxCurrentLineSpan: Int)

    // What an item's content draws, the items in the order they were emitted
    // (each 28 high — a header or footer 10), the scroll asked for, and what
    // was logged.
    object Drawn {
        var mark = StringBuilder()
        fun draw(s: String) { mark.append(s) }
        val items = mutableListOf<String>()
        fun sizeOf(item: String) = if (item == "H" || item == "F") 10 else 28
        var scrolledTo = -1
        var offset = 0
        val logs = mutableListOf<String>()
        val effects = mutableListOf<suspend () -> Unit>()
        fun record(content: () -> Unit) { mark = StringBuilder(); content(); items += mark.toString().ifEmpty { "_" } }
        // A lazy list's item keys, and one two items shared (Compose throws
        // "Key … was already used" when both are composed).
        val keys = mutableSetOf<Any>()
        var duplicate: Any? = null
        fun key(key: ((Int) -> Any)?, count: Int) { key?.let { k -> repeat(count) { i -> k(i).let { if (!keys.add(it)) duplicate = it } } } }
    }
    // A composition's positional slots: what remember keeps and the keys a
    // LaunchedEffect restarts on, across recompositions, as Compose keeps them.
    object Composition {
        val slots = mutableListOf<Any?>()
        var cursor = 0
        @Suppress("UNCHECKED_CAST")
        fun <T> slot(init: () -> T): T {
            if (cursor < slots.size) return slots[cursor++] as T
            val value = init(); slots += value; cursor++; return value
        }
    }
    class Keyed(var key: Any?, var value: Any?)
    class MutableState<T>(var value: T)
    fun <T> mutableStateOf(value: T) = MutableState(value)
    fun <T> remember(calculation: () -> T): T = Composition.slot(calculation)
    @Suppress("UNCHECKED_CAST")
    fun <T> remember(key1: Any?, calculation: () -> T): T {
        val slot = Composition.slot { Keyed(Any(), null) }
        if (slot.key != key1) { slot.key = key1; slot.value = calculation() }
        return slot.value as T
    }
    fun LaunchedEffect(key1: Any?, block: suspend kotlinx.coroutines.CoroutineScope.() -> Unit) {
        val slot = Composition.slot { Keyed(Any(), null) }
        if (slot.key != key1) { slot.key = key1; Drawn.effects += { kotlinx.coroutines.coroutineScope { block() } } }
    }
    class ListItemInfo(val index: Int, val size: Int)
    class ListLayoutInfo(val viewportStartOffset: Int, val viewportEndOffset: Int, val visibleItemsInfo: List<ListItemInfo>)
    class LazyListState {
        val layoutInfo get() = ListLayoutInfo(0, 100, Drawn.items.mapIndexed { i, item -> ListItemInfo(i, Drawn.sizeOf(item)) })
        suspend fun scrollToItem(index: Int, scrollOffset: Int = 0) { Drawn.scrolledTo = index; Drawn.offset = scrollOffset }
        suspend fun animateScrollToItem(index: Int, scrollOffset: Int = 0) { Drawn.scrolledTo = index; Drawn.offset = scrollOffset }
    }
    class IntSize(val width: Int, val height: Int)
    class GridItemInfo(val index: Int, val size: IntSize)
    class GridLayoutInfo(val viewportStartOffset: Int, val viewportEndOffset: Int, val visibleItemsInfo: List<GridItemInfo>)
    class LazyGridState {
        val layoutInfo get() = GridLayoutInfo(0, 100, Drawn.items.mapIndexed { i, item -> GridItemInfo(i, IntSize(60, Drawn.sizeOf(item))) })
        suspend fun scrollToItem(index: Int, scrollOffset: Int = 0) { Drawn.scrolledTo = index; Drawn.offset = scrollOffset }
        suspend fun animateScrollToItem(index: Int, scrollOffset: Int = 0) { Drawn.scrolledTo = index; Drawn.offset = scrollOffset }
    }
    fun rememberLazyGridState() = remember { LazyGridState() }
    class LazyGridScope {
        fun item(span: (LazyGridItemSpanScope.() -> GridItemSpan)? = null, content: () -> Unit) = Drawn.record(content)
        fun items(count: Int, key: ((Int) -> Any)? = null, span: (LazyGridItemSpanScope.(Int) -> GridItemSpan)? = null, itemContent: (Int) -> Unit) {
            Drawn.key(key, count)
            repeat(count) { i -> Drawn.record { itemContent(i) } }
        }
    }
    class LazyListScope {
        fun item(content: () -> Unit) = Drawn.record(content)
        fun items(count: Int, key: ((Int) -> Any)? = null, itemContent: (Int) -> Unit) {
            Drawn.key(key, count)
            repeat(count) { i -> Drawn.record { itemContent(i) } }
        }
    }
    fun LazyVerticalGrid(columns: GridCells.Fixed, reverseLayout: Boolean = false, verticalArrangement: Arrangement? = null,
                         horizontalArrangement: Arrangement? = null, modifier: Modifier = Modifier, state: LazyGridState? = null,
                         content: LazyGridScope.() -> Unit) { LazyGridScope().content() }
    enum class CollectionStackMode { LAZY, EAGER, NONE;
        companion object { fun fromJson(value: Any?) = when (value) { "eager" -> EAGER; "none" -> NONE; else -> LAZY } } }
    enum class CollectionStackAxis { VERTICAL, HORIZONTAL }
    // The lazy content under LAZY; the eager content (the cells composed in
    // order, each recording its place) under EAGER and NONE.
    fun CollectionStack(mode: CollectionStackMode, axis: CollectionStackAxis, modifier: Modifier = Modifier, spacing: Dp? = null,
                        reverseLayout: Boolean = false, lazyState: LazyListState? = null, eagerScrollState: ScrollState? = null,
                        lazyContent: LazyListScope.() -> Unit, eagerContent: () -> Unit) {
        if (mode == CollectionStackMode.LAZY) LazyListScope().lazyContent() else eagerContent()
    }
    fun Box(modifier: Modifier = Modifier, contentAlignment: Alignment = Alignment.TopStart, content: () -> Unit) { content() }
    inline fun <reified T : Any> viewModel(key: String? = null): T = T::class.java.getDeclaredConstructor().newInstance()
    class CollectionDataSource(val sections: List<CollectionDataSection> = emptyList())
    class CollectionDataSection(
        val header: HeaderFooterData? = null,
        val footer: HeaderFooterData? = null,
        val cells: CellData? = null
    ) {
        class CellData(val viewName: String, val data: List<Map<String, Any>>)
        class HeaderFooterData(val viewName: String, val data: Map<String, Any>)
    }
    class Data(val rows: CollectionDataSource? = null, val target: Any? = null, val cols: Int = 2, val mode: String = "lazy")

    // The pager composes each page in turn; the page it was asked for is the scroll.
    class PagerState(val pageCount: () -> Int) {
        val currentPage = 0
        suspend fun animateScrollToPage(page: Int) { Drawn.scrolledTo = page }
        suspend fun scrollToPage(page: Int) { Drawn.scrolledTo = page }
    }
    fun rememberPagerState(pageCount: () -> Int) = remember { PagerState(pageCount) }
    fun HorizontalPager(state: PagerState, modifier: Modifier = Modifier, pageContent: (Int) -> Unit) {
        repeat(state.pageCount()) { page -> Drawn.record { pageContent(page) } }
    }

    // The flow: a column of FlowRows. Each laid-out node is 28 below the one
    // positioned before it, in composition order — the scrolled content
    // first, then the cells — which is enough to say WHICH cell's place a
    // scroll read; where Compose lays them out is the device arm's. The same
    // for the non-lazy containers (the EAGER CollectionStack, the
    // wrapContent Column): their viewport, then their cells; along x too, for
    // a row (28 wide, 28 to the right of the one before).
    class FlowCoordinates(val y: Int) : androidx.compose.ui.layout.LayoutCoordinates {
        override val isAttached = true
        override val size = IntSize(28, 28)
        override fun localPositionOf(sourceCoordinates: androidx.compose.ui.layout.LayoutCoordinates, relativeToSource: androidx.compose.ui.geometry.Offset) =
            ((sourceCoordinates as FlowCoordinates).y - y).toFloat().let { androidx.compose.ui.geometry.Offset(it, it) }
    }
    object Positions { var next = 0 }
    fun Modifier.onGloballyPositioned(onGloballyPositioned: (androidx.compose.ui.layout.LayoutCoordinates) -> Unit): Modifier {
        onGloballyPositioned(FlowCoordinates(Positions.next)); Positions.next += 28; return this
    }
    class ScrollState { val viewportSize = 100; val value = 0
        suspend fun animateScrollTo(value: Int) { Drawn.scrolledTo = value }
        suspend fun scrollTo(value: Int) { Drawn.scrolledTo = value } }
    fun Modifier.wrapContentHeight(): Modifier = this
    fun Modifier.fillMaxHeight(): Modifier = this
    // The wrapContent Column's bounding layout step: compiled, not run (the
    // device arm measures what it does).
    class Placeable(val width: Int, val height: Int) { fun place(x: Int, y: Int) {} }
    interface Measurable { fun measure(constraints: androidx.compose.ui.unit.Constraints): Placeable }
    class MeasureResult
    class MeasureScope { fun layout(width: Int, height: Int, placementBlock: () -> Unit): MeasureResult = MeasureResult() }
    fun Modifier.layout(measure: MeasureScope.(Measurable, androidx.compose.ui.unit.Constraints) -> MeasureResult): Modifier = this
    fun rememberScrollState() = remember { ScrollState() }
    fun Modifier.verticalScroll(state: ScrollState): Modifier = this
    fun Modifier.requiredHeight(height: Dp): Modifier = this
    fun Modifier.wrapContentHeight(align: Alignment, unbounded: Boolean = false): Modifier = this
    fun Column(modifier: Modifier = Modifier, verticalArrangement: Arrangement? = null, content: () -> Unit) { content() }
    fun FlowRow(modifier: Modifier = Modifier, horizontalArrangement: Arrangement? = null, verticalArrangement: Arrangement? = null, content: () -> Unit) { content() }
    fun key(vararg keys: Any?, block: () -> Unit) { block() }
  KOTLIN

  # The stubs a fully-qualified name reaches.
  KJ_SCROLL_QUALIFIED = {
    'Lazy.kt' => "package androidx.compose.foundation.lazy\nfun rememberLazyListState() = stubs.remember { stubs.LazyListState() }\n",
    # An enrichment that says it ran: "<key>_e".
    'CellIdGenerator.kt' => "package com.kotlinjsonui.utils\nobject CellIdGenerator {\n" \
                            "    fun enrichCellIds(data: List<Map<String, Any>>, primaryKey: String): List<Map<String, Any>> =\n" \
                            "        data.map { it + (\"cellId\" to \"${it[primaryKey]}_e\") }\n}\n",
    # A debuggable app, and what it logs.
    'Platform.kt' => "package androidx.compose.ui.platform\nobject LocalContext { val current = android.content.Context() }\n",
    'Context.kt' => "package android.content\nclass Context { val applicationInfo = android.content.pm.ApplicationInfo() }\n",
    'ApplicationInfo.kt' => "package android.content.pm\nclass ApplicationInfo { var flags = FLAG_DEBUGGABLE\n    companion object { const val FLAG_DEBUGGABLE = 2 } }\n",
    'Log.kt' => "package android.util\nobject Log { fun w(tag: String, msg: String): Int { stubs.Drawn.logs += msg; return 0 } }\n",
    'Layout.kt' => "package androidx.compose.ui.layout\ninterface LayoutCoordinates { val isAttached: Boolean; val size: stubs.IntSize\n" \
                   "    fun localPositionOf(sourceCoordinates: LayoutCoordinates, relativeToSource: androidx.compose.ui.geometry.Offset): androidx.compose.ui.geometry.Offset }\n",
    'Geometry.kt' => "package androidx.compose.ui.geometry\nclass Offset(val x: Float, val y: Float) { companion object { val Zero = Offset(0f, 0f) } }\n",
    # The non-lazy containers' scroll (round 12): a frame passes at once.
    'Foundation.kt' => "package androidx.compose.foundation\nfun rememberScrollState() = stubs.remember { stubs.ScrollState() }\n",
    'Runtime.kt' => "package androidx.compose.runtime\nsuspend fun <R> withFrameNanos(onFrame: (Long) -> R): R = onFrame(0L)\n",
    'Unit.kt' => "package androidx.compose.ui.unit\nenum class LayoutDirection { Ltr, Rtl }\n" \
                 "class Constraints(val minWidth: Int, val maxWidth: Int, val minHeight: Int, val maxHeight: Int) {\n" \
                 "    val hasBoundedHeight get() = maxHeight != Int.MAX_VALUE\n" \
                 "    companion object { fun fitPrioritizingWidth(minWidth: Int, maxWidth: Int, minHeight: Int, maxHeight: Int) = Constraints(minWidth, maxWidth, minHeight, maxHeight) } }\n",
    'Direction.kt' => "package androidx.compose.ui.platform\nobject LocalLayoutDirection { val current = androidx.compose.ui.unit.LayoutDirection.Ltr }\n"
  }.freeze

  # Section A: header, cells A0…A4 (keys k0…k4), footer; section B: header,
  # cells B0…B4 (keys k3 — shared with A — x1…x4). `grid: true` drops A's
  # footer and B's header, so a filler item ends A's part-filled row.
  def data_sections(grid: false, dup: false)
    a = if dup
          'cells = CollectionDataSection.CellData("A", listOf("k0", "k1", "k1", "k3", "k4").map { mapOf<String, Any>("key" to it) })'
        else
          'cells = CollectionDataSection.CellData("A", List(5) { mapOf<String, Any>("key" to "k$it") })'
        end
    b = 'cells = CollectionDataSection.CellData("B", listOf("k3", "x1", "x2", "x3", "x4").map { mapOf<String, Any>("key" to it) })'
    edge = 'CollectionDataSection.HeaderFooterData("E", emptyMap())'
    return "listOf(CollectionDataSection(header = #{edge}, #{a}), CollectionDataSection(#{b}))" if grid

    "listOf(CollectionDataSection(header = #{edge}, footer = #{edge}, #{a}), CollectionDataSection(header = #{edge}, #{b}))"
  end

  def node(extra = {})
    { 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'scrollTo' => '@{target}',
      'sections' => [{ 'cell' => 'ACell', 'header' => 'HCell', 'footer' => 'FCell' }, { 'cell' => 'BCell', 'header' => 'HCell' }] }.merge(extra)
  end

  def pager_node(extra = {})
    { 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'scrollTo' => '@{target}', 'layout' => 'horizontal', 'paging' => true,
      'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell' }] }.merge(extra)
  end

  def grid_node(extra = {})
    node('columns' => 2, 'sections' => [{ 'cell' => 'ACell', 'header' => 'HCell' }, { 'cell' => 'BCell' }]).merge(extra)
  end

  # route => [emitted body, data options, targets, first]: each target is a
  # change from `first` (the value the Collection composes with, "" unless
  # named); a nil first composes once, with the target.
  def routes
    # Integers are Int values; strings are Strings (the class decides what a
    # value names, round 14).
    ints = [0, 3, 6, 9, '3#77', -1]
    keys = ['k3', 'x2', 'k1', '0#77', 'nothing', 3]
    {
      'stack' => [emit(node), {}, ints],
      'stackReversed' => [emit(node('reverseLayout' => true)), {}, ints],
      'stackKeys' => [emit(node('cellIdProperty' => 'key')), {}, keys],
      'stackEnriched' => [emit(node('cellIdProperty' => 'key', 'autoChangeTrackingId' => true)), {}, %w[k3_e x2_e k3]],
      'stackCenter' => [emit(node('scrollAnchor' => 'center')), {}, [6]],
      'stackTop' => [emit(node('scrollAnchor' => 'top')), {}, [6]],
      'stackDupKeys' => [emit(node('cellIdProperty' => 'key')), { dup: true }, %w[k1 k3]],
      'stackInitial' => [emit(node), {}, [6], nil],
      'stackAnchor' => [emit(node('defaultScrollAnchor' => 'bottom')), {}, [''], nil],
      'stackAnchorCenter' => [emit(node('defaultScrollAnchor' => 'center')), {}, [''], nil],
      'grid' => [emit(grid_node), { grid: true }, ints],
      'gridReversed' => [emit(grid_node('reverseLayout' => true)), { grid: true }, ints],
      'gridBound' => [emit(grid_node('columns' => '@{cols}')), { grid: true }, ints],
      'gridKeys' => [emit(grid_node('cellIdProperty' => 'key')), { grid: true }, keys],
      'gridDupKeys' => [emit(grid_node('cellIdProperty' => 'key')), { grid: true, dup: true }, %w[k1]],
      'gridAnchor' => [emit(grid_node('defaultScrollAnchor' => 'bottom')), { grid: true }, [''], nil],
      'classList' => [emit({ 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'scrollTo' => '@{target}', 'columns' => 2,
                             'cellClasses' => ['ACell'], 'headerClasses' => ['HCell'] }), { grid: true }, [0, 6]],
      'pager' => [emit(pager_node), { grid: true }, [0, 6, 9, 10]],
      'pagerKeys' => [emit(pager_node('cellIdProperty' => 'key')), { grid: true }, %w[k3 x2 0#77]],
      'flow' => [emit(node('layout' => 'flow', 'height' => 100)), {}, [0, 6]],
      'flowKeys' => [emit(node('layout' => 'flow', 'height' => 100, 'cellIdProperty' => 'key')), {}, %w[k3 x2 0#77]],
      # Round 12 (4f rulings 2026-09-27): the EAGER CollectionStack, declared
      # and bound; the wrapContent Column; defaultScrollAnchor under
      # reverseLayout.
      'eager' => [emit(node('lazy' => 'eager')), {}, [0, 6, 9, -1]],
      'eagerKeys' => [emit(node('lazy' => 'eager', 'cellIdProperty' => 'key')), {}, %w[k3 x2 0#77 nothing]],
      'eagerCenter' => [emit(node('lazy' => 'eager', 'scrollAnchor' => 'center')), {}, [6]],
      'eagerTop' => [emit(node('lazy' => 'eager', 'scrollAnchor' => 'top')), {}, [6]],
      'eagerInitial' => [emit(node('lazy' => 'eager')), {}, [6], nil],
      'eagerAnchor' => [emit(node('lazy' => 'eager', 'defaultScrollAnchor' => 'bottom')), {}, [''], nil],
      'eagerRow' => [emit(node('lazy' => 'eager', 'layout' => 'horizontal')), {}, [6]],
      'eagerBound' => [emit(node('lazy' => '@{mode}', 'cellIdProperty' => 'key')), { mode: 'eager' }, [6, '3#77']],
      'eagerBoundLazy' => [emit(node('lazy' => '@{mode}', 'cellIdProperty' => 'key')), { mode: 'lazy' }, [6, '3#77']],
      'wrap' => [emit(node('height' => 'wrapContent')), {}, [0, 6]],
      'wrapKeys' => [emit(node('height' => 'wrapContent', 'cellIdProperty' => 'key')), {}, %w[k3 x2 0#77]],
      'wrapAnchor' => [emit(node('height' => 'wrapContent', 'defaultScrollAnchor' => 'center')), {}, [''], nil],
      'wrapNone' => [emit(node('height' => 'wrapContent', 'lazy' => 'none')), {}, [6]],
      'stackReversedAnchor' => [emit(node('reverseLayout' => true, 'defaultScrollAnchor' => 'bottom')), {}, [''], nil],
      'stackReversedAnchorTop' => [emit(node('reverseLayout' => true, 'defaultScrollAnchor' => 'top')), {}, [''], nil],
      'stackReversedAnchorCenter' => [emit(node('reverseLayout' => true, 'defaultScrollAnchor' => 'center')), {}, [''], nil],
      'gridReversedAnchor' => [emit(grid_node('reverseLayout' => true, 'defaultScrollAnchor' => 'bottom')), { grid: true }, [''], nil],
      'gridReversedAnchorTop' => [emit(grid_node('reverseLayout' => true, 'defaultScrollAnchor' => 'top')), { grid: true }, [''], nil]
    }
  end

  def program(routes)
    functions = routes.map { |name, (body, _, _)| "@Composable fun #{name}(data: Data, viewModel: Any) {\n#{body}\n}" }
    calls = routes.flat_map do |name, (_, options, targets, *first)|
      first = first.empty? ? '' : first.first
      targets.map do |target|
        sections = data_sections(**options.except(:mode))
        mode = options[:mode] ? ", mode = \"#{options[:mode]}\"" : ''
        first_arg = first.nil? ? 'null' : "\"#{first}\""
        target_arg = target.is_a?(Integer) ? target.to_s : "\"#{target}\""
        "    run(\"#{name} #{target}\", #{first_arg}, #{target_arg}) { value -> #{name}(Data(CollectionDataSource(#{sections}), value#{mode}), Any()) }"
      end
    end
    ["import stubs.*\n", scaffold('ACell', 'A'), scaffold('BCell', 'B'), scaffold('HCell', 'H'), scaffold('FCell', 'F'),
     functions.join("\n\n"),
     <<~KOTLIN
       // One composition, then its effects — as a frame does.
       fun frame(value: Any?, compose: (Any?) -> Unit) {
           Composition.cursor = 0; Drawn.items.clear(); Drawn.keys.clear(); Positions.next = 0
           compose(value)
           val effects = Drawn.effects.toList(); Drawn.effects.clear()
           kotlinx.coroutines.runBlocking { effects.forEach { it() } }
       }
       fun run(label: String, first: String?, target: Any?, compose: (Any?) -> Unit) {
           Composition.slots.clear(); Drawn.effects.clear(); Drawn.scrolledTo = -1; Drawn.offset = 0; Drawn.logs.clear(); Drawn.duplicate = null
           if (first != null) frame(first, compose)
           frame(target, compose)
           val at = Drawn.items.getOrNull(Drawn.scrolledTo) ?: "none"
           println(label + " => " + at + " @" + Drawn.scrolledTo + " offset " + Drawn.offset + " logs " + Drawn.logs.size +
               " of " + Drawn.items.joinToString(" ") + " | duplicate key " + Drawn.duplicate)
       }
       fun main() {
       #{calls.join("\n")}
       }
     KOTLIN
    ].join("\n")
  end

  # Compiles and runs the program; `route target => item [@index of items]`.
  # One compile and run per program: the examples read the same printout
  # (a compile is ~40 s).
  KJ_SCROLL_RUNS = {}

  def run_emitted(routes)
    skip "compile: #{KotlinCompiler.unavailable_reason}" if KotlinCompiler.unavailable_reason

    KJ_SCROLL_RUNS[program(routes)] ||= compile_and_run(routes)
  end

  def compile_and_run(routes)

    stdlib = KotlinCompiler.newest('org.jetbrains.kotlin', 'kotlin-stdlib')
    coroutines = KotlinCompiler.newest('org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm')
    reflect = KotlinCompiler.newest('org.jetbrains.kotlin', 'kotlin-reflect')
    annotations = KotlinCompiler.newest('org.jetbrains', 'annotations')
    Dir.mktmpdir('kjui_scroll') do |dir|
      files = { 'Emitted.kt' => program(routes), 'Stubs.kt' => KJ_SCROLL_STUBS }.merge(KJ_SCROLL_QUALIFIED)
      files.each { |name, source| File.write(File.join(dir, name), source) }
      compiler_cp = [KotlinCompiler.compiler_jar, stdlib, reflect, coroutines, annotations,
                     KotlinCompiler.newest('org.jetbrains.intellij.deps', 'trove4j')].compact.join(':')
      out, status = Open3.capture2e(KotlinCompiler.java_bin, '-cp', compiler_cp, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
                                    '-no-stdlib', '-cp', [stdlib, reflect, annotations, coroutines].join(':'),
                                    '-d', File.join(dir, 'out'), *files.keys.map { |name| File.join(dir, name) })
      errors = out.lines.grep(/error:/)
      raise "the emitted code did not compile:\n#{errors.join}\n#{files['Emitted.kt']}" unless status.success? && errors.empty?

      run, status = Open3.capture2e(KotlinCompiler.java_bin, '-cp', [File.join(dir, 'out'), stdlib, coroutines].join(':'), 'EmittedKt')
      raise "the emitted code did not run:\n#{run}" unless status.success?

      run.lines.to_h { |l| k, v = l.chomp.split(' => ', 2); [k, v] }
    end
  end

  # One file, for the suite's compile ratchet (compile_as_kotlin compiles one
  # source): the stubs in the file's own package, and the names the emit
  # writes fully qualified reached through stubs of the same simple name.
  # The run arm below compiles the emit as it is, in several files.
  def one_file(routes)
    program(routes).sub("import stubs.*\n", '')
                   .gsub('androidx.compose.foundation.lazy.rememberLazyListState()', 'rememberLazyListState()')
                   .gsub('com.kotlinjsonui.utils.CellIdGenerator.', 'CellIdGenerator.')
                   .gsub('androidx.compose.ui.platform.LocalContext.', 'LocalContext.')
                   .gsub('android.content.pm.ApplicationInfo.', 'ApplicationInfo.')
                   .gsub('android.util.Log.', 'Log.')
                   .gsub('androidx.compose.ui.layout.LayoutCoordinates', 'LayoutCoordinates')
                   .gsub('androidx.compose.ui.geometry.Offset', 'Offset')
                   .gsub('androidx.compose.foundation.rememberScrollState()', 'rememberScrollState()')
                   .gsub('androidx.compose.runtime.withFrameNanos', 'withFrameNanos')
                   .gsub('androidx.compose.ui.unit.Constraints', 'Constraints')
                   .gsub('androidx.compose.ui.platform.LocalLayoutDirection', 'LocalLayoutDirection')
                   .gsub('androidx.compose.ui.unit.LayoutDirection', 'LayoutDirection') +
      "\n" + KJ_SCROLL_STUBS.sub("package stubs\n", '').gsub('androidx.compose.ui.layout.LayoutCoordinates', 'LayoutCoordinates')
                            .gsub('androidx.compose.ui.geometry.Offset', 'Offset').gsub('androidx.compose.ui.unit.Constraints', 'Constraints') +
      "fun rememberLazyListState() = remember { LazyListState() }\n" +
      KJ_SCROLL_QUALIFIED['CellIdGenerator.kt'].sub("package com.kotlinjsonui.utils\n", '') +
      "object LocalContext { val current = Context() }\nclass Context { val applicationInfo = ApplicationInfo() }\n" \
      "class ApplicationInfo { var flags = FLAG_DEBUGGABLE\n    companion object { const val FLAG_DEBUGGABLE = 2 } }\n" \
      "object Log { fun w(tag: String, msg: String): Int = 0 }\n" \
      "interface LayoutCoordinates { val isAttached: Boolean; val size: IntSize\n" \
      "    fun localPositionOf(sourceCoordinates: LayoutCoordinates, relativeToSource: Offset): Offset }\n" \
      "class Offset(val x: Float, val y: Float) { companion object { val Zero = Offset(0f, 0f) } }\n" \
      "suspend fun <R> withFrameNanos(onFrame: (Long) -> R): R = onFrame(0L)\n" \
      "enum class LayoutDirection { Ltr, Rtl }\nobject LocalLayoutDirection { val current = LayoutDirection.Ltr }\n" \
      "class Constraints(val minWidth: Int, val maxWidth: Int, val minHeight: Int, val maxHeight: Int) {\n" \
      "    val hasBoundedHeight get() = maxHeight != Int.MAX_VALUE\n" \
      "    companion object { fun fitPrioritizingWidth(minWidth: Int, maxWidth: Int, minHeight: Int, maxHeight: Int) = Constraints(minWidth, maxWidth, minHeight, maxHeight) } }\n"
  end

  it 'every route compiles (the compile arm; the run below compiles it again to run it)' do
    expect(one_file(routes)).to compile_as_kotlin
  end

  def landed(lines, label)
    (lines[label] or raise "no run for #{label}: #{lines.keys.inspect}").split(' ').first
  end

  # `route target` => { at:, index:, offset:, logs: }
  def read(lines, label)
    line = lines[label] or raise "no run for #{label}: #{lines.keys.inspect}"
    at, index, offset, logs = line.match(/\A(\S+) @(-?\d+) offset (-?\d+) logs (\d+)/).captures
    { at: at, index: index.to_i, offset: offset.to_i, logs: logs.to_i }
  end

  it 'an Int is a cell counted across the sections; a key the first cell that has it, on the stack and the grid' do
    lines = run_emitted(routes)
    # The stack's items: H A0 A1 A2 A3 A4 F H B0 … — item 6 is F, item 3 A2.
    # The Ints are cells; -1 names none. The String "3#77" is no cell's key
    # (key = cellId here, and no cell has one): the legacy lazy item 3, A2 on
    # the stack (B2, reversed), and said.
    expect([0, 3, 6, 9, '3#77', -1].map { |t| landed(lines, "stack #{t}") }).to eq(%w[A0 A3 B1 B4 A2 none]), lines.inspect
    expect([0, 3, 6, 9, -1].map { |t| landed(lines, "stackReversed #{t}") }).to eq(%w[A0 A3 B1 B4 none]), lines.inspect
    expect(read(lines, 'stack 3#77')[:logs]).to eq(1), lines.inspect
    # The grid's items: H A0 … A4 _ B0 … — A4 leaves its row part filled, so a
    # filler precedes B0; item 6 is the filler.
    %w[grid gridReversed gridBound].each do |route|
      expect([0, 3, 6, 9, -1].map { |t| landed(lines, "#{route} #{t}") }).to eq(%w[A0 A3 B1 B4 none]), lines.inspect
    end
    %w[stackKeys gridKeys].each do |route|
      # k3 is A3's key and B0's: the first section's. "0#77" is no key: read,
      # as before jsonui-cli 1.9.0, as the lazy item index — item 0, the
      # header — and said (4f ruling, round 11). "nothing" scrolls nowhere.
      expect(%w[k3 x2 k1 0#77 nothing].map { |t| landed(lines, "#{route} #{t}") }).to eq(%w[A3 B2 A1 H none]), lines.inspect
      expect(%w[k3 0#77 nothing].map { |t| read(lines, "#{route} #{t}")[:logs] }).to eq([0, 1, 0]), lines.inspect
      # An Int with cellIdProperty is the counted cell — A3 — not a key and
      # not the lazy item 3 (A2) it was read as until jsonui-cli 1.9.0.
      expect(read(lines, "#{route} 3").values_at(:at, :logs)).to eq(['A3', 0]), lines.inspect
    end
    # Under autoChangeTrackingId a cell's key is its enriched cellId.
    expect(%w[k3_e x2_e k3].map { |t| landed(lines, "stackEnriched #{t}") }).to eq(%w[A3 B2 none]), lines.inspect
    # The class-list grid: a header item, then every data section's cells,
    # each drawn with cellClasses[0] (so the second section's cell 1 is A1).
    expect([0, 6].map { |t| lines["classList #{t}"].split(' ').first(2) }).to eq([%w[A0 @1], %w[A1 @7]]), lines.inspect
  end

  # Round 11 (4f ruling 2026-09-27).
  it 'a scroll runs on a change: the value the list first composes with scrolls nowhere' do
    lines = run_emitted(routes)
    expect(read(lines, 'stackInitial 6')[:index]).to eq(-1), lines.inspect
    expect(read(lines, 'stack 6')[:at]).to eq('B1'), lines.inspect
  end

  it 'scrollAnchor lands the item: bottom its end at the viewport end, center its middle, top its start; reversed, top and bottom trade' do
    lines = run_emitted(routes)
    # A cell is 28 high in a 100 viewport.
    expect(read(lines, 'stack 6')[:offset]).to eq(-72), lines.inspect        # bottom (the default)
    expect(read(lines, 'grid 6')[:offset]).to eq(-72), lines.inspect
    expect(read(lines, 'stackCenter 6')[:offset]).to eq(-36), lines.inspect
    expect(read(lines, 'stackTop 6')[:offset]).to eq(0), lines.inspect
    expect(read(lines, 'stackReversed 6')[:offset]).to eq(0), lines.inspect  # bottom, reversed: the list's start
  end

  it 'defaultScrollAnchor counts cells across the sections, as scrollTo does' do
    lines = run_emitted(routes)
    # Ten cells: bottom is the last, B4 (item 12, after H A0…A4 F H B0…B3);
    # center the sixth, B0. The grid: B4 after its filler, item 11.
    expect(read(lines, 'stackAnchor ').values_at(:at, :index)).to eq(['B4', 12]), lines.inspect
    expect(read(lines, 'stackAnchorCenter ').values_at(:at, :index)).to eq(['B0', 8]), lines.inspect
    expect(read(lines, 'gridAnchor ').values_at(:at, :index)).to eq(['B4', 11]), lines.inspect
  end

  it 'the pager and the flow scroll by the rule too (they read no scrollTo before 1.9.0)' do
    lines = run_emitted(routes)
    # A page is a cell: A0…A4 B0…B4. "10" names no page; "0#77" (no key) is
    # the legacy item index, page 0, and is said.
    expect([0, 6, 9, 10].map { |t| read(lines, "pager #{t}")[:index] }).to eq([0, 6, 9, -1]), lines.inspect
    expect(%w[k3 x2 0#77].map { |t| read(lines, "pagerKeys #{t}").values_at(:index, :logs) }).to eq([[3, 0], [7, 0], [0, 1]]), lines.inspect
    # The flow scrolls its own scroll state to the cell's place: the content
    # at 0, cell n at 28 (n + 1) in the stubs' layout, bottom-anchored in a
    # 100 viewport — 28 (n + 1) - 72 (k3 is A3, n 3; x2 is B2, n 7). A String that is no key names nothing
    # on a flow (no lazy item).
    expect([0, 6].map { |t| read(lines, "flow #{t}")[:index] }).to eq([0, 124]), lines.inspect
    expect(%w[k3 x2 0#77].map { |t| read(lines, "flowKeys #{t}")[:index] }).to eq([40, 152, -1]), lines.inspect
  end

  # Round 12 (4f rulings 2026-09-27). In the stubs a non-lazy container's
  # viewport is laid out first, then its cells, each 28 below the last: cell
  # n at 28 (n + 1), in a 100 viewport scrolled to 0. What the scroll asks
  # for is the scroll position — bottom-anchored (the default) 28 (n + 1) - 72.
  it 'the EAGER CollectionStack scrolls to the cell by the rule — an Int the counted cell, a String a key, landed by scrollAnchor, on a change' do
    lines = run_emitted(routes)
    # 0 → A0 (28 - 72, the top: 0); 6 → B1 (196 - 72); 9 → B4; -1 nowhere.
    expect([0, 6, 9, -1].map { |t| read(lines, "eager #{t}")[:index] }).to eq([0, 124, 208, -1]), lines.inspect
    # k3 is A3's key (and B0's): A3, 112 - 72; x2 is B2's: 224 - 72. The
    # legacy "0#77" names no cell here — the container has no lazy item —
    # and nothing is said.
    expect(%w[k3 x2 0#77 nothing].map { |t| read(lines, "eagerKeys #{t}").values_at(:index, :logs) }).to eq([[40, 0], [152, 0], [-1, 0], [-1, 0]]), lines.inspect
    expect(read(lines, 'eagerCenter 6')[:index]).to eq(160), lines.inspect   # 196 - 36
    expect(read(lines, 'eagerTop 6')[:index]).to eq(196), lines.inspect
    expect(read(lines, 'eagerInitial 6')[:index]).to eq(-1), lines.inspect   # the value it composes with
    expect(read(lines, 'eagerRow 6')[:index]).to eq(124), lines.inspect      # along x
  end

  it "a bound `lazy` decides at run time: EAGER scrolls its cells, LAZY its items (and reads the legacy form)" do
    lines = run_emitted(routes)
    expect(%w[6 3#77].map { |t| read(lines, "eagerBound #{t}").values_at(:index, :logs) }).to eq([[124, 0], [-1, 0]]), lines.inspect
    expect(%w[6 3#77].map { |t| read(lines, "eagerBoundLazy #{t}").values_at(:at, :logs) }).to eq([['B1', 0], ['A2', 1]]), lines.inspect
  end

  it 'the wrapContent Column scrolls to the cell by the rule; `lazy: none` scrolls nowhere' do
    lines = run_emitted(routes)
    expect([0, 6].map { |t| read(lines, "wrap #{t}")[:index] }).to eq([0, 124]), lines.inspect
    expect(%w[k3 x2 0#77].map { |t| read(lines, "wrapKeys #{t}")[:index] }).to eq([40, 152, -1]), lines.inspect
    expect(read(lines, 'wrapNone 6')[:index]).to eq(-1), lines.inspect
  end

  it 'defaultScrollAnchor on a non-lazy container: the middle or last cell at its top edge, once the cells arrive' do
    lines = run_emitted(routes)
    expect(read(lines, 'eagerAnchor ')[:index]).to eq(280), lines.inspect    # B4, the tenth cell: 28 × 10
    expect(read(lines, 'wrapAnchor ')[:index]).to eq(168), lines.inspect     # center: B0, the sixth: 28 × 6
  end

  it 'defaultScrollAnchor under reverseLayout: bottom is where the list rests, top the cell drawn at the visual top' do
    lines = run_emitted(routes)
    # The reversed stack emits B first: H B0 … B4 H A0 … A4 F. bottom moves
    # nothing (until jsonui-cli 1.9.0 it went to B4, item 5 — the visual
    # top); top goes to the last cell emitted, A4 (item 11); center is the
    # middle cell, B0.
    expect(read(lines, 'stackReversedAnchor ')[:index]).to eq(-1), lines.inspect
    expect(read(lines, 'stackReversedAnchorTop ').values_at(:at, :index)).to eq(['A4', 11]), lines.inspect
    expect(read(lines, 'stackReversedAnchorCenter ').values_at(:at, :index)).to eq(['B0', 1]), lines.inspect
    expect(read(lines, 'gridReversedAnchor ')[:index]).to eq(-1), lines.inspect
    expect(read(lines, 'gridReversedAnchorTop ')[:at]).to eq('A4'), lines.inspect
  end

  it "no two items of a lazy list share a key — two sections', or two cells of one section" do
    lines = run_emitted(routes)
    # Section B's k3 is "1:k3"; section A's second k1 is "k1#2".
    expect(lines.select { |_, v| !v.end_with?('| duplicate key null') }).to eq({}), lines.inspect
    # The first cell with the key is still the one a key names.
    expect(landed(lines, 'stackDupKeys k1')).to eq('A1'), lines.inspect
    expect(landed(lines, 'stackDupKeys k3')).to eq('A3'), lines.inspect
    expect(landed(lines, 'gridDupKeys k1')).to eq('A1'), lines.inspect
  end
end
