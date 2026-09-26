# frozen_string_literal: true

require 'open3'
require 'set'
require 'tmpdir'
require_relative '../../../lib/compose/components/collection_component'
require_relative '../../../lib/compose/generators/cell_generator'
require_relative '../../support/kotlin_compiler'

# Declared `sections` of more than one column: a grid per section on every
# route — each section's cells start a row of their own, as sjui codegen and
# SwiftJsonUI Dynamic draw them.
#
# Until 1.8.121 (measured on d084cfb2, 2026-09-26) the lazy / eager routes held
# every section in one LazyVerticalGrid, so section 2 continued section 1's
# last row unless a header item sat between; lazy:none and wrapContent drew one
# cell per row.
#
# The arm RUNS the emitted code. Compiled with kotlinc and run on the JVM
# against stubs that lay items out by LazyGrid's line rule (an item whose span
# does not fit what the line has left starts the next line;
# `maxCurrentLineSpan` is what the line has left — the two members of
# LazyGridItemSpanScope, javap'd from foundation-android 1.12.1) and a Row /
# Column that record what they hold. The rule is a transcription, not the
# Compose layout: a green says the emitted builder asks for these lines.
RSpec.describe 'kjui codegen: a grid per section' do
  def emit(node)
    %i[info debug warn].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    KjuiTools::Compose::Components::CollectionComponent.generate(node, 1, Set.new, nil)
  end

  def node(extra = {})
    { 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'columns' => 2,
      'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell', 'header' => 'BHead' }] }.merge(extra)
  end

  def scaffold(class_name, letter)
    generator = KjuiTools::Compose::Generators::CellGenerator.allocate
    view = generator.send(:main_cell_content, class_name, nil, 'com.example')
    model = generator.send(:cell_viewmodel_content, class_name, 'x_cell', 'com.example')
    params = view[/fun #{class_name}View\((.*?)\)\s*\{/m, 1] or raise "no #{class_name}View in the scaffold"
    update = model[/fun updateData\((.*?)\)/, 1] or raise "no updateData in the scaffold"
    "class #{class_name}ViewModel { fun updateData(#{update}) {} }\n" \
      "@Composable fun #{class_name}View(#{params.strip}) { Layout.draw(\"#{letter}\" + ((modifier as? Tagged)?.tag?.substringAfterLast('_') ?: \"\")) }\n"
  end

  SECTION_GRID_STUBS = <<~KOTLIN
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
    fun Modifier.wrapContentHeight(): Modifier = this
    class Arrangement { companion object { fun spacedBy(space: Dp): Arrangement = Arrangement() } }
    object GridCells { class Fixed(val count: Int) }
    class GridItemSpan(val span: Int)
    class LazyGridItemSpanScope(val maxLineSpan: Int, val maxCurrentLineSpan: Int)

    // What a laid-out grid holds: one string per line; per cell its letter and
    // the index its test tag carries, `_` for an empty item, and a `.` for
    // each span unit beyond 1.
    object Layout {
        val lines = mutableListOf<StringBuilder>()
        var row: StringBuilder? = null
        fun draw(letter: String) { (row ?: StringBuilder().also { lines += it }).append(letter) }
        fun dump(): String = lines.joinToString("|")
    }
    class LazyGridScope(private val lineSpan: Int) {
        private var used = 0
        private var line: StringBuilder? = null
        private fun place(span: Int, mark: String) {
            if (line == null || used + span > lineSpan) { line = StringBuilder().also { Layout.lines += it }; used = 0 }
            line!!.append(mark).append(".".repeat(span - 1))
            used += span
            if (used == lineSpan) line = null
        }
        private fun left() = if (line == null) lineSpan else lineSpan - used
        fun item(span: (LazyGridItemSpanScope.() -> GridItemSpan)? = null, content: () -> Unit) {
            place(span?.invoke(LazyGridItemSpanScope(lineSpan, left()))?.span ?: 1, "_")
        }
        fun items(count: Int, key: ((Int) -> Any)? = null, span: (LazyGridItemSpanScope.(Int) -> GridItemSpan)? = null, itemContent: (Int) -> Unit) {
            repeat(count) { i ->
                Layout.row = null
                val before = Layout.lines.size
                itemContent(i) // draws the cell's letter into a line of its own; moved into the grid line
                val letter = Layout.lines.removeAt(before).toString()
                place(span?.invoke(LazyGridItemSpanScope(lineSpan, left()), i)?.span ?: 1, letter)
            }
        }
    }
    fun LazyVerticalGrid(columns: GridCells.Fixed, modifier: Modifier = Modifier, content: LazyGridScope.() -> Unit) {
        LazyGridScope(columns.count).content()
    }
    // A horizontal grid's lines are its columns; the rule is the same.
    fun LazyHorizontalGrid(rows: GridCells.Fixed, modifier: Modifier = Modifier, content: LazyGridScope.() -> Unit) {
        LazyGridScope(rows.count).content()
    }
    fun Box(modifier: Modifier = Modifier, contentAlignment: Alignment = Alignment.TopStart, content: () -> Unit) { content() }
    class ColumnScope
    class RowScope { fun Modifier.weight(weight: Float): Modifier = this }
    fun Column(modifier: Modifier = Modifier, verticalArrangement: Arrangement? = null, content: ColumnScope.() -> Unit) { ColumnScope().content() }
    fun Row(modifier: Modifier = Modifier, horizontalArrangement: Arrangement? = null, content: RowScope.() -> Unit) {
        val row = StringBuilder().also { Layout.lines += it }
        Layout.row = row
        RowScope().content()
        Layout.row = null
    }
    fun Spacer(modifier: Modifier) { Layout.row?.append("_") }
    fun LaunchedEffect(key1: Any?, block: suspend kotlinx.coroutines.CoroutineScope.() -> Unit) {}
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
    class Data(val rows: CollectionDataSource? = null, val cols: Int = 2)
    fun cells(name: String, n: Int) = CollectionDataSection.CellData(name, List(n) { mapOf<String, Any>("i" to it) })
  KOTLIN

  # case name => [Kotlin sections, the lines expected]
  SECTION_GRID_CASES = {
    'section 1 ends a row part filled' => ['listOf(CollectionDataSection(cells = cells("A", 3)), CollectionDataSection(cells = cells("B", 2)))'],
    'section 1 fills its last row' => ['listOf(CollectionDataSection(cells = cells("A", 2)), CollectionDataSection(cells = cells("B", 2)))'],
    'section 2 has a header' => ['listOf(CollectionDataSection(cells = cells("A", 3)), CollectionDataSection(header = CollectionDataSection.HeaderFooterData("H", emptyMap()), cells = cells("B", 2)))']
  }.freeze

  # Each (function name => emitted body) against each case, with a main that
  # prints `name case => lines`.
  def program(functions)
    calls = functions.keys.product(SECTION_GRID_CASES.keys).map do |fn, name|
      "    Layout.lines.clear(); #{fn}(Data(CollectionDataSource(#{SECTION_GRID_CASES[name][0]})), Any()); println(\"#{fn} #{name} => \" + Layout.dump())"
    end
    [SECTION_GRID_STUBS, scaffold('ACell', 'A'), scaffold('BCell', 'B'), scaffold('BHead', 'H'),
     functions.map { |fn, body| "@Composable fun #{fn}(data: Data, viewModel: Any) {\n#{body}\n}" }.join("\n\n"),
     "fun main() {\n#{calls.join("\n")}\n}"].join("\n")
  end

  def routes
    {
      'lazy' => emit(node),
      'eager' => emit(node('lazy' => 'eager')),
      'none' => emit(node('lazy' => 'none')),
      'wrap' => emit(node('height' => 'wrapContent')),
      'horizontal' => emit(node('layout' => 'horizontal')),
      'binding' => emit(node('columns' => '@{cols}')),
      'bindingNone' => emit(node('columns' => '@{cols}', 'lazy' => 'none')),
      'ownColumns' => emit(node('columns' => nil, 'lazy' => 'none',
                                'sections' => [{ 'cell' => 'ACell', 'columns' => 2 }, { 'cell' => 'BCell', 'header' => 'BHead', 'columns' => 2 }]).compact),
      'lcm' => emit(node('columns' => nil,
                         'sections' => [{ 'cell' => 'ACell', 'columns' => 2 }, { 'cell' => 'BCell', 'columns' => 3 }]).compact)
    }
  end

  # Compiles and runs the program; `name case => lines`.
  def run_emitted(functions)
    skip "compile: #{KotlinCompiler.unavailable_reason}" if KotlinCompiler.unavailable_reason

    source = program(functions)
    stdlib = KotlinCompiler.newest('org.jetbrains.kotlin', 'kotlin-stdlib')
    coroutines = KotlinCompiler.newest('org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm')
    reflect = KotlinCompiler.newest('org.jetbrains.kotlin', 'kotlin-reflect')
    annotations = KotlinCompiler.newest('org.jetbrains', 'annotations')
    Dir.mktmpdir('kjui_run') do |dir|
      File.write(File.join(dir, 'Emitted.kt'), source)
      compiler_cp = [KotlinCompiler.compiler_jar, stdlib, reflect, coroutines, annotations,
                     KotlinCompiler.newest('org.jetbrains.intellij.deps', 'trove4j')].compact.join(':')
      out, status = Open3.capture2e(KotlinCompiler.java_bin, '-cp', compiler_cp, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
                                    '-no-stdlib', '-cp', [stdlib, reflect, annotations, coroutines].join(':'),
                                    '-d', File.join(dir, 'out'), File.join(dir, 'Emitted.kt'))
      errors = out.lines.grep(/error:/)
      raise "the emitted code did not compile:\n#{errors.join}\n#{source}" unless status.success? && errors.empty?

      run, status = Open3.capture2e(KotlinCompiler.java_bin, '-cp', [File.join(dir, 'out'), stdlib, coroutines].join(':'), 'EmittedKt')
      raise "the emitted code did not run:\n#{run}" unless status.success?

      run.lines.to_h { |l| k, v = l.chomp.split(' => ', 2); [k, v] }
    end
  end

  it 'every route compiles (the compile arm; the run below compiles it again to run it)' do
    expect(program(routes)).to compile_as_kotlin
  end

  it 'lays each section out from a row of its own, on every route, adding no empty row' do
    lines = run_emitted(routes)
    %w[lazy eager horizontal binding].each do |route|
      expect(lines["#{route} section 1 ends a row part filled"]).to eq('A0A1|A2_|B0B1'), lines.inspect
      expect(lines["#{route} section 1 fills its last row"]).to eq('A0A1|B0B1'), lines.inspect
      expect(lines["#{route} section 2 has a header"]).to eq('A0A1|A2|_.|B0B1'), lines.inspect
    end
    %w[none wrap ownColumns bindingNone].each do |route|
      expect(lines["#{route} section 1 ends a row part filled"]).to eq('A0A1|A2_|B0B1'), lines.inspect
      expect(lines["#{route} section 1 fills its last row"]).to eq('A0A1|B0B1'), lines.inspect
      expect(lines["#{route} section 2 has a header"]).to eq('A0A1|A2_|H|B0B1'), lines.inspect
    end
    # Columns 2 and 3 in one grid of 6: section 1's cells span 3, section 2's
    # 2 — the fill is counted in grid units, so two cells of 3 fill a row.
    expect(lines['lcm section 1 ends a row part filled']).to eq('A0..A1..|A2.._..|B0.B1.'), lines.inspect
    expect(lines['lcm section 1 fills its last row']).to eq('A0..A1..|B0.B1.'), lines.inspect
  end

  it 'a single section is emitted as it was (nothing to separate)' do
    code = emit(node('sections' => [{ 'cell' => 'ACell' }]))
    expect(code).not_to include('gridLineFill')
    expect(code).not_to include('maxCurrentLineSpan')
  end

  it 'a one-column section on the composable route keeps one cell per row' do
    code = emit(node('columns' => nil, 'lazy' => 'none', 'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell', 'columns' => 2 }]).compact)
    expect(code.scan('.chunked(').size).to eq(1)
  end
end
