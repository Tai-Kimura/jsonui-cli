# frozen_string_literal: true

require 'set'
require_relative '../../lib/compose/compose_builder'
require_relative '../support/kotlin_compiler'

# Sibling children are statements of one Kotlin block. A Collection hoists
# `val section0` / `val cellData0` (and `val enrichedData0` under
# autoChangeTrackingId) beside its call, so two sibling Collections declared
# one name twice and the file did not compile. kotlinc in KotlinJsonUI's
# conformance-host said "Conflicting declarations: local val section0",
# six errors for three Collections (ticket
# kjui-sibling-collections-redeclare-section-locals-in-one-scope). A child
# with visibility sits in its VisibilityWrapper's lambda, which is why the
# consumer faces' sibling Collections, all with visibility, compiled. A
# child whose locals clash with an earlier sibling's is now generated a
# level deeper, in a `run { }` of its own. The first one, and every child
# whose names are new, is emitted as before.
RSpec.describe 'kjui codegen: sibling children keep their locals apart' do
  def collection(id, extra = {})
    { 'type' => 'Collection', 'id' => id, 'items' => "@{#{id}}", 'cellIdProperty' => 'id',
      'sections' => [{ 'cell' => 'ACell' }] }.merge(extra)
  end

  def emit(children, depth = 1)
    %i[info debug warn].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    KjuiTools::Compose::ComposeBuilder.new
                                      .send(:generate_component, { 'type' => 'View', 'orientation' => 'vertical', 'child' => children }, depth).to_s
  end

  # Every `val` / `var` a block declares directly, by the block's indentation
  # and the line that opened it: [opening line, name] pairs that repeat.
  def redeclared(code)
    open_blocks = []
    seen = Hash.new { |h, k| h[k] = [] }
    code.lines.each_with_index do |line, i|
      indent = line[/\A */].size
      open_blocks.pop while open_blocks.any? && open_blocks.last[:indent] >= indent && line.strip.start_with?('}', ')')
      if (m = line.match(/\A *va[lr] ([A-Za-z_]\w*)\b/))
        owner = open_blocks.reverse.find { |b| b[:indent] < indent }
        seen[[owner && owner[:line], m[1]]] << i + 1
      end
      open_blocks << { indent: indent, line: i } if line.rstrip.end_with?('{', '(')
    end
    seen.select { |_k, lines| lines.size > 1 }
  end

  let(:three) { [collection('a'), collection('b'), collection('c', 'autoChangeTrackingId' => true)] }

  it 'three sibling Collections: the first as before, the second and third each in a run { } of its own' do
    code = emit(three)
    expect(code.scan(/^        val section0 = /).size).to eq(1)
    expect(code.scan(/^        run \{\n            val section0 = /).size).to eq(2)
    expect(code).to include('            val enrichedData0 = if (cellData0 != null) remember(cellData0.data)')
    expect(redeclared(code)).to eq({})
  end

  it 'two siblings: one run { }' do
    code = emit([collection('a'), collection('b')])
    expect(code.scan('run {').size).to eq(1)
    expect(redeclared(code)).to eq({})
  end

  it 'siblings with visibility (the consumer faces\' shape): no run { }, each in its VisibilityWrapper' do
    code = emit([collection('a', 'visibility' => '@{aVisibility}'), collection('b', 'visibility' => '@{bVisibility}')])
    expect(code).not_to include('run {')
    expect(code.scan('VisibilityWrapper(').size).to eq(2)
  end

  it 'one Collection beside other views: emitted as before (control)' do
    alone = emit([collection('a')])
    beside = emit([{ 'type' => 'Label', 'text' => 'x' }, collection('a'), { 'type' => 'Label', 'text' => 'y' }])
    expect(alone).not_to include('run {')
    expect(beside).not_to include('run {')
  end

  it 'the detector finds the old emit (mutation: no scope of its own)' do
    builder = KjuiTools::Compose::ComposeBuilder
    original = builder.instance_method(:in_own_scope_if_its_locals_clash)
    builder.send(:define_method, :in_own_scope_if_its_locals_clash) { |child_code, _depth, _declared| child_code }
    begin
      code = emit(three)
    ensure
      builder.send(:define_method, :in_own_scope_if_its_locals_clash, original)
    end
    expect(redeclared(code).keys.map(&:last).sort).to eq(%w[cellData0 cellData0 section0 section0].uniq.sort)
  end

  # Types the builder's whole emit for three sibling Collections against stubs
  # transcribed from KotlinJsonUI's signatures (CollectionStack, its mode and
  # axis, the cell ViewModel a cell layout's scaffold has) and Compose's
  # (Column, LazyListScope.items, remember, LaunchedEffect, viewModel). A
  # transcription, not a compile against the library. The redeclaration is
  # kotlinc's own error, which no stub can hide.
  it 'compiles, three siblings and two', :kotlin_compile do
    stubs = <<~KOTLIN
      annotation class Composable
      interface Modifier { companion object : Modifier }
      fun Modifier.testTag(tag: String): Modifier = this
      class SemanticsPropertyReceiver { var testTagsAsResourceId: Boolean = false }
      fun Modifier.semantics(properties: SemanticsPropertyReceiver.() -> Unit): Modifier = this
      class ColumnScope
      fun Column(modifier: Modifier = Modifier, content: ColumnScope.() -> Unit) { ColumnScope().content() }
      class LazyListScope { fun items(count: Int, key: ((Int) -> Any)? = null, itemContent: (Int) -> Unit) { repeat(count) { itemContent(it) } } }
      enum class CollectionStackMode { LAZY, EAGER, NONE }
      enum class CollectionStackAxis { VERTICAL, HORIZONTAL }
      fun CollectionStack(mode: CollectionStackMode, axis: CollectionStackAxis, modifier: Modifier = Modifier,
                          lazyContent: LazyListScope.() -> Unit, eagerContent: () -> Unit) { LazyListScope().lazyContent(); eagerContent() }
      class CellData(val viewName: String, val data: List<Map<String, Any>>)
      class CollectionDataSection(val cells: CellData?)
      class CollectionDataSource(val sections: List<CollectionDataSection>)
      class Data { val a: CollectionDataSource? = null; val b: CollectionDataSource? = null; val c: CollectionDataSource? = null }
      val data = Data()
      open class ViewModel
      class ACellViewModel : ViewModel() { fun updateData(updates: Map<String, Any>) {} }
      val viewModel = Any()
      inline fun <reified T : ViewModel> viewModel(key: String? = null): T = T::class.java.getDeclaredConstructor().newInstance()
      fun <T> remember(vararg keys: Any?, calculation: () -> T): T = calculation()
      fun LaunchedEffect(key1: Any?, block: suspend () -> Unit) {}
      fun ACellView(viewModel: ACellViewModel, modifier: Modifier = Modifier) {}
      object com { object kotlinjsonui { object utils { object CellIdGenerator {
          fun enrichCellIds(data: List<Map<String, Any>>, property: String): List<Map<String, Any>> = data
      } } } }
    KOTLIN
    [three, [collection('a'), collection('b')]].each do |children|
      expect("#{stubs}\nfun Host() {\n#{emit(children)}\n}\n").to compile_as_kotlin
    end
  end
end
