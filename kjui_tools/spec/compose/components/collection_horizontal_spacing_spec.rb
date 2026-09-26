# frozen_string_literal: true

require 'set'
require_relative '../../../lib/compose/components/collection_component'
require_relative '../../support/kotlin_compiler'

# Spacing on every horizontal Collection, one lane or many (4f ruling,
# 2026-09-26; the rule SwiftJsonUI Dynamic dde0628 and sjui codegen draw):
# along the scroll axis lineSpacing (its alias sectionSpacing), else
# itemSpacing, else 0; between lanes columnSpacing, else itemSpacing, else 0.
# Pages sit along the scroll axis. Until jsonui-cli 1.9.0 (measured on
# d975d6eb) the horizontal grid took the scroll axis from lineSpacing, else
# columnSpacing, and never spaced its lanes; the CollectionStack from
# itemSpacing, then columnSpacing, then lineSpacing; the lazy:none Row from
# columnSpacing, then itemSpacing; paging from itemSpacing, then columnSpacing.
# (Lanes themselves — LazyHorizontalGrid rows, a section break per section —
# are collection_section_grid_spec.rb's.)
RSpec.describe 'kjui codegen: horizontal spacing' do
  def emit(extra)
    %i[info debug warn].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    KjuiTools::Compose::Components::CollectionComponent.generate(
      { 'type' => 'Collection', 'id' => 'list', 'layout' => 'horizontal', 'items' => '@{rows}' }.merge(extra), 1, Set.new, nil
    )
  end

  # The value each site spaces the scroll axis and the lanes by.
  def along(code)
    code[/horizontalArrangement = Arrangement\.spacedBy\((\w+)\.dp\)/, 1] || code[/^\s*spacing = (\w+)\.dp,/, 1] ||
      code[/pageSpacing = (\w+)\.dp/, 1]
  end

  def lanes(code)
    code[/verticalArrangement = Arrangement\.spacedBy\((\w+)\.dp\)/, 1]
  end

  SPACING_ROUTES = {
    'the lane grid' => { 'columns' => 2, 'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell', 'columns' => 3 }] },
    'the CollectionStack' => { 'sections' => [{ 'cell' => 'ACell' }] },
    'the lazy:none Row' => { 'lazy' => 'none', 'sections' => [{ 'cell' => 'ACell' }] },
    'paging' => { 'paging' => true, 'sections' => [{ 'cell' => 'ACell' }] }
  }.freeze

  SPACING_ROUTES.each do |route, extra|
    it "#{route}: along the scroll axis lineSpacing, else itemSpacing — never columnSpacing" do
      expect(along(emit(extra.merge('lineSpacing' => 8, 'itemSpacing' => 5, 'columnSpacing' => 3)))).to eq('8')
      expect(along(emit(extra.merge('sectionSpacing' => 7, 'itemSpacing' => 5, 'columnSpacing' => 3)))).to eq('7')
      expect(along(emit(extra.merge('itemSpacing' => 5, 'columnSpacing' => 3)))).to eq('5')
      expect(along(emit(extra.merge('columnSpacing' => 3)))).to be_nil
    end
  end

  it 'the lane grid spaces its lanes by columnSpacing, else itemSpacing; one lane has nothing to space' do
    grid = SPACING_ROUTES['the lane grid']
    expect(lanes(emit(grid.merge('lineSpacing' => 8, 'columnSpacing' => 3, 'itemSpacing' => 5)))).to eq('3')
    expect(lanes(emit(grid.merge('lineSpacing' => 8, 'itemSpacing' => 5)))).to eq('5')
    expect(lanes(emit(grid.merge('lineSpacing' => 8)))).to be_nil
    expect(lanes(emit('columns' => '@{cols}', 'columnSpacing' => 3, 'sections' => [{ 'cell' => 'ACell' }]))).to eq('3')
    expect(lanes(emit('cellClasses' => ['RowCell'], 'itemSpacing' => 6))).to be_nil # one lane (the faces' shape)
  end

  HORIZONTAL_SPACING_STUBS = <<~KOTLIN
    annotation class Composable
    interface Modifier { companion object : Modifier }
    fun Modifier.testTag(tag: String): Modifier = this
    fun Modifier.fillMaxSize(): Modifier = this
    class SemanticsPropertyReceiver { var testTagsAsResourceId: Boolean = false }
    fun Modifier.semantics(properties: SemanticsPropertyReceiver.() -> Unit): Modifier = this
    class Dp
    val Int.dp: Dp get() = Dp()
    interface Alignment { companion object { val TopStart = object : Alignment {} } }
    class Arrangement { companion object { fun spacedBy(space: Dp): Arrangement = Arrangement() } }
    object GridCells { class Fixed(val count: Int) }
    class GridItemSpan(val span: Int)
    class LazyGridItemSpanScope { val maxLineSpan: Int = 1; val maxCurrentLineSpan: Int = 1 }
    class LazyGridScope {
        fun item(span: (LazyGridItemSpanScope.() -> GridItemSpan)? = null, content: () -> Unit) {}
        fun items(count: Int, span: (LazyGridItemSpanScope.(Int) -> GridItemSpan)? = null, itemContent: (Int) -> Unit) {}
    }
    fun LazyHorizontalGrid(rows: GridCells.Fixed, modifier: Modifier = Modifier, horizontalArrangement: Arrangement? = null,
                           verticalArrangement: Arrangement? = null, content: LazyGridScope.() -> Unit) {}
    fun Box(modifier: Modifier = Modifier, contentAlignment: Alignment = Alignment.TopStart, content: () -> Unit) {}
    fun LaunchedEffect(key1: Any?, block: suspend kotlinx.coroutines.CoroutineScope.() -> Unit) {}
    inline fun <reified T> viewModel(key: String? = null): T = throw IllegalStateException()
    class ACellViewModel { fun updateData(updates: Map<String, Any>) {} }
    class BCellViewModel { fun updateData(updates: Map<String, Any>) {} }
    @Composable fun ACellView(viewModel: ACellViewModel, modifier: Modifier = Modifier) {}
    @Composable fun BCellView(viewModel: BCellViewModel, modifier: Modifier = Modifier) {}
    class CollectionDataSource(val sections: List<CollectionDataSection> = emptyList())
    class CollectionDataSection(val cells: CellData? = null) { class CellData(val data: List<Map<String, Any>>) }
    class Data(val rows: CollectionDataSource? = null)
  KOTLIN

  it 'the lane grid with both spacings compiles' do
    code = emit(SPACING_ROUTES['the lane grid'].merge('lineSpacing' => 8, 'columnSpacing' => 3))
    expect("#{HORIZONTAL_SPACING_STUBS}\n@Composable fun host(data: Data, viewModel: Any) {\n#{code}\n}\n").to compile_as_kotlin
  end
end
