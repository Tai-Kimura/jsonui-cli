# frozen_string_literal: true

require 'open3'
require 'set'
require 'tmpdir'
require_relative '../../../lib/compose/components/collection_component'
require_relative '../../../lib/compose/generators/cell_generator'
require_relative '../../support/kotlin_compiler'

# A flow Collection of two or more sections: a flow per section — each
# section's cells wrap in a FlowRow of their own, one under the other, as
# sjui draws a FlowLayout per section in a VStack. One FlowRow held every
# section, so section 2 continued section 1's last row (measured on 6bdb6aba,
# 2026-09-26). Ticket collection-attributes-declared-but-not-drawn-on-some-paths.
#
# The arm RUNS the emitted code: compiled by kotlinc and run on the JVM
# against stubs in which each FlowRow is one wrapping region (a line of the
# printout) and each cell prints its letter and the index its test tag
# carries. A green says the emitted builder asks for these regions, not how
# Compose wraps them.
RSpec.describe 'kjui codegen: a flow per section' do
  def emit(extra = {})
    %i[info debug warn].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    node = { 'type' => 'Collection', 'id' => 'list', 'layout' => 'flow', 'items' => '@{rows}',
             'lineSpacing' => 6, 'columnSpacing' => 4,
             'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell' }] }.merge(extra)
    KjuiTools::Compose::Components::CollectionComponent.generate(node, 1, Set.new, nil)
  end

  # A header or footer (`edge: true`) also prints how it was placed: `~` when
  # the view itself was handed fillMaxWidth (a fixed-width root then fills or
  # centres itself in the row), `!` when it is not in a full-width row.
  def scaffold(class_name, letter, edge: false)
    generator = KjuiTools::Compose::Generators::CellGenerator.allocate
    view = generator.send(:main_cell_content, class_name, nil, 'com.example')
    model = generator.send(:cell_viewmodel_content, class_name, 'x_cell', 'com.example')
    params = view[/fun #{class_name}View\((.*?)\)\s*\{/m, 1] or raise "no #{class_name}View in the scaffold"
    update = model[/fun updateData\((.*?)\)/, 1] or raise 'no updateData in the scaffold'
    placed = edge ? ' + (if (modifier is Wide) "~" else "") + (if (Layout.fullRow) "" else "!")' : ''
    "class #{class_name}ViewModel { fun updateData(#{update}) {} }\n" \
      "@Composable fun #{class_name}View(#{params.strip}) { Layout.draw(\"#{letter}\" + ((modifier as? Tagged)?.tag?.substringAfterLast('_') ?: \"\")#{placed}) }\n"
  end

  FLOW_SECTIONS_STUBS = <<~KOTLIN
    annotation class Composable
    interface Modifier { companion object : Modifier }
    class Tagged(val tag: String) : Modifier
    fun Modifier.testTag(tag: String): Modifier = Tagged(tag)
    class Wide(val inner: Modifier) : Modifier
    fun Modifier.fillMaxWidth(): Modifier = Wide(this)
    fun Modifier.fillMaxSize(): Modifier = this
    class ScrollState
    fun rememberScrollState(): ScrollState = ScrollState()
    fun Modifier.verticalScroll(state: ScrollState): Modifier = this
    fun Modifier.height(value: Dp): Modifier = this
    fun Modifier.requiredHeight(value: Dp): Modifier = this
    fun Modifier.fillMaxHeight(): Modifier = this
    class SemanticsPropertyReceiver { var testTagsAsResourceId: Boolean = false }
    fun Modifier.semantics(properties: SemanticsPropertyReceiver.() -> Unit): Modifier = this
    class Dp
    val Int.dp: Dp get() = Dp()
    interface Alignment { interface Vertical; companion object { val Top = object : Vertical {} } }
    fun Modifier.wrapContentHeight(align: Alignment.Vertical, unbounded: Boolean = false): Modifier = this
    class Arrangement { companion object { fun spacedBy(space: Dp): Arrangement = Arrangement() } }
    class Constraints(val hasBoundedHeight: Boolean)
    class BoxWithConstraintsScope { val constraints = Constraints(true) }
    fun BoxWithConstraints(modifier: Modifier = Modifier, content: BoxWithConstraintsScope.() -> Unit) { BoxWithConstraintsScope().content() }
    class ColumnScope
    fun Column(modifier: Modifier = Modifier, verticalArrangement: Arrangement? = null, content: ColumnScope.() -> Unit) { ColumnScope().content() }
    // A FlowRow is one wrapping region: a line of the printout.
    object Layout {
        val lines = mutableListOf<StringBuilder>()
        var region: StringBuilder? = null
        var fullRow = false
        fun draw(cell: String) { (region ?: StringBuilder().also { lines += it }).append(cell) }
        fun dump(): String = lines.joinToString("|")
    }
    fun FlowRow(modifier: Modifier = Modifier, horizontalArrangement: Arrangement, verticalArrangement: Arrangement, content: () -> Unit) {
        val outer = Layout.region
        Layout.region = StringBuilder().also { Layout.lines += it }
        content()
        Layout.region = outer
    }
    fun Box(modifier: Modifier = Modifier, content: () -> Unit) {
        val outer = Layout.fullRow
        Layout.fullRow = modifier is Wide
        content()
        Layout.fullRow = outer
    }
    fun LaunchedEffect(key1: Any?, block: suspend kotlinx.coroutines.CoroutineScope.() -> Unit) {}
    inline fun <T> key(vararg keys: Any?, block: () -> T): T = block()
    inline fun <T> remember(key1: Any?, calculation: () -> T): T = calculation()
    inline fun <T> remember(key1: Any?, key2: Any?, calculation: () -> T): T = calculation()
    object com { object kotlinjsonui { object utils { object CellIdGenerator {
        fun enrichCellIds(data: List<Map<String, Any>>, property: String): List<Map<String, Any>> = data
    } } } }
    inline fun <reified T : Any> viewModel(key: String? = null): T = T::class.java.getDeclaredConstructor().newInstance()
    class CollectionDataSource(val sections: List<CollectionDataSection> = emptyList())
    class CollectionDataSection(val cells: CellData? = null, val header: HeaderFooterData? = null, val footer: HeaderFooterData? = null) {
        class CellData(val viewName: String, val data: List<Map<String, Any>>)
        class HeaderFooterData(val viewName: String, val data: Map<String, Any>)
    }
    class Data(val rows: CollectionDataSource? = null)
    fun cells(name: String, n: Int) = CollectionDataSection.CellData(name, List(n) { mapOf<String, Any>("id" to "$name$it") })
  KOTLIN

  def routes
    {
      'plain' => emit,
      'matchParent' => emit('height' => 'matchParent'),
      'fixedHeight' => emit('height' => 200),
      'lazyNone' => emit('lazy' => 'none'),
      'tracked' => emit('cellIdProperty' => 'id', 'autoChangeTrackingId' => true),
      'oneSection' => emit('sections' => [{ 'cell' => 'ACell' }]),
      # Round 7: a section's declared header and footer are rows of their own.
      'edges' => emit('sections' => [{ 'cell' => 'ACell', 'header' => 'HCell', 'footer' => 'FCell' }, { 'cell' => 'BCell' }]),
      'edgesLazyNone' => emit('lazy' => 'none', 'sections' => [{ 'cell' => 'ACell', 'header' => 'HCell', 'footer' => 'FCell' }, { 'cell' => 'BCell' }]),
      'edgesOneSection' => emit('sections' => [{ 'cell' => 'ACell', 'header' => 'HCell' }]),
      'headerOnly' => emit('sections' => [{ 'header' => 'HCell' }, { 'cell' => 'BCell' }]),
      'edgesTracked' => emit('cellIdProperty' => 'id', 'autoChangeTrackingId' => true,
                             'sections' => [{ 'cell' => 'ACell', 'header' => 'HCell', 'footer' => 'FCell' }, { 'cell' => 'BCell' }])
    }
  end

  def program(functions)
    calls = functions.keys.map do |fn|
      "    Layout.lines.clear(); #{fn}(Data(CollectionDataSource(listOf(CollectionDataSection(cells(\"A\", 3), " \
        "CollectionDataSection.HeaderFooterData(\"H\", emptyMap()), CollectionDataSection.HeaderFooterData(\"F\", emptyMap())), " \
        "CollectionDataSection(cells(\"B\", 2))))), Any()); println(\"#{fn} => \" + Layout.dump())"
    end
    [FLOW_SECTIONS_STUBS, scaffold('ACell', 'A'), scaffold('BCell', 'B'), scaffold('HCell', 'H', edge: true), scaffold('FCell', 'F', edge: true),
     functions.map { |fn, body| "@Composable fun #{fn}(data: Data, viewModel: Any) {\n#{body}\n}" }.join("\n\n"),
     "fun main() {\n#{calls.join("\n")}\n}"].join("\n")
  end

  it 'every route compiles (the compile arm; the run below compiles it again to run it)' do
    expect(program(routes)).to compile_as_kotlin
  end

  it 'each section wraps in a region of its own, on every route that draws sections; one section as before' do
    skip "compile: #{KotlinCompiler.unavailable_reason}" if KotlinCompiler.unavailable_reason

    lines = Dir.mktmpdir('kjui_flow') do |dir|
      File.write(File.join(dir, 'Emitted.kt'), program(routes))
      stdlib = KotlinCompiler.jar('org.jetbrains.kotlin', 'kotlin-stdlib')
      coroutines = KotlinCompiler.jar('org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm')
      reflect = KotlinCompiler.jar('org.jetbrains.kotlin', 'kotlin-reflect')
      annotations = KotlinCompiler.jar('org.jetbrains', 'annotations')
      compiler_cp = KotlinCompiler.compiler_classpath
      out, = KotlinCompiler.java_capture2e('-cp', compiler_cp, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
                             '-no-stdlib', '-cp', [stdlib, reflect, annotations, coroutines].join(':'),
                             '-d', File.join(dir, 'out'), File.join(dir, 'Emitted.kt'))
      raise "did not compile:\n#{out}" if out.include?('error:')

      run, status = KotlinCompiler.java_capture2e('-cp', [File.join(dir, 'out'), stdlib, coroutines].join(':'), 'EmittedKt')
      raise "did not run:\n#{run}" unless status.success?

      run.lines.to_h { |l| l.chomp.split(' => ', 2) }
    end
    %w[plain matchParent fixedHeight lazyNone tracked].each do |route|
      expect(lines[route]).to eq('A0A1A2|B0B1'), lines.inspect
    end
    expect(lines['oneSection']).to eq('A0A1A2'), lines.inspect
    # The header a line of its own above the section's region, the footer
    # below (4f ruling 2026-09-26, round 7; the flow drew neither) — each in a
    # full-width row, the view at its own size.
    %w[edges edgesLazyNone edgesTracked].each { |route| expect(lines[route]).to eq('H|A0A1A2|F|B0B1'), lines.inspect }
    expect(lines['edgesOneSection']).to eq('H|A0A1A2'), lines.inspect
    expect(lines['headerOnly']).to eq('H|B0B1'), lines.inspect
  end

  it 'spaces the sections by the line spacing, and each region by the declared spacings' do
    code = emit
    expect(code).to match(/\A\s*Column\(/)
    column_args = code[/\A\s*Column\((.*?)\n\s*\) \{/m, 1]
    expect(column_args).to include('verticalArrangement = Arrangement.spacedBy(6.dp)'), code
    expect(code.scan('FlowRow(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp), ' \
                     'verticalArrangement = Arrangement.spacedBy(6.dp))').size).to eq(2)
    expect(emit('sections' => [{ 'cell' => 'ACell' }])).to match(/\A\s*FlowRow\(/)
  end

  # Each flow cell gets a ViewModel of its own. `viewModel(key = …)` returns
  # the instance its ViewModelStore already holds for that key
  # (ViewModelProvider.get(key, modelClass) — transcribed below as a map by
  # key), and the flow key was `<cell>_flow_<cellIndex>`: two sections of the
  # same cell class gave their first cells ONE ViewModel, so the later
  # section's data overwrote the earlier's and both cells drew it (measured on
  # the emit of 137468b2: `A:b0 A:b1 A:a2 | A:b0 A:b1`). The key carries the
  # section, as the sectioned grid's `<cell>_cell_<section>_<cellIndex>` does.
  # The two sections' rows share their ids (k0, k1…), so the cellIdProperty
  # key (`<cell>_flow_<cellId>`) is at the position where a missing section
  # collides too.
  describe 'the ViewModel each flow cell draws' do
    STORE_STUBS = <<~KOTLIN
      object Store { val byKey = HashMap<String, Any>() }
      inline fun <reified T : Any> viewModel(key: String? = null): T =
          Store.byKey.getOrPut(key ?: T::class.java.name) { T::class.java.getDeclaredConstructor().newInstance() } as T
      fun LaunchedEffect(key1: Any?, block: suspend kotlinx.coroutines.CoroutineScope.() -> Unit) {
          kotlinx.coroutines.runBlocking { block() }
      }
      class ACellViewModel { var data: Map<String, Any> = emptyMap(); fun updateData(updates: Map<String, Any>) { data = updates } }
      object Drawn { val cells = mutableListOf<Pair<String, ACellViewModel>>() }
      @Composable fun ACellView(viewModel: ACellViewModel, modifier: Modifier = Modifier) { Drawn.cells += ((modifier as? Tagged)?.tag ?: "") to viewModel }
    KOTLIN

    def shared_program(code)
      stubs = FLOW_SECTIONS_STUBS
              .sub(/^inline fun <reified T : Any> viewModel.*\n/, '')
              .sub(/^fun LaunchedEffect.*\n/, '')
      <<~KOTLIN
        #{stubs}
        #{STORE_STUBS}
        @Composable fun flow(data: Data, viewModel: Any) {
        #{code}
        }
        fun main() {
            flow(Data(CollectionDataSource(listOf(
                CollectionDataSection(cells = CollectionDataSection.CellData("A", List(3) { mapOf<String, Any>("id" to "k$it", "v" to "a$it") })),
                CollectionDataSection(cells = CollectionDataSection.CellData("A", List(2) { mapOf<String, Any>("id" to "k$it", "v" to "b$it") }))
            ))), Any())
            println("DRAWN " + Drawn.cells.joinToString(" ") { (tag, vm) -> tag.substringAfterLast('_') + ":" + vm.data["v"] })
            println("DISTINCT " + Drawn.cells.map { System.identityHashCode(it.second) }.distinct().size)
        }
      KOTLIN
    end

    it 'two sections of the same cell class draw their own data, one ViewModel per cell, with and without cellIdProperty' do
      skip "compile: #{KotlinCompiler.unavailable_reason}" if KotlinCompiler.unavailable_reason

      [{}, { 'cellIdProperty' => 'id' }].each do |extra|
        code = emit({ 'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'ACell' }] }.merge(extra))
        out = Dir.mktmpdir('kjui_flow_vm') do |dir|
          File.write(File.join(dir, 'Emitted.kt'), shared_program(code))
          stdlib = KotlinCompiler.jar('org.jetbrains.kotlin', 'kotlin-stdlib')
          coroutines = KotlinCompiler.jar('org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm')
          reflect = KotlinCompiler.jar('org.jetbrains.kotlin', 'kotlin-reflect')
          annotations = KotlinCompiler.jar('org.jetbrains', 'annotations')
          compiler_cp = KotlinCompiler.compiler_classpath
          built, = KotlinCompiler.java_capture2e('-cp', compiler_cp, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
                                   '-no-stdlib', '-cp', [stdlib, reflect, annotations, coroutines].join(':'),
                                   '-d', File.join(dir, 'out'), File.join(dir, 'Emitted.kt'))
          raise "did not compile:\n#{built}" if built.include?('error:')

          ran, status = KotlinCompiler.java_capture2e('-cp', [File.join(dir, 'out'), stdlib, coroutines].join(':'), 'EmittedKt')
          raise "did not run:\n#{ran}" unless status.success?

          ran
        end
        expect(out[/DRAWN (.*)/, 1]).to eq('0:a0 1:a1 2:a2 0:b0 1:b1'), "#{extra}\n#{out}"
        expect(out[/DISTINCT (\d+)/, 1]).to eq('5'), "#{extra}\n#{out}"
      end
    end

    it 'keys each flow cell by its section, as the sectioned grid does' do
      code = emit('sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'ACell' }])
      expect(code).to include('viewModel(key = "ACell_flow_0_${cellIndex}_').and include('viewModel(key = "ACell_flow_1_${cellIndex}_')
    end
  end
end
