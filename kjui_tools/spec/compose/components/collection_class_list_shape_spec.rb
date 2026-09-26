# frozen_string_literal: true

require 'set'
require 'tmpdir'
require_relative '../../../lib/compose/components/collection_component'
require_relative '../../../lib/compose/generators/cell_generator'
require_relative '../../support/kotlin_compiler'

# The class-list Collection — `cellClasses` (with `headerClasses` /
# `footerClasses`), `items` and no `sections` — on the Compose codegen, route
# by route, against sjui codegen's route table: the cells come from the
# data's own sections (CollectionDataSource), every one of them on the
# vertical routes and the first on the horizontal and flow routes; a header
# is drawn before them and a footer after on the vertical routes only, with
# or without items; paging draws nothing.
#
# Until 1.8.121 (measured on 8e4ea3ea, 2026-09-26) only the lazy grid drew
# this shape, as `data.rows?.get("<cellClass>")` through `<cellClass>View(data
# = …)` — neither compiles against CollectionDataSource and the cell scaffold
# — with a no-items branch using an undeclared `item`; the horizontal grid
# drew a header and footer; flow, lazy:none and wrapContent drew nothing.
# Ticket collection-attributes-declared-but-not-drawn-on-some-paths.
#
# Compiled against the view and ViewModel signatures `kjui g cell` scaffolds,
# read from the generator's own templates (CellGenerator#main_cell_content / #cell_viewmodel_content), and a
# CollectionDataSource transcribed from KotlinJsonUI's
# com.kotlinjsonui.data.CollectionDataSection.kt (fields only; a
# transcription, not a compile against the library). Stubs for the Compose
# names: a green says "well-typed against these stubs", not "valid Compose".
RSpec.describe 'kjui codegen: the class-list Collection (cellClasses, items, no sections)' do
  CLASS_LIST_BASE = {
    'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}',
    'cellClasses' => ['row_cell'], 'headerClasses' => ['HeadCell'], 'footerClasses' => ['FootCell']
  }.freeze

  # route => [attributes, where the cells come from, header / footer drawn]
  CLASS_LIST_ROUTES = {
    'lazy, vertical, 1 column' => [{}, :every, true],
    'lazy, grid' => [{ 'columns' => 2 }, :every, true],
    'lazy, horizontal' => [{ 'layout' => 'horizontal' }, :first, false],
    'flow' => [{ 'layout' => 'flow' }, :first, false],
    'lazy:none, vertical' => [{ 'lazy' => 'none' }, :every, true],
    'lazy:none, grid' => [{ 'lazy' => 'none', 'columns' => 2 }, :every, true],
    'lazy:none, horizontal' => [{ 'lazy' => 'none', 'layout' => 'horizontal' }, :first, false],
    'wrapContent height, vertical' => [{ 'height' => 'wrapContent' }, :every, true],
    'wrapContent height, grid' => [{ 'height' => 'wrapContent', 'columns' => 2 }, :every, true],
    'paging' => [{ 'layout' => 'horizontal', 'paging' => true }, :nothing, false]
  }.freeze

  def emit(node, imports = Set.new)
    %i[info debug warn].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    KjuiTools::Compose::Components::CollectionComponent.generate(node, 1, imports, nil)
  end

  def scaffold(class_name)
    generator = KjuiTools::Compose::Generators::CellGenerator.allocate
    view = generator.send(:main_cell_content, class_name, nil, 'com.example')
    model = generator.send(:cell_viewmodel_content, class_name, 'x_cell', 'com.example')
    params = view[/fun #{class_name}View\((.*?)\)\s*\{/m, 1] or raise "no #{class_name}View in the scaffold"
    update = model[/fun updateData\((.*?)\)/, 1] or raise "no updateData in the #{class_name}ViewModel scaffold"
    "class #{class_name}ViewModel { fun updateData(#{update}) {} }\n" \
      "@Composable fun #{class_name}View(#{params.strip}) {}\n"
  end

  CLASS_LIST_STUBS = <<~KOTLIN
    annotation class Composable
    interface Modifier { companion object : Modifier }
    fun Modifier.testTag(tag: String): Modifier = this
    fun Modifier.fillMaxWidth(): Modifier = this
    fun Modifier.fillMaxSize(): Modifier = this
    class SemanticsPropertyReceiver { var testTagsAsResourceId: Boolean = false }
    fun Modifier.semantics(properties: SemanticsPropertyReceiver.() -> Unit): Modifier = this
    class Dp
    val Int.dp: Dp get() = Dp()
    interface Alignment {
        interface Vertical
        companion object {
            val TopStart = object : Alignment {}
            val Top = object : Vertical {}
        }
    }
    fun Modifier.wrapContentHeight(align: Alignment.Vertical = Alignment.Top, unbounded: Boolean = false): Modifier = this
    class Arrangement { companion object { fun spacedBy(space: Dp): Arrangement = Arrangement() } }
    object GridCells { class Fixed(val count: Int) }
    class GridItemSpan(val span: Int)
    class LazyGridItemSpanScope { val maxLineSpan: Int = 1 }
    class LazyGridScope {
        fun item(span: (LazyGridItemSpanScope.() -> GridItemSpan)? = null, content: () -> Unit) {}
        fun items(count: Int, itemContent: (Int) -> Unit) {}
    }
    fun LazyVerticalGrid(columns: GridCells.Fixed, modifier: Modifier = Modifier, content: LazyGridScope.() -> Unit) {}
    fun LazyHorizontalGrid(rows: GridCells.Fixed, modifier: Modifier = Modifier, content: LazyGridScope.() -> Unit) {}
    fun Box(modifier: Modifier = Modifier, contentAlignment: Alignment = Alignment.TopStart, content: () -> Unit) {}
    class ColumnScope
    class RowScope { fun Modifier.weight(weight: Float): Modifier = this }
    fun Column(modifier: Modifier = Modifier, content: ColumnScope.() -> Unit) {}
    fun Row(modifier: Modifier = Modifier, horizontalArrangement: Arrangement? = null, content: RowScope.() -> Unit) {}
    fun Spacer(modifier: Modifier) {}
    fun FlowRow(modifier: Modifier = Modifier, horizontalArrangement: Arrangement, verticalArrangement: Arrangement, content: () -> Unit) {}
    class PagerState
    fun rememberPagerState(pageCount: () -> Int): PagerState = PagerState()
    fun HorizontalPager(state: PagerState, modifier: Modifier = Modifier, pageContent: (Int) -> Unit) {}
    fun LaunchedEffect(key1: Any?, block: suspend kotlinx.coroutines.CoroutineScope.() -> Unit) {}
    inline fun <reified T> viewModel(key: String? = null): T = throw IllegalStateException()
    class CollectionDataSource(val sections: List<CollectionDataSection> = emptyList())
    class CollectionDataSection(
        val header: HeaderFooterData? = null,
        val footer: HeaderFooterData? = null,
        val cells: CellData? = null
    ) {
        class CellData(val viewName: String, val data: List<Map<String, Any>>)
        class HeaderFooterData(val viewName: String, val data: Map<String, Any>)
    }
    class NullableData(val rows: CollectionDataSource? = null)
    class PlainData(val rows: CollectionDataSource = CollectionDataSource())
  KOTLIN

  def placement(code)
    {
      every: code.include?('.forEachIndexed { sectionIndex, section ->') || code.include?('.flatMapIndexed { sectionIndex, section ->'),
      first: code.include?('.firstOrNull()?.cells'),
      cells: code.scan('RowCellView(').size,
      header: code.index('HeadCellView('),
      footer: code.index('FootCellView('),
      cell_at: code.index('RowCellView(')
    }
  end

  CLASS_LIST_ROUTES.each do |route, (attributes, source, edges)|
    it "#{route}: cells from #{source == :every ? 'every data section' : source == :first ? 'the first data section' : 'nowhere'}, " \
       "#{edges ? 'header before and footer after' : 'no header or footer'}" do
      imports = Set.new
      code = emit(CLASS_LIST_BASE.merge(attributes), imports)
      at = placement(code)
      case source
      when :every
        expect([at[:every], at[:first], at[:cells]]).to eq([true, false, 1]), code
      when :first
        expect([at[:every], at[:first], at[:cells]]).to eq([false, true, 1]), code
      else
        expect(at[:cells]).to eq(0), code
      end
      if edges
        expect(at[:header]).to be < at[:cell_at]
        expect(at[:cell_at]).to be < at[:footer]
      else
        expect([at[:header], at[:footer]]).to eq([nil, nil]), code
      end
      if source != :nothing
        # Each cell its own ViewModel: keyed by the data section as well as
        # the cell, or two sections' first cells would share one.
        expect(code).to include('viewModel(key = "RowCell_cell_${sectionIndex}_${cellIndex}_')
      end
      # A grid lays the cells in rows of `columns`: the lazy grid's own
      # column count, or rows of that many on the composable routes.
      expect(code).to match(/GridCells\.Fixed\(2\)|\.chunked\(2\)/), code if attributes['columns'] == 2
      # A short last row keeps its cells at a column's width: the missing
      # cells are weighted spacers, not left for the others to fill.
      expect(code).to include('Spacer(modifier = Modifier.weight(1f))') if code.include?('.chunked(')
      expect(code).not_to include('.get("')
      expect(code).not_to match(/\bdata = /)
      drawn = [('row_cell' unless source == :nothing), ('HeadCell' if edges), ('FootCell' if edges)].compact
      expect(imports.select { |i| i.to_s.start_with?('cell:') }.map { |i| i.sub('cell:', '') }).to match_array(drawn)
    end
  end

  it 'a header and a footer with no items are still drawn, and no cell is' do
    CLASS_LIST_ROUTES.each do |route, (attributes, _source, edges)|
      code = emit(CLASS_LIST_BASE.merge(attributes).reject { |k, _| k == 'items' })
      at = placement(code)
      expect([at[:cells], !at[:header].nil?, !at[:footer].nil?]).to eq([0, edges, edges]), "#{route}\n#{code}"
      expect(code).not_to match(/items\(0\)|\bitem\]|= item\b/), route
    end
  end

  it 'every route compiles against the cell scaffold and CollectionDataSource, nullable or not' do
    functions = []
    CLASS_LIST_ROUTES.each_with_index do |(route, (attributes, _source, _edges)), index|
      functions << "// #{route}\n@Composable fun route#{index}(data: NullableData, viewModel: Any) {\n#{emit(CLASS_LIST_BASE.merge(attributes))}\n}"
      functions << "// #{route}, no items\n@Composable fun route#{index}NoItems(data: NullableData, viewModel: Any) {\n" \
                   "#{emit(CLASS_LIST_BASE.merge(attributes).reject { |k, _| k == 'items' })}\n}"
    end
    allow(KjuiTools::Compose::Helpers::ResourceResolver).to receive(:generated_property_nullable?).and_return(false)
    CLASS_LIST_ROUTES.each_with_index do |(route, (attributes, _source, _edges)), index|
      functions << "// #{route}, a non-null property\n@Composable fun route#{index}Plain(data: PlainData, viewModel: Any) {\n" \
                   "#{emit(CLASS_LIST_BASE.merge(attributes))}\n}"
    end
    source = "#{CLASS_LIST_STUBS}\n#{scaffold('RowCell')}#{scaffold('HeadCell')}#{scaffold('FootCell')}\n#{functions.join("\n\n")}\n"
    expect(source).to compile_as_kotlin
  end
end
