# frozen_string_literal: true

require 'set'
require_relative '../../../lib/compose/components/collection_component'
require_relative '../../support/kotlin_compiler'

# Collection.items is a CollectionDataSource or an array (4f ruling,
# 2026-09-26). A class-list Collection (cellClasses, no `sections`) whose items
# property the layout DECLARES a list — `Array`, `[T]` — is one section: every
# element with cellClasses[0], on the routes a one-section data source draws
# (paging reads declared sections only). Any other declaration, or none, is the
# canonical CollectionDataSource, emitted as before. Until jsonui-cli 1.9.0
# every class-list route read `.sections`, which a List does not have.
#
# The cells' ViewModels read a map (updateData(Map<String, Any>)): a list of
# the cell's own Data (List<RowCellData>) becomes its maps (toMap()), an
# untyped list (List<Any?>) is read element by element as maps, and a list of
# any other type is named.
RSpec.describe 'kjui codegen: a class-list Collection whose items are a declared list' do
  CLASS_LIST_ITEMS_ROUTES = {
    'lazy vertical' => {}, 'lazy grid' => { 'columns' => 2 }, 'lazy horizontal' => { 'layout' => 'horizontal' },
    'flow' => { 'layout' => 'flow' }, 'lazy:none' => { 'lazy' => 'none' }, 'lazy:none grid' => { 'lazy' => 'none', 'columns' => 2 },
    'lazy:none horizontal' => { 'lazy' => 'none', 'layout' => 'horizontal' }, 'wrapContent' => { 'height' => 'wrapContent' },
    'paging' => { 'layout' => 'horizontal', 'paging' => true }
  }.freeze

  # declared => [data definition, the list expression, the Kotlin property]
  CLASS_LIST_ITEMS_DECLARATIONS = {
    '[RowCellData] = []' => [{ 'name' => 'rows', 'class' => '[RowCellData]', 'defaultValue' => '[]' },
                             'data.rows.map { it.toMap() }', 'val rows: List<RowCellData> = emptyList()'],
    'Array (no default)' => [{ 'name' => 'rows', 'class' => 'Array' },
                             'data.rows.orEmpty().mapNotNull { it as? Map<String, Any> }', 'val rows: List<Any?>? = null']
  }.freeze

  def emit(extra, definition)
    %i[info debug].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = definition ? { definition['name'] => definition } : {}
    KjuiTools::Compose::Components::CollectionComponent.generate(
      { 'type' => 'Collection', 'id' => 'list', 'cellClasses' => ['row_cell'], 'items' => '@{rows}' }.merge(extra), 1, Set.new, nil
    )
  ensure
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  CLASS_LIST_ITEMS_DECLARATIONS.each do |declared, (definition, list, _kotlin)|
    CLASS_LIST_ITEMS_ROUTES.each do |route, extra|
      it "items #{declared}, #{route}: #{route == 'paging' ? 'nothing' : 'the declared list, one section'}, no `.sections`" do
        allow(KjuiTools::Core::Logger).to receive(:warn)
        code = emit(extra, definition)
        if route == 'paging'
          expect(code).not_to include('RowCellView(')
        else
          expect(code.scan('RowCellView(').size).to eq(1), code
          expect(code).to include(list)
          expect(code).to include('val sectionIndex = 0').or include('Triple(0, cellIndex, cellData)')
        end
        expect(code).not_to include('.sections')
      end
    end
  end

  it 'a CollectionDataSource, or no declaration, reads the data sections as before' do
    allow(KjuiTools::Core::Logger).to receive(:warn)
    [{ 'name' => 'rows', 'class' => 'CollectionDataSource' }, nil].each do |definition|
      expect(emit({}, definition)).to include('.forEachIndexed { sectionIndex, section ->'), definition.inspect
    end
  end

  it 'names a list of another type: its elements are no map, so its cells draw with no data' do
    said = []
    allow(KjuiTools::Core::Logger).to receive(:warn) { |m| said << m }
    code = emit({}, { 'name' => 'rows', 'class' => '[Booking]', 'defaultValue' => '[]' })
    expect(said.join).to include("items 'rows' is a list of Booking; a cell reads its own RowCellData or a map")
    expect(code).to include('data.rows.mapNotNull { it as? Map<String, Any> }')
  end

  CLASS_LIST_ITEMS_STUBS = <<~KOTLIN
    annotation class Composable
    interface Modifier { companion object : Modifier }
    fun Modifier.testTag(tag: String): Modifier = this
    fun Modifier.fillMaxWidth(): Modifier = this
    fun Modifier.fillMaxSize(): Modifier = this
    fun Modifier.verticalScroll(state: ScrollState): Modifier = this
    fun Modifier.wrapContentHeight(align: Alignment.Vertical = Alignment.Top, unbounded: Boolean = false): Modifier = this
    fun Modifier.height(value: Dp): Modifier = this
    fun Modifier.requiredHeight(value: Dp): Modifier = this
    fun Modifier.fillMaxHeight(): Modifier = this
    class ScrollState
    fun rememberScrollState(): ScrollState = ScrollState()
    class SemanticsPropertyReceiver { var testTagsAsResourceId: Boolean = false }
    fun Modifier.semantics(properties: SemanticsPropertyReceiver.() -> Unit): Modifier = this
    class Dp
    val Int.dp: Dp get() = Dp()
    interface Alignment { interface Vertical; companion object { val TopStart = object : Alignment {}; val Top = object : Vertical {} } }
    class Arrangement { companion object { fun spacedBy(space: Dp): Arrangement = Arrangement() } }
    object GridCells { class Fixed(val count: Int) }
    class GridItemSpan(val span: Int)
    class LazyGridItemSpanScope { val maxLineSpan: Int = 1; val maxCurrentLineSpan: Int = 1 }
    class LazyGridScope {
        fun item(span: (LazyGridItemSpanScope.() -> GridItemSpan)? = null, content: () -> Unit) {}
        fun items(count: Int, itemContent: (Int) -> Unit) {}
    }
    fun LazyVerticalGrid(columns: GridCells.Fixed, modifier: Modifier = Modifier, content: LazyGridScope.() -> Unit) {}
    fun LazyHorizontalGrid(rows: GridCells.Fixed, modifier: Modifier = Modifier, content: LazyGridScope.() -> Unit) {}
    fun Box(modifier: Modifier = Modifier, contentAlignment: Alignment = Alignment.TopStart, content: () -> Unit) {}
    class ColumnScope
    class RowScope { fun Modifier.weight(weight: Float): Modifier = this }
    fun Column(modifier: Modifier = Modifier, verticalArrangement: Arrangement? = null, content: ColumnScope.() -> Unit) {}
    fun Row(modifier: Modifier = Modifier, horizontalArrangement: Arrangement? = null, content: RowScope.() -> Unit) {}
    fun Spacer(modifier: Modifier) {}
    fun FlowRow(modifier: Modifier = Modifier, horizontalArrangement: Arrangement, verticalArrangement: Arrangement, content: () -> Unit) {}
    class PagerState
    fun rememberPagerState(pageCount: () -> Int): PagerState = PagerState()
    fun HorizontalPager(state: PagerState, modifier: Modifier = Modifier, pageContent: (Int) -> Unit) {}
    fun LaunchedEffect(key1: Any?, block: suspend kotlinx.coroutines.CoroutineScope.() -> Unit) {}
    inline fun <reified T> viewModel(key: String? = null): T = throw IllegalStateException()
    class RowCellViewModel { fun updateData(updates: Map<String, Any>) {} }
    @Composable fun RowCellView(viewModel: RowCellViewModel, modifier: Modifier = Modifier) {}
    data class RowCellData(val title: String = "") { fun toMap(): MutableMap<String, Any> = mutableMapOf("title" to title) }
  KOTLIN

  it 'every route compiles against List<RowCellData> and List<Any?>?' do
    allow(KjuiTools::Core::Logger).to receive(:warn)
    functions = CLASS_LIST_ITEMS_DECLARATIONS.each_with_index.flat_map do |(declared, (definition, _list, kotlin)), d|
      ["class Data#{d}(#{kotlin})"] + CLASS_LIST_ITEMS_ROUTES.each_with_index.map do |(route, extra), r|
        "// #{declared}, #{route}\n@Composable fun route#{d}_#{r}(data: Data#{d}, viewModel: Any) {\n#{emit(extra, definition)}\n}"
      end
    end
    expect("#{CLASS_LIST_ITEMS_STUBS}\n#{functions.join("\n\n")}\n").to compile_as_kotlin
  end
end
