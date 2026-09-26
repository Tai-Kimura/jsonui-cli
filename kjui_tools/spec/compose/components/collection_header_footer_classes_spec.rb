# frozen_string_literal: true

require 'set'
require 'tmpdir'
require_relative '../../../lib/compose/components/collection_component'
require_relative '../../../lib/compose/generators/cell_generator'
require_relative '../../support/kotlin_compiler'

# `headerClasses` / `footerClasses` on the Compose codegen: the header view
# once before the cells and the footer view once after, full width — what
# sjui draws. Until 1.8.121 both names were read into locals and never used:
# the declared attributes drew nothing on Android (measured on b53f59da,
# 2026-09-26; ticket collection-attributes-declared-but-not-drawn-on-some-paths).
#
# Compiled against the view signature `kjui g cell` scaffolds, read from the
# generator's own template (CellGenerator#create_main_cell_template) rather
# than transcribed here. Stubs for the Compose names: a green says
# "well-typed against these stubs", not "valid Compose".
RSpec.describe 'kjui codegen: headerClasses / footerClasses' do
  def emit(node)
    %i[info debug warn].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    KjuiTools::Compose::Components::CollectionComponent.generate(node, 1, Set.new, nil)
  end

  # `fun XView(<params>)` as the cell scaffold writes it, with an empty body.
  def scaffold_stub(class_name)
    Dir.mktmpdir('kjui_cell') do |dir|
      path = File.join(dir, "#{class_name}View.kt")
      KjuiTools::Compose::Generators::CellGenerator.allocate.send(
        :create_main_cell_template, path, class_name, 'x_cell', '', 'com.example'
      )
      params = File.read(path)[/fun #{class_name}View\((.*?)\)\s*\{/m, 1]
      raise "no #{class_name}View in the scaffold" unless params

      "class #{class_name}ViewModel\n@Composable fun #{class_name}View(#{params.strip}) {}\n"
    end
  end

  STUBS = <<~KOTLIN
    annotation class Composable
    open class Modifier { companion object : Modifier() }
    fun Modifier.testTag(tag: String): Modifier = this
    fun Modifier.fillMaxWidth(): Modifier = this
    class SemanticsPropertyReceiver { var testTagsAsResourceId: Boolean = false }
    fun Modifier.semantics(properties: SemanticsPropertyReceiver.() -> Unit): Modifier = this
    object GridCells { class Fixed(val count: Int) }
    class GridItemSpan(val span: Int)
    class LazyGridItemSpanScope { val maxLineSpan: Int = 1 }
    class LazyGridScope {
        fun item(span: (LazyGridItemSpanScope.() -> GridItemSpan)? = null, content: () -> Unit) {}
        fun items(count: Int, itemContent: (Int) -> Unit) {}
    }
    fun LazyVerticalGrid(columns: GridCells.Fixed, modifier: Modifier = Modifier, content: LazyGridScope.() -> Unit) {}
    inline fun <reified T> viewModel(key: String? = null): T = throw IllegalStateException()
    class Data(val rows: Map<String, List<Any>>? = null)
  KOTLIN

  let(:node) do
    { 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}',
      'headerClasses' => ['header_cell'], 'footerClasses' => ['FooterCell'] }
  end

  it 'draws the header view once before and the footer view once after, full width' do
    code = emit(node)
    header = code.index('HeaderCellView(')
    footer = code.index('FooterCellView(')
    expect(header).not_to be_nil, code
    expect(footer).not_to be_nil, code
    expect(header).to be < footer
    expect(code.scan('item(span = { GridItemSpan(maxLineSpan) })').size).to eq(2)
    expect(code).not_to include('nothing rendered')
  end

  it 'compiles against the view signature the cell scaffold writes' do
    source = "#{STUBS}\n#{scaffold_stub('HeaderCell')}#{scaffold_stub('FooterCell')}\n" \
             "@Composable fun host(data: Data, viewModel: Any) {\n#{emit(node)}\n}\n"
    expect(source).to compile_as_kotlin
  end

  it 'draws nothing for neither (the control: the declaration-faithful empty grid is unchanged)' do
    expect(emit(node.reject { |k, _| %w[headerClasses footerClasses].include?(k) })).to include('nothing rendered')
  end
end
