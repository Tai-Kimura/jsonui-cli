# frozen_string_literal: true

require 'set'
require_relative '../../../lib/compose/components/collection_component'
require_relative '../../../lib/compose/generators/cell_generator'
require_relative '../../support/kotlin_compiler'

# A paging Collection's content padding pads EACH PAGE'S CELL, inside the
# page — as sjui pads the page's cell (add_paging_cell) and KotlinJsonUI
# Dynamic its page box — not the HorizontalPager's `contentPadding`, which
# narrows the page and lets the neighbouring pages show in the padding. The
# padding is the one every other Collection route takes
# (collection_stack_content_padding_expr): contentPadding / insets (1, 2 or 4
# values, [top, right, bottom, left], an array or a `|` string), plus
# insetHorizontal / insetVertical, plus the safe area, side by side; a binding
# in the insets array is its own term. The pager read no insets through
# jsonui-cli 1.9.0.
#
# The arm RUNS the emitted pager on the JVM against stubs in which
# HorizontalPager (which takes no contentPadding here: emitting one does not
# compile) composes each page in turn and each cell prints the modifier chain
# it was handed — the paddings, in order with its test tag.
RSpec.describe 'kjui codegen: a paging Collection pads each page cell by its insets' do
  def emit(extra)
    %i[info debug warn].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    node = { 'type' => 'Collection', 'id' => 'pager', 'layout' => 'horizontal', 'paging' => true, 'items' => '@{rows}',
             'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell' }] }.merge(extra)
    KjuiTools::Compose::Components::CollectionComponent.generate(node, 1, Set.new, nil)
  end

  def scaffold(class_name, letter)
    generator = KjuiTools::Compose::Generators::CellGenerator.allocate
    view = generator.send(:main_cell_content, class_name, nil, 'com.example')
    model = generator.send(:cell_viewmodel_content, class_name, 'x_cell', 'com.example')
    params = view[/fun #{class_name}View\((.*?)\)\s*\{/m, 1] or raise "no #{class_name}View in the scaffold"
    update = model[/fun updateData\((.*?)\)/, 1] or raise 'no updateData in the scaffold'
    "class #{class_name}ViewModel { var item: Map<String, Any> = emptyMap(); fun updateData(#{update}) { item = updates } }\n" \
      "@Composable fun #{class_name}View(#{params.strip}) { Pages.draw(\"#{letter}\" + viewModel.item[\"id\"] + \"[\" + modifier.log.joinToString(\" \") + \"]\") }\n"
  end

  PAGING_INSETS_STUBS = <<~KOTLIN
    annotation class Composable
    open class Modifier(val log: List<String> = emptyList()) { companion object : Modifier() }
    fun Modifier.testTag(tag: String): Modifier = Modifier(log + "tag")
    fun Modifier.fillMaxSize(): Modifier = Modifier(log + "fill")
    class SemanticsPropertyReceiver { var testTagsAsResourceId: Boolean = false }
    fun Modifier.semantics(properties: SemanticsPropertyReceiver.() -> Unit): Modifier = this
    data class Dp(val v: Float) { operator fun plus(other: Dp) = Dp(v + other.v) }
    val Int.dp: Dp get() = Dp(toFloat())
    class PaddingValues(val start: Dp = 0.dp, val top: Dp = 0.dp, val end: Dp = 0.dp, val bottom: Dp = 0.dp)
    fun PaddingValues(all: Dp): PaddingValues = PaddingValues(start = all, top = all, end = all, bottom = all)
    fun PaddingValues(horizontal: Dp, vertical: Dp): PaddingValues = PaddingValues(start = horizontal, top = vertical, end = horizontal, bottom = vertical)
    fun n(d: Dp) = d.v.toInt().toString()
    // top/right/bottom/left, right the end and left the start (left to right).
    fun Modifier.padding(p: PaddingValues): Modifier = Modifier(log + "pad(${n(p.top)}/${n(p.end)}/${n(p.bottom)}/${n(p.start)})")
    class PagerState(val pageCount: () -> Int, val currentPage: Int = 0) { suspend fun animateScrollToPage(page: Int) {} }
    fun rememberPagerState(pageCount: () -> Int): PagerState = PagerState(pageCount)
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
    class ScreenModel
    inline fun <reified T : Any> viewModel(key: String? = null): T = T::class.java.getDeclaredConstructor().newInstance()
    class CollectionDataSource(val sections: List<CollectionDataSection> = emptyList())
    class CollectionDataSection(val cells: CellData? = null) {
        class CellData(val viewName: String, val data: List<Map<String, Any>>)
    }
    class Data(val rows: CollectionDataSource? = null, val t: Int? = 20)
    fun cells(name: String, n: Int) = CollectionDataSection.CellData(name, List(n) { mapOf<String, Any>("id" to "$name$it") })
  KOTLIN

  def routes
    {
      'none' => emit({}),
      'leftThirty' => emit('insets' => [0, 0, 0, 30]),
      'oneValue' => emit('insets' => 12),
      'twoValues' => emit('insets' => [8, 4]),
      'pipeString' => emit('insets' => '8|4|12|6'),
      'contentPadding' => emit('contentPadding' => [1, 2, 3, 4]),
      'axesOnly' => emit('insetHorizontal' => 16, 'insetVertical' => 2),
      'added' => emit('insets' => [8, 4], 'insetHorizontal' => 10, 'insetVertical' => 2),
      'bound' => emit('insets' => ['@{t}', 0, 0, 0], 'insetVertical' => 4),
      'oneSection' => emit('sections' => [{ 'cell' => 'ACell' }], 'insets' => [0, 0, 0, 30])
    }
  end

  # Data sections: A0 A1 | B0.
  def program(functions)
    calls = functions.keys.map do |fn|
      "    Pages.drawn.clear(); #{fn}(Data(CollectionDataSource(listOf(CollectionDataSection(cells(\"A\", 2)), " \
        "CollectionDataSection(cells(\"B\", 1))))), ScreenModel()); println(\"#{fn} => \" + Pages.drawn.joinToString(\" \"))"
    end
    [PAGING_INSETS_STUBS, scaffold('ACell', 'a'), scaffold('BCell', 'b'),
     functions.map { |fn, body| "@Composable fun #{fn}(data: Data, viewModel: ScreenModel) {\n#{body}\n}" }.join("\n\n"),
     "fun main() {\n#{calls.join("\n")}\n}"].join("\n")
  end

  it 'every page cell carries the padding, before its test tag; the pager itself none' do
    skip "compile: #{KotlinCompiler.unavailable_reason}" if KotlinCompiler.unavailable_reason

    expect(program(routes)).to compile_as_kotlin
    run = KotlinCompiler.run(program(routes))
    expect(run.errors).to eq([])
    lines = run.output.lines.to_h { |l| l.chomp.split(' => ', 2) }
    pages = ->(pad) { %w[aA0 aA1 bB0].map { |c| "#{c}[#{pad}tag fill]" }.join(' ') }
    expect(lines['none']).to eq(pages.('')), lines.inspect
    expect(lines['leftThirty']).to eq(pages.('pad(0/0/0/30) ')), lines.inspect
    expect(lines['oneValue']).to eq(pages.('pad(12/12/12/12) ')), lines.inspect
    expect(lines['twoValues']).to eq(pages.('pad(8/4/8/4) ')), lines.inspect
    expect(lines['pipeString']).to eq(pages.('pad(8/4/12/6) ')), lines.inspect
    expect(lines['contentPadding']).to eq(pages.('pad(1/2/3/4) ')), lines.inspect
    expect(lines['axesOnly']).to eq(pages.('pad(2/16/2/16) ')), lines.inspect
    # Added side by side: [8, 4] + insetVertical 2 + insetHorizontal 10.
    expect(lines['added']).to eq(pages.('pad(10/14/10/14) ')), lines.inspect
    # The binding (t = 20) and insetVertical 4 on the top.
    expect(lines['bound']).to eq(pages.('pad(24/0/4/0) ')), lines.inspect
    expect(lines['oneSection']).to eq('aA0[pad(0/0/0/30) tag fill] aA1[pad(0/0/0/30) tag fill]'), lines.inspect
  end

  it 'the safe area is added to the insets on the page cell, not on the pager' do
    code = emit('insets' => [0, 0, 0, 30], 'contentInsetAdjustmentBehavior' => 'always')
    padding = code[/val pagePadding = (.*)$/, 1]
    expect(padding).to start_with('WindowInsets.safeDrawing.asPaddingValues().let { safe ->')
    expect(padding).to include('start = safe.calculateStartPadding(dir) + 30.dp')
    pager = code[/HorizontalPager\((.*?)\) \{ page ->/m, 1]
    expect(pager).not_to include('contentPadding')
    expect(pager).not_to include('padding')
    expect(code.scan('modifier = Modifier.padding(pagePadding).testTag("pager_item_$page").fillMaxSize()').size).to eq(2)
  end

  it 'without insets, insetHorizontal / insetVertical or a safe area the emit has no page padding' do
    code = emit('contentInsetAdjustmentBehavior' => 'never')
    expect(code).not_to include('pagePadding')
    expect(code).not_to include('contentPadding')
  end
end
