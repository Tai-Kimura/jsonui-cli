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
    interface Alignment { companion object { val TopStart = object : Alignment {} } }
    class Arrangement { companion object { fun spacedBy(space: Dp): Arrangement = Arrangement() } }
    object GridCells { class Fixed(val count: Int) }
    class GridItemSpan(val span: Int)
    class LazyGridItemSpanScope(val maxLineSpan: Int, val maxCurrentLineSpan: Int)

    // What an item's content draws, and the items in the order they were emitted.
    object Drawn {
        var mark = StringBuilder()
        fun draw(s: String) { mark.append(s) }
        val items = mutableListOf<String>()
        var scrolledTo = -1
        val effects = mutableListOf<suspend () -> Unit>()
        fun record(content: () -> Unit) { mark = StringBuilder(); content(); items += mark.toString().ifEmpty { "_" } }
        // A lazy list's item keys, and one two items shared (Compose throws
        // "Key … was already used" when both are composed).
        val keys = mutableSetOf<Any>()
        var duplicate: Any? = null
        fun key(key: ((Int) -> Any)?, count: Int) { key?.let { k -> repeat(count) { i -> k(i).let { if (!keys.add(it)) duplicate = it } } } }
    }
    class LayoutInfo { val viewportStartOffset = 0; val viewportEndOffset = 100 }
    class LazyState {
        val layoutInfo = LayoutInfo()
        suspend fun scrollToItem(index: Int, scrollOffset: Int = 0) { Drawn.scrolledTo = index }
        suspend fun animateScrollToItem(index: Int, scrollOffset: Int = 0) { Drawn.scrolledTo = index }
    }
    fun rememberLazyGridState() = LazyState()
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
                         horizontalArrangement: Arrangement? = null, modifier: Modifier = Modifier, state: LazyState? = null,
                         content: LazyGridScope.() -> Unit) { LazyGridScope().content() }
    enum class CollectionStackMode { LAZY, EAGER, NONE }
    enum class CollectionStackAxis { VERTICAL, HORIZONTAL }
    fun CollectionStack(mode: CollectionStackMode, axis: CollectionStackAxis, modifier: Modifier = Modifier, spacing: Dp? = null,
                        reverseLayout: Boolean = false, lazyState: LazyState? = null,
                        lazyContent: LazyListScope.() -> Unit, eagerContent: () -> Unit) { LazyListScope().lazyContent() }
    fun Box(modifier: Modifier = Modifier, contentAlignment: Alignment = Alignment.TopStart, content: () -> Unit) { content() }
    fun LaunchedEffect(key1: Any?, block: suspend kotlinx.coroutines.CoroutineScope.() -> Unit) {
        Drawn.effects += { kotlinx.coroutines.coroutineScope { block() } }
    }
    inline fun <T> remember(key1: Any?, calculation: () -> T): T = calculation()
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
    class Data(val rows: CollectionDataSource? = null, val target: String? = null, val cols: Int = 2)
  KOTLIN

  # The two stubs a fully-qualified name reaches.
  KJ_SCROLL_QUALIFIED = {
    'Lazy.kt' => "package androidx.compose.foundation.lazy\nfun rememberLazyListState() = stubs.LazyState()\n",
    # An enrichment that says it ran: "<key>_e".
    'CellIdGenerator.kt' => "package com.kotlinjsonui.utils\nobject CellIdGenerator {\n" \
                            "    fun enrichCellIds(data: List<Map<String, Any>>, primaryKey: String): List<Map<String, Any>> =\n" \
                            "        data.map { it + (\"cellId\" to \"${it[primaryKey]}_e\") }\n}\n"
  }.freeze

  # Section A: header, cells A0…A4 (keys k0…k4), footer; section B: header,
  # cells B0…B4 (keys k3 — shared with A — x1…x4). `grid: true` drops A's
  # footer and B's header, so a filler item ends A's part-filled row.
  def data_sections(grid: false)
    a = 'cells = CollectionDataSection.CellData("A", List(5) { mapOf<String, Any>("key" to "k$it") })'
    b = 'cells = CollectionDataSection.CellData("B", listOf("k3", "x1", "x2", "x3", "x4").map { mapOf<String, Any>("key" to it) })'
    edge = 'CollectionDataSection.HeaderFooterData("E", emptyMap())'
    return "listOf(CollectionDataSection(header = #{edge}, #{a}), CollectionDataSection(#{b}))" if grid

    "listOf(CollectionDataSection(header = #{edge}, footer = #{edge}, #{a}), CollectionDataSection(header = #{edge}, #{b}))"
  end

  def node(extra = {})
    { 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'scrollTo' => '@{target}',
      'sections' => [{ 'cell' => 'ACell', 'header' => 'HCell', 'footer' => 'FCell' }, { 'cell' => 'BCell', 'header' => 'HCell' }] }.merge(extra)
  end

  def grid_node(extra = {})
    node('columns' => 2, 'sections' => [{ 'cell' => 'ACell', 'header' => 'HCell' }, { 'cell' => 'BCell' }]).merge(extra)
  end

  # route => [emitted body, grid data?, targets]
  def routes
    ints = %w[0 3 6 9 3#77]
    keys = %w[k3 x2 k1 0#77 nothing]
    {
      'stack' => [emit(node), false, ints],
      'stackReversed' => [emit(node('reverseLayout' => true)), false, ints],
      'stackKeys' => [emit(node('cellIdProperty' => 'key')), false, keys],
      'stackEnriched' => [emit(node('cellIdProperty' => 'key', 'autoChangeTrackingId' => true)), false, %w[k3_e x2_e k3]],
      'grid' => [emit(grid_node), true, ints],
      'gridReversed' => [emit(grid_node('reverseLayout' => true)), true, ints],
      'gridBound' => [emit(grid_node('columns' => '@{cols}')), true, ints],
      'gridKeys' => [emit(grid_node('cellIdProperty' => 'key')), true, keys],
      'classList' => [emit({ 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'scrollTo' => '@{target}', 'columns' => 2,
                             'cellClasses' => ['ACell'], 'headerClasses' => ['HCell'] }), true, %w[0 6]]
    }
  end

  def program(routes)
    functions = routes.map { |name, (body, _, _)| "@Composable fun #{name}(data: Data, viewModel: Any) {\n#{body}\n}" }
    calls = routes.flat_map do |name, (_, grid, targets)|
      targets.map do |target|
        "    run(\"#{name} #{target}\") { #{name}(Data(CollectionDataSource(#{data_sections(grid: grid)}), \"#{target}\"), Any()) }"
      end
    end
    ["import stubs.*\n", scaffold('ACell', 'A'), scaffold('BCell', 'B'), scaffold('HCell', 'H'), scaffold('FCell', 'F'),
     functions.join("\n\n"),
     <<~KOTLIN
       fun run(label: String, compose: () -> Unit) {
           Drawn.items.clear(); Drawn.effects.clear(); Drawn.scrolledTo = -1; Drawn.keys.clear(); Drawn.duplicate = null
           compose()
           kotlinx.coroutines.runBlocking { Drawn.effects.forEach { it() } }
           val at = Drawn.items.getOrNull(Drawn.scrolledTo) ?: "none"
           println(label + " => " + at + " @" + Drawn.scrolledTo + " of " + Drawn.items.joinToString(" ") + " | duplicate key " + Drawn.duplicate)
       }
       fun main() {
       #{calls.join("\n")}
       }
     KOTLIN
    ].join("\n")
  end

  # Compiles and runs the program; `route target => item [@index of items]`.
  def run_emitted(routes)
    skip "compile: #{KotlinCompiler.unavailable_reason}" if KotlinCompiler.unavailable_reason

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
  # source): the stubs in the file's own package, and the two names the emit
  # writes fully qualified reached through stubs of the same simple name.
  # The run arm below compiles the emit as it is, in four files.
  def one_file(routes)
    program(routes).sub("import stubs.*\n", '')
                   .gsub('androidx.compose.foundation.lazy.rememberLazyListState()', 'rememberLazyListState()')
                   .gsub('com.kotlinjsonui.utils.CellIdGenerator.', 'CellIdGenerator.') +
      "\n" + KJ_SCROLL_STUBS.sub("package stubs\n", '') +
      "fun rememberLazyListState() = LazyState()\n" +
      KJ_SCROLL_QUALIFIED['CellIdGenerator.kt'].sub("package com.kotlinjsonui.utils\n", '')
  end

  it 'every route compiles (the compile arm; the run below compiles it again to run it)' do
    expect(one_file(routes)).to compile_as_kotlin
  end

  def landed(lines, label)
    (lines[label] or raise "no run for #{label}: #{lines.keys.inspect}").split(' ').first
  end

  it 'an Int is a cell counted across the sections; a key the first cell that has it, on the stack and the grid' do
    lines = run_emitted(routes)
    # The stack's items: H A0 A1 A2 A3 A4 F H B0 … — item 6 is F, item 3 A2.
    %w[stack stackReversed].each do |route|
      expect(%w[0 3 6 9 3#77].map { |t| landed(lines, "#{route} #{t}") }).to eq(%w[A0 A3 B1 B4 A3]), lines.inspect
    end
    # The grid's items: H A0 … A4 _ B0 … — A4 leaves its row part filled, so a
    # filler precedes B0; item 6 is the filler.
    %w[grid gridReversed gridBound].each do |route|
      expect(%w[0 3 6 9 3#77].map { |t| landed(lines, "#{route} #{t}") }).to eq(%w[A0 A3 B1 B4 A3]), lines.inspect
    end
    %w[stackKeys gridKeys].each do |route|
      # k3 is A3's key and B0's: the first section's. "0#77" is no key: read,
      # as before jsonui-cli 1.9.0, as the lazy item index — item 0, the
      # header. "nothing" scrolls nowhere.
      expect(%w[k3 x2 k1 0#77 nothing].map { |t| landed(lines, "#{route} #{t}") }).to eq(%w[A3 B2 A1 H none]), lines.inspect
    end
    # Under autoChangeTrackingId a cell's key is its enriched cellId.
    expect(%w[k3_e x2_e k3].map { |t| landed(lines, "stackEnriched #{t}") }).to eq(%w[A3 B2 none]), lines.inspect
    # No two items of a lazy list share a key: section B's k3 is "1:k3" (a
    # shared key took the list down in Compose once both items were composed).
    expect(lines.select { |_, v| !v.end_with?('| duplicate key null') }).to eq({}), lines.inspect
    # The class-list grid: a header item, then every data section's cells,
    # each drawn with cellClasses[0] (so the second section's cell 1 is A1).
    expect(%w[0 6].map { |t| lines["classList #{t}"].split(' ').first(2) }).to eq([%w[A0 @1], %w[A1 @7]]), lines.inspect
  end
end
