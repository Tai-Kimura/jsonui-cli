# frozen_string_literal: true

require 'set'
require 'tmpdir'
require_relative '../../../lib/compose/components/collection_component'
require_relative '../../../lib/compose/generators/cell_generator'
require_relative '../../support/kotlin_compiler'
require_relative '../../support/compose_bounded_scroll_stubs'

# A Collection cell (and a section header / footer) is composed with its own
# data from its first frame. Each one gets its ViewModel from
# `viewModel(key = …)`, which makes a fresh one for a key it has not seen: a
# cell composed for the first time, or — under autoChangeTrackingId, whose
# key carries a hash of the cell's contents — a cell whose data changed.
# Until this change the ViewModel was fed only by `LaunchedEffect(data) {
# updateData(data) }`, which runs after the frame is composed, so that frame
# drew the cell from its layout's defaults (measured on an emulator: a cell
# with a label its data hides drew taller for exactly one frame on every data
# change, and in a reverseLayout list every row above it moved).
#
# Every site now seeds the ViewModel in composition, before the view
# (CollectionComponent.seed_view_model_line), and keeps the LaunchedEffect.
#
# The run arm COMPILES the emitted routes with kotlinc and RUNS them on the
# JVM against stubs that keep Compose's timing: a frame composes the body;
# a LaunchedEffect's block is queued and runs only after that frame (and
# again only when its key changes); `remember` keeps its value per call
# position while its keys are equal; `viewModel(key)` keeps one ViewModel per
# key. Each view prints what its ViewModel holds when it composes — its
# letter and the row's id, `-` for none. A green says the emitted code hands
# the view its data before the view composes, against these stubs.
RSpec.describe 'kjui codegen: a Collection cell composes with its own data from its first frame' do
  FIRST_FRAME_SECTIONS = [{ 'cell' => 'ACell', 'header' => 'HCell', 'footer' => 'FCell' }, { 'cell' => 'BCell', 'header' => 'HCell' }].freeze

  FIRST_FRAME_ROUTES = {
    'list' => {},
    'lazyNone' => { 'lazy' => 'none' },
    'wrapContent' => { 'height' => 'wrapContent' },
    'grid' => { 'columns' => 2 },
    'gridLazyNone' => { 'columns' => 2, 'lazy' => 'none' },
    'tracked' => { 'cellIdProperty' => 'id', 'autoChangeTrackingId' => true },
    'trackedGrid' => { 'columns' => 2, 'cellIdProperty' => 'id', 'autoChangeTrackingId' => true },
    'keyed' => { 'cellIdProperty' => 'id' },
    'flow' => { 'layout' => 'flow' },
    'row' => { 'layout' => 'horizontal', 'lazy' => 'none' },
    'paging' => { 'layout' => 'horizontal', 'paging' => true },
    'classList' => { 'sections' => nil, 'cellClasses' => ['ACell'], 'headerClasses' => ['HCell'], 'footerClasses' => ['FCell'] }
  }.freeze

  def emit(extra)
    %i[info debug warn].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    node = { 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'sections' => FIRST_FRAME_SECTIONS }.merge(extra).compact
    ComposeBoundedScrollStubs.unqualify(KjuiTools::Compose::Components::CollectionComponent.generate(node, 1, Set.new, nil))
  end

  # The ViewModel and view signatures `kjui g cell` scaffolds; the view
  # prints what its ViewModel holds when it composes.
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
    interface Alignment { interface Vertical; companion object { val TopStart = object : Alignment {}; val Top = object : Vertical {} } }
    class Arrangement { companion object { fun spacedBy(space: Dp): Arrangement = Arrangement() } }
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
    open class Model { var item: Map<String, Any> = emptyMap() }
    inline fun <reified T : Any> viewModel(key: String? = null): T =
        Frame.models.getOrPut(key!!) { T::class.java.getDeclaredConstructor().newInstance() } as T

    class CollectionDataSource(val sections: List<CollectionDataSection> = emptyList())
    class CollectionDataSection(val cells: CellData? = null, val header: HeaderFooterData? = null, val footer: HeaderFooterData? = null) {
        class CellData(val viewName: String, val data: List<Map<String, Any>>)
        class HeaderFooterData(val viewName: String, val data: Map<String, Any>)
    }
    class Data(val rows: CollectionDataSource? = null)
    fun cells(name: String, n: Int, rev: String) = CollectionDataSection.CellData(name, List(n) { mapOf<String, Any>("id" to "$name$it$rev") })
    fun edge(name: String, rev: String) = CollectionDataSection.HeaderFooterData(name, mapOf<String, Any>("id" to "$name$rev"))
    fun rows(rev: String) = Data(CollectionDataSource(listOf(
        CollectionDataSection(cells("a", 2, rev), edge("h", rev), edge("f", rev)),
        CollectionDataSection(cells("b", 1, rev), edge("h", rev))
    )))
    #{ComposeBoundedScrollStubs::KOTLIN}
  KOTLIN

  # Per route, one line of frames separated by ` | `:
  #   1. the first frame;
  #   2. the next frame, after the first one's effects ran;
  #   3. a frame after a cell's own write to its ViewModel, the data unchanged;
  #   4. a frame with every row's data changed (its id gains `'`).
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

  def routes
    FIRST_FRAME_ROUTES.transform_values { |extra| emit(extra) }
  end

  it 'every site seeds its ViewModel in composition, before its view and ahead of the LaunchedEffect it keeps' do
    FIRST_FRAME_ROUTES.each do |route, extra|
      code = emit(extra)
      # (The class-list shape's header / footer has no data to feed: its view
      # follows its ViewModel line directly.)
      fed = code.scan(/^\s*val (\w+ViewModel): \w+ViewModel = viewModel\(key = .*\n\s*(.*)\n\s*(.*)\n/)
                .reject { |_, next_line, _| next_line.start_with?('Box(') }
      expect(fed).not_to be_empty, route
      fed.each do |vm, seed, effect|
        expect(seed).to match(/\Aremember\(#{vm}, ([\w.]+)\) \{ #{vm}\.updateData\(\1\); \1 \}\z/), "#{route}: #{seed}"
        data = seed[/\Aremember\(#{vm}, ([\w.]+)\)/, 1]
        expect(effect).to start_with("LaunchedEffect(#{data}) {"), "#{route}: #{effect}"
      end
      expect(code.scan('.updateData(').size).to eq(fed.size * 2), route
    end
    # Every emitted feed in the component is seeded: each LaunchedEffect
    # that updates a ViewModel follows a seed_view_model_line.
    source = File.read(File.expand_path('../../../lib/compose/components/collection_component.rb', __dir__)).lines
    feeds = source.each_index.select do |i|
      source[i].include?('indent("LaunchedEffect(') && (source[i] + source[i + 1].to_s).match?(/ViewModel\.updateData\(/)
    end
    expect(feeds.size).to eq(18)
    feeds.each { |i| expect(source[i - 1]).to include('seed_view_model_line('), "line #{i + 1}: #{source[i]}" }
  end

  it 'every route compiles (the compile arm; the run below compiles it again to run it)' do
    expect(program(routes)).to compile_as_kotlin
  end

  it 'the first frame draws every cell, header and footer with its own data, and later frames follow the data' do
    frames = run(routes)
    frames.each do |route, line|
      # The class-list shape's header / footer carry no data (its section has
      # none to give them): its cells are what it feeds.
      line = line.split(' | ').map { |f| f.split.grep_v(/\A[HF]-\z/).join(' ') }.join(' | ') if route == 'classList'
      f1, f2, f3, f4 = line.split(' | ')
      # 1. No view composed from its ViewModel's defaults.
      expect(f1).not_to include('-'), "#{route}: #{line}"
      # 2. The effects that ran after it changed nothing.
      expect(f2).to eq(f1), "#{route}: #{line}"
      # 3. A recomposition with the same data leaves a cell's own write alone
      #    (the seed runs per new ViewModel or new data only).
      expect(f3.split.grep(/\AA/).uniq).to eq(['Aown']), "#{route}: #{line}"
      # 4. New data is drawn in the frame that brings it — a reused
      #    ViewModel (same key) or a new one (autoChangeTrackingId's key).
      expect(f4.split.reject { |t| t == '/' }).to all(end_with("'")), "#{route}: #{line}"
    end
    expect(frames['list'].split(' | ').first).to eq('Hh Aa0 Aa1 Ff Hh Bb0 / Hh Aa0 Aa1 Ff Hh Bb0')
    expect(frames['paging'].split(' | ').first).to eq('Aa0 Aa1 Bb0')
    expect(frames['classList'].split(' | ').first).to eq('H- Aa0 Aa1 Ab0 F-')
    expect(frames.keys).to match_array(FIRST_FRAME_ROUTES.keys)
  end

  it 'control: without the seed, the stubs show the first frame drawn from the defaults' do
    allow(KjuiTools::Compose::Components::CollectionComponent).to receive(:seed_view_model_line) { |_, _, depth| '    ' * depth + '// unseeded' }
    frames = run(FIRST_FRAME_ROUTES.slice('list', 'trackedGrid', 'paging').transform_values { |extra| emit(extra) })
    frames.each do |route, line|
      f1, f2, _f3, f4 = line.split(' | ')
      expect(f1.split.reject { |t| t == '/' }).to all(end_with('-')), "#{route}: #{line}"
      expect(f2).not_to include('-'), "#{route}: #{line}"
      # A re-keyed cell (autoChangeTrackingId) is a new ViewModel: its data
      # changed, and its frame drew the defaults again.
      expect(f4.split.grep(/\AA/)).to all(end_with('-')), "#{route}: #{line}" if route == 'trackedGrid'
    end
  end
end
