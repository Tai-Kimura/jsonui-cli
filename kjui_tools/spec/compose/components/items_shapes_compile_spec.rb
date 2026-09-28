# frozen_string_literal: true

require 'set'
require_relative '../../../lib/compose/compose_builder'
require_relative '../../support/kotlin_compiler'

# `items` is declared ["array", "binding"] on Collection (whose alias Table
# is) and on Radio. Every declared shape, through the Compose codegen.
#
# Until 1.9.0 (measured on 32785ce8, 2026-09-26) a Table given an array
# raised NoMethodError (`.match` on an Array) — kjui drew Table with its own
# TableComponent, where the type-synonym canon, sjui and rjui draw it as a
# Collection — and a Radio given a binding raised NoMethodError (`each` on a
# String): the build went down on a declared shape. Ticket
# kjui-codegen-table-crashes-on-an-items-array.
RSpec.describe 'kjui codegen: each declared shape of `items`' do
  # Stubs of the Compose names the Radio emit calls — a green says
  # "well-typed against these stubs", not "valid Compose".
  RADIO_STUBS = <<~KOTLIN
    open class Modifier { companion object : Modifier() }
    class Dp
    val Int.dp: Dp get() = Dp()
    fun Modifier.fillMaxWidth(): Modifier = this
    fun Modifier.height(h: Dp): Modifier = this
    fun Modifier.width(w: Dp): Modifier = this
    fun Modifier.clickable(onClick: () -> Unit): Modifier = this
    // A node with an id carries its test tag (the common stages).
    fun Modifier.testTag(tag: String): Modifier = this
    class SemanticsPropertyReceiver { var testTagsAsResourceId: Boolean = false }
    fun Modifier.semantics(properties: SemanticsPropertyReceiver.() -> Unit): Modifier = this
    class Color { companion object { val Black = Color() } }
    object Alignment { class Vertical; val CenterVertically = Vertical() }
    fun Row(modifier: Modifier = Modifier, verticalAlignment: Alignment.Vertical = Alignment.CenterVertically, content: () -> Unit) {}
    fun Column(modifier: Modifier = Modifier, content: () -> Unit) {}
    fun Text(text: String, color: Color = Color.Black) {}
    // A Radio's selected colour: its own, else the tint a container handed
    // down (KotlinJsonUI's jsonUITintOr, InheritedTint).
    class RadioButtonColors
    object RadioButtonDefaults { fun colors(selectedColor: Color = Color.Black) = RadioButtonColors() }
    class ColorScheme { val primary = Color() }
    object MaterialTheme { val colorScheme = ColorScheme() }
    fun jsonUITintOr(fallback: Color): Color = fallback
    fun RadioButton(selected: Boolean, onClick: () -> Unit, colors: RadioButtonColors = RadioButtonColors()) {}
    fun Spacer(modifier: Modifier) {}
    class ViewModel { fun updateData(values: Map<String, Any?>) {} }
    class Data(val rows: List<Any> = listOf(), val sel: String = "")
  KOTLIN

  def emit(node)
    %i[info debug warn].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    KjuiTools::Compose::ComposeBuilder.new.send(:generate_component, JSON.parse(JSON.generate(node)), 1).to_s
  end

  shapes = { 'an array' => %w[a b], 'an empty array' => [], 'a binding' => '@{rows}', 'absent' => :absent }.freeze

  def with_items(node, items)
    items == :absent ? node : node.merge('items' => items)
  end

  # Each route CollectionComponent takes (a minimal Collection returns before
  # it reads `items` at all, which is how a family table of minimal nodes
  # missed the eight routes that raised).
  CELL = ['RowCell'].freeze
  ROUTES = [
    {}, { 'cellClasses' => CELL }, { 'cellClasses' => CELL, 'layout' => 'horizontal' },
    { 'cellClasses' => CELL, 'layout' => 'flow' }, { 'cellClasses' => CELL, 'layout' => 'horizontal', 'paging' => true },
    { 'cellClasses' => CELL, 'lazy' => 'none' }, { 'cellClasses' => CELL, 'lazy' => 'none', 'layout' => 'horizontal' },
    { 'cellClasses' => CELL, 'height' => 'wrapContent' }, { 'sections' => [{ 'cell' => 'RowCell' }] },
    { 'sections' => [{ 'cell' => 'RowCell', 'columns' => 2 }] }, { 'sections' => [{ 'cell' => 'RowCell' }], 'layout' => 'horizontal' },
    { 'sections' => [{ 'cell' => 'RowCell' }], 'lazy' => 'none' },
    { 'sections' => [{ 'cell' => 'RowCell' }], 'cellIdProperty' => 'id', 'autoChangeTrackingId' => true }
  ].freeze

  it 'draws a Table as the Collection it is, on every route and whatever shape its items take' do
    aggregate_failures do
      ROUTES.product(shapes.to_a).each do |route, (label, items)|
        base = { 'id' => 'list', 'width' => 'matchParent', 'height' => 200 }.merge(route)
        collection = emit(with_items(base.merge('type' => 'Collection'), items))
        table = emit(with_items(base.merge('type' => 'Table'), items))
        expect(table).to eq(collection), "#{route} items #{label}"
        expect(table).not_to include('HorizontalDivider'), "#{route} items #{label}: TableComponent's rows"
      end
    end
  end

  it 'sets an items array aside on every route (a binding is what the routes draw from)' do
    aggregate_failures do
      ROUTES.each do |route|
        base = { 'type' => 'Collection', 'id' => 'list', 'width' => 'matchParent', 'height' => 200 }.merge(route)
        expect(emit(with_items(base, %w[a b]))).to eq(emit(base)), route.inspect
      end
    end
  end

  it 'draws a Radio with an items array as its options, and with a binding as the list the data holds; both compile' do
    array = emit('type' => 'Radio', 'id' => 'r', 'items' => %w[a b], 'selectedValue' => '@{sel}')
    bound = emit('type' => 'Radio', 'id' => 'r', 'items' => '@{rows}', 'selectedValue' => '@{sel}')
    expect(array.scan('RadioButton(').size).to eq(2)
    expect(bound).to include('data.rows.forEach { item ->').and include('selected = data.sel == item')
    expect(bound.scan('RadioButton(').size).to eq(1) # one row, drawn for each item
    source = [array, bound].each_with_index.map { |code, i| "fun host#{i}(data: Data, viewModel: ViewModel) {\n#{code}\n}\n" }.join
    expect("#{RADIO_STUBS}\n#{source}").to compile_as_kotlin
  end
end
