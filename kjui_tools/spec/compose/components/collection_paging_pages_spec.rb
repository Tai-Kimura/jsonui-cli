# frozen_string_literal: true

require 'open3'
require 'set'
require 'tmpdir'
require_relative '../../../lib/compose/components/collection_component'
require_relative '../../../lib/compose/generators/cell_generator'
require_relative '../../support/kotlin_compiler'

# A paging Collection's pages (4f ruling, 2026-09-26, round 6): one page per
# cell, every drawn section's cells in order — what sjui, rjui and both
# Dynamic renderers draw. Until jsonui-cli 1.9.0 the pager read data section
# 0 only (its page count and its cells: `….firstOrNull()?.cells`), so a
# second section drew no page; and the class-list shape (cellClasses, no
# `sections`) drew none at all. It is one section now — the first data
# section, or the declared list — as on the other one-section routes. One
# declared section keeps the text this emitter always wrote (the golden below
# is that emit, measured on deaead11 for the faces' carousel shape).
#
# The arm RUNS the emitted pager: compiled by kotlinc and run on the JVM
# against stubs in which HorizontalPager composes each of its pageCount pages
# in turn and each cell prints the item it was given and the index its test
# tag carries — the page's place among all the pages.
RSpec.describe 'kjui codegen: a paging Collection draws a page per cell of every section' do
  def emit(extra, definitions = {})
    %i[info debug warn].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = definitions
    node = { 'type' => 'Collection', 'id' => 'pager', 'layout' => 'horizontal', 'paging' => true, 'items' => '@{rows}' }.merge(extra)
    KjuiTools::Compose::Components::CollectionComponent.generate(node, 1, Set.new, nil)
  ensure
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  def scaffold(class_name, letter)
    generator = KjuiTools::Compose::Generators::CellGenerator.allocate
    view = generator.send(:main_cell_content, class_name, nil, 'com.example')
    model = generator.send(:cell_viewmodel_content, class_name, 'x_cell', 'com.example')
    params = view[/fun #{class_name}View\((.*?)\)\s*\{/m, 1] or raise "no #{class_name}View in the scaffold"
    update = model[/fun updateData\((.*?)\)/, 1] or raise 'no updateData in the scaffold'
    "class #{class_name}ViewModel { var item: Map<String, Any> = emptyMap(); fun updateData(#{update}) { item = updates } }\n" \
      "@Composable fun #{class_name}View(#{params.strip}) { Pages.draw(\"#{letter}\" + viewModel.item[\"id\"] + \"@\" + ((modifier as? Tagged)?.tag?.substringAfterLast('_') ?: \"\")) }\n"
  end

  PAGING_PAGES_STUBS = <<~KOTLIN
    annotation class Composable
    interface Modifier { companion object : Modifier }
    class Tagged(val tag: String) : Modifier
    fun Modifier.testTag(tag: String): Modifier = Tagged(tag)
    fun Modifier.fillMaxSize(): Modifier = this
    class SemanticsPropertyReceiver { var testTagsAsResourceId: Boolean = false }
    fun Modifier.semantics(properties: SemanticsPropertyReceiver.() -> Unit): Modifier = this
    class Dp
    val Int.dp: Dp get() = Dp()
    class PagerState(val pageCount: () -> Int, val currentPage: Int = 0) { suspend fun animateScrollToPage(page: Int) {} }
    fun rememberPagerState(pageCount: () -> Int): PagerState = PagerState(pageCount)
    fun rememberPagerState(initialPage: Int, pageCount: () -> Int): PagerState = PagerState(pageCount, initialPage)
    // The pager composes each of its pages in turn: a page is a line of the printout.
    object Pages {
        val drawn = mutableListOf<String>()
        fun draw(cell: String) { drawn += cell }
    }
    fun HorizontalPager(state: PagerState, pageSpacing: Dp? = null, modifier: Modifier = Modifier, pageContent: (Int) -> Unit) {
        for (page in 0 until state.pageCount()) pageContent(page)
    }
    fun LaunchedEffect(key1: Any?, block: suspend kotlinx.coroutines.CoroutineScope.() -> Unit) {
        kotlinx.coroutines.runBlocking { block() }
    }
    fun <T> snapshotFlow(block: () -> T): kotlinx.coroutines.flow.Flow<T> = kotlinx.coroutines.flow.flowOf(block())
    // The screen's ViewModel: the pager writes the page it shows back here.
    class ScreenModel { val written = mutableListOf<Map<String, Any>>(); fun updateData(updates: Map<String, Any>) { written += updates } }
    inline fun <T> remember(calculation: () -> T): T = calculation()
    inline fun <T> remember(key1: Any?, calculation: () -> T): T = calculation()
    // A bound pager's programmatic-scroll flag (`var … by remember { mutableStateOf(false) }`).
    class MutableState<T>(var value: T)
    fun <T> mutableStateOf(value: T): MutableState<T> = MutableState(value)
    operator fun <T> MutableState<T>.getValue(thisRef: Any?, property: kotlin.reflect.KProperty<*>): T = value
    operator fun <T> MutableState<T>.setValue(thisRef: Any?, property: kotlin.reflect.KProperty<*>, value: T) { this.value = value }
    inline fun <T> remember(key1: Any?, key2: Any?, calculation: () -> T): T = calculation()
    object com { object kotlinjsonui { object utils { object CellIdGenerator {
        fun enrichCellIds(data: List<Map<String, Any>>, property: String): List<Map<String, Any>> = data
    } } } }
    inline fun <reified T : Any> viewModel(key: String? = null): T = T::class.java.getDeclaredConstructor().newInstance()
    class CollectionDataSource(val sections: List<CollectionDataSection> = emptyList())
    class CollectionDataSection(val cells: CellData? = null) {
        class CellData(val viewName: String, val data: List<Map<String, Any>>)
    }
    class Data(val rows: CollectionDataSource? = null, val page: Int = 3)
    fun cells(name: String, n: Int) = CollectionDataSection.CellData(name, List(n) { mapOf<String, Any>("id" to "$name$it") })
  KOTLIN

  FOUR_SECTIONS = [{ 'cell' => 'ACell' }, { 'header' => 'HCell' }, { 'cell' => 'BCell' }, { 'cell' => 'CCell' }].freeze

  def routes
    {
      'twoSections' => emit('sections' => FOUR_SECTIONS.values_at(0, 2)),
      'aSectionWithoutACell' => emit('sections' => FOUR_SECTIONS),
      'bound' => emit('sections' => FOUR_SECTIONS.values_at(0, 2), 'currentPage' => '@{page}'),
      'tracked' => emit('sections' => FOUR_SECTIONS.values_at(0, 2), 'cellIdProperty' => 'id', 'autoChangeTrackingId' => true),
      'oneSection' => emit('sections' => FOUR_SECTIONS.first(1)),
      'classList' => emit('cellClasses' => ['ACell'])
    }
  end

  # Data sections: A0 A1 | H0..H4 (under FOUR_SECTIONS, a section whose
  # declared config draws no cell) | B0 B1 B2 | C0.
  def program(functions)
    calls = functions.keys.map do |fn|
      "    Pages.drawn.clear(); #{fn}(Data(CollectionDataSource(listOf(CollectionDataSection(cells(\"A\", 2)), " \
        "CollectionDataSection(cells(\"H\", 5)), CollectionDataSection(cells(\"B\", 3)), CollectionDataSection(cells(\"C\", 1))))), ScreenModel()); " \
        "println(\"#{fn} => \" + Pages.drawn.joinToString(\" \"))"
    end
    [PAGING_PAGES_STUBS, scaffold('ACell', 'a'), scaffold('BCell', 'b'), scaffold('CCell', 'c'),
     functions.map { |fn, body| "@Composable fun #{fn}(data: Data, viewModel: ScreenModel) {\n#{body}\n}" }.join("\n\n"),
     "fun main() {\n#{calls.join("\n")}\n}"].join("\n")
  end

  it 'every route compiles (the run below compiles it again to run it)' do
    expect(program(routes)).to compile_as_kotlin
  end

  it 'a page per cell of every drawn section, in order, each tagged with its place among all the pages' do
    skip "compile: #{KotlinCompiler.unavailable_reason}" if KotlinCompiler.unavailable_reason

    lines = Dir.mktmpdir('kjui_pages') do |dir|
      File.write(File.join(dir, 'Emitted.kt'), program(routes))
      stdlib = KotlinCompiler.newest('org.jetbrains.kotlin', 'kotlin-stdlib')
      coroutines = KotlinCompiler.newest('org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm')
      reflect = KotlinCompiler.newest('org.jetbrains.kotlin', 'kotlin-reflect')
      annotations = KotlinCompiler.newest('org.jetbrains', 'annotations')
      compiler_cp = [KotlinCompiler.compiler_jar, stdlib, reflect, coroutines, annotations,
                     KotlinCompiler.newest('org.jetbrains.intellij.deps', 'trove4j')].compact.join(':')
      out, = KotlinCompiler.java_capture2e('-cp', compiler_cp, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
                             '-no-stdlib', '-cp', [stdlib, reflect, annotations, coroutines].join(':'),
                             '-d', File.join(dir, 'out'), File.join(dir, 'Emitted.kt'))
      raise "did not compile:\n#{out}" if out.include?('error:')

      run, status = KotlinCompiler.java_capture2e('-cp', [File.join(dir, 'out'), stdlib, reflect, coroutines].join(':'), 'EmittedKt')
      raise "did not run:\n#{run}" unless status.success?

      run.lines.to_h { |l| l.chomp.split(' => ', 2) }
    end
    # Each printed page: the cell drawn (a / b / c), the item, `@` the index
    # its test tag carries. Declared section k draws data section k.
    expect(lines['aSectionWithoutACell']).to eq('aA0@0 aA1@1 bB0@2 bB1@3 bB2@4 cC0@5'), lines.inspect
    two = 'aA0@0 aA1@1 bH0@2 bH1@3 bH2@4 bH3@5 bH4@6'
    expect(lines['twoSections']).to eq(two), lines.inspect
    expect(lines['bound']).to eq(two), lines.inspect
    expect(lines['tracked']).to eq(two), lines.inspect
    # One declared section: the first data section, as always.
    expect(lines['oneSection']).to eq('aA0@0 aA1@1'), lines.inspect
    # The class-list shape: one section, the first data section.
    expect(lines['classList']).to eq('aA0@0 aA1@1'), lines.inspect
  end

  it 'the class-list shape over a declared list: its elements' do
    code = emit({ 'cellClasses' => ['ACell'] }, { 'rows' => { 'name' => 'rows', 'class' => '[ACellData]', 'defaultValue' => '[]' } })
    expect(code).to include('val pageSection0 = data.rows.map { it.toMap() }')
    expect(code).to include('val pageCount = pageSection0.size')
    expect(code.scan('ACellView(').size).to eq(1)
  end

  it 'no items: no page' do
    code = KjuiTools::Compose::Components::CollectionComponent.generate(
      { 'type' => 'Collection', 'id' => 'pager', 'layout' => 'horizontal', 'paging' => true, 'cellClasses' => ['ACell'] }, 1, Set.new, nil
    )
    expect(code).to include('val pageCount = 0')
    expect(code).not_to include('ACellView(')
  end

  # The bound pager's two effects are the 1.9.6 text: through 1.9.5 the
  # write-back was unguarded and cancelled the effect's own scroll
  # (kjui-pager-writeback-cancels-its-own-programmatic-scroll, below).
  it 'one declared section: the emit it always had (the faces carousel shape)' do
    node = { 'type' => 'Collection', 'id' => 'carousel', 'layout' => 'horizontal', 'paging' => true, 'items' => '@{cards}',
             'currentPage' => '@{currentPage}', 'itemSpacing' => 8, 'sections' => [{ 'cell' => 'card_cell' }],
             'cellClasses' => ['card_cell'] }
    %i[info debug warn].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    expect(KjuiTools::Compose::Components::CollectionComponent.generate(node, 1, Set.new, nil)).to eq(<<~'KOTLIN'.chomp.gsub(/^/, '    '))
      val pageCount = data.cards?.sections?.firstOrNull()?.cells?.data?.size ?: 0
      val pagerState = rememberPagerState(initialPage = (data.currentPage).coerceIn(0, (pageCount - 1).coerceAtLeast(0))) { pageCount }
      var programmaticScroll by remember { mutableStateOf(false) }
      LaunchedEffect(data.currentPage) {
          val target = data.currentPage.coerceIn(0, (pageCount - 1).coerceAtLeast(0))
          if (pagerState.currentPage != target) {
              programmaticScroll = true
              try {
                  pagerState.animateScrollToPage(target)
              } finally {
                  programmaticScroll = false
              }
          }
          if (data.currentPage != pagerState.currentPage) viewModel.updateData(mapOf("currentPage" to pagerState.currentPage))
      }
      LaunchedEffect(pagerState) {
          snapshotFlow { pagerState.currentPage }.collect { page ->
              if (!programmaticScroll) viewModel.updateData(mapOf("currentPage" to page))
          }
      }
      HorizontalPager(
          state = pagerState,
          pageSpacing = 8.dp,
          modifier = Modifier
              .testTag("carousel")
              .semantics { testTagsAsResourceId = true }
      ) { page ->
          val cellData = data.cards?.sections?.firstOrNull()?.cells
          if (cellData != null) {
              val item = cellData.data.getOrNull(page)
              if (item != null) {
                  val cellViewModel: CardCellViewModel = viewModel(key = "card_cell_page_${page}_${viewModel.hashCode()}")
                  remember(cellViewModel, item) { cellViewModel.updateData(item); item }
                  LaunchedEffect(item) {
                      cellViewModel.updateData(item)
                  }
                  CardCellView(
                      viewModel = cellViewModel,
                      modifier = Modifier.testTag("carousel_item_$page").fillMaxSize()
                  )
              }
          }
      }
    KOTLIN
  end
end

# kjui-pager-writeback-cancels-its-own-programmatic-scroll: with `currentPage`
# bound, the pager wrote every `pagerState.currentPage` back into the data —
# including the pages a ViewModel-driven `animateScrollToPage` passes through.
# That moved `data.<page>`, re-keyed `LaunchedEffect(data.<page>)` and
# cancelled the animation it was running. Measured on a device (conf_ci,
# Compose BOM 2026.09.00) through jsonui-cli 1.9.5 with the generated view of
# a bound pager: 0 -> 6 of 7 pages stopped on 5, 0 -> 2 of 3 stopped on 1,
# 0 -> 1 reached 1. With this emit: 6, 2 and 1.
#
# The write-back now stays quiet while the effect's own scroll is in flight —
# the guard KotlinJsonUI Dynamic keeps (`programmaticScroll`) — and once the
# scroll lands the page it landed on is written back. The page callback still
# hears every page, programmatic ones included, as on the Dynamic face.
#
# These arms read the emitted text: what the guard does at runtime is the
# device measurement above, which no JVM stub of Compose's effect keys can
# stand for. That the text is well-typed Kotlin is the `bound` route of the
# compile arm above.
RSpec.describe 'kjui codegen: a bound pager does not cancel its own programmatic scroll' do
  def emit(extra)
    %i[info debug warn].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    node = {
      'type' => 'Collection', 'id' => 'pager', 'layout' => 'horizontal', 'paging' => true,
      'items' => '@{rows}', 'sections' => [{ 'cell' => 'x_cell' }]
    }.merge(extra)
    KjuiTools::Compose::Components::CollectionComponent.generate(node, 1, Set.new, nil)
  end

  def block(code, opener)
    lines = code.lines
    start = lines.index { |l| l.include?(opener) } or raise "no #{opener} in the emit"
    depth = 0
    lines[start..].each_with_index do |line, i|
      depth += line.count('{') - line.count('}')
      return lines[start..start + i].join if depth.zero?
    end
    raise "#{opener} does not close"
  end

  let(:code) { emit('currentPage' => '@{page}', 'onPageChanged' => '@{onPage}') }

  it 'raises the flag around the animation and lowers it however the animation ends' do
    effect = block(code, 'LaunchedEffect(data.page)')
    expect(code).to include('var programmaticScroll by remember { mutableStateOf(false) }')
    expect(effect).to match(/programmaticScroll = true\s+try \{\s+pagerState\.animateScrollToPage\(target\)\s+\} finally \{\s+programmaticScroll = false\s+\}/)
  end

  it 'writes back only pages the user moved to, and the page a programmatic scroll lands on' do
    collector = block(code, 'LaunchedEffect(pagerState)')
    # Through 1.9.5 this line was unguarded: `viewModel.updateData(mapOf("page" to page))`.
    expect(collector).to include('if (!programmaticScroll) viewModel.updateData(mapOf("page" to page))')
    expect(collector.scan('viewModel.updateData(').size).to eq(1)

    effect = block(code, 'LaunchedEffect(data.page)').lines
    landing = effect.index { |l| l.include?('viewModel.updateData(') }
    expect(landing).not_to be_nil
    expect(effect[landing]).to include('if (data.page != pagerState.currentPage) viewModel.updateData(mapOf("page" to pagerState.currentPage))')
    # After the try/finally, not inside it: a cancelled scroll writes nothing.
    finally_at = effect.index { |l| l.include?('} finally {') }
    finally_close = (finally_at + 1...effect.size).find { |i| effect[i].strip == '}' }
    expect(finally_close).to be < landing
  end

  it 'still tells the page callback every page' do
    collector = block(code, 'LaunchedEffect(pagerState)')
    expect(collector).to include("data.onPage?.invoke(page)\n")
    expect(collector).not_to match(/programmaticScroll\)?\s*data\.onPage/)
  end

  it 'emits no flag when currentPage is not bound' do
    # Control: only the callback leg, which writes nothing back.
    unbound = emit('onPageChanged' => '@{onPage}')
    expect(unbound).not_to include('programmaticScroll')
    expect(block(unbound, 'LaunchedEffect(pagerState)')).to include('data.onPage?.invoke(page)')
  end
end
