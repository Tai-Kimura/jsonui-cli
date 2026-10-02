# frozen_string_literal: true

require 'set'
require 'compose/compose_builder'
require 'compose/components/radio_component'
require_relative '../support/kotlin_compiler'

# kjui-radio-items-never-calls-onvaluechange: a Radio in its declared `items`
# form drew a row per item and wrote its selection back on a tap, and called
# no onValueChange (through jsonui-cli 1.9.5 only the undeclared `options` form
# wired the handler). It compiled, so nothing said so. Both iOS faces call it
# with the item (read, not run); KotlinJsonUI Dynamic's items path does not
# (measured: kjui-dynamic-radio-items-never-calls-onvaluechange).
#
# The arm RUNS the emitted group on the JVM: the stubs keep every click
# lambda the group registers (the row's clickable and the RadioButton's
# onClick — two ways to tap the same item), the run taps each once, and the
# handler must be called once per tap with that item.
RSpec.describe 'kjui Radio items: a tap calls onValueChange with the item' do
  RADIO_ITEMS_RESOLVER = KjuiTools::Compose::Helpers::ResourceResolver

  def emit(node, handler_class)
    RADIO_ITEMS_RESOLVER.data_definitions = { 'h' => { 'name' => 'h', 'class' => handler_class } }
    KjuiTools::Compose::Components::RadioComponent.generate(
      { 'type' => 'Radio', 'id' => 'r', 'onValueChange' => '@{h}' }.merge(node), 0, Set.new
    )
  ensure
    RADIO_ITEMS_RESOLVER.data_definitions = {}
  end

  static_items = { 'items' => %w[a b], 'selectedValue' => '@{sel}' }
  bound_items = { 'items' => '@{list}', 'selectedValue' => '@{sel}' }

  it 'calls the handler in the row and in the button of every item' do
    code = emit(static_items, '((String, String) -> Void)?')
    # Through 1.9.5: 0 calls.
    expect(code.scan('data.h?.invoke("r", "a")').size).to eq(2)
    expect(code.scan('data.h?.invoke("r", "b")').size).to eq(2)
    expect(emit(bound_items, '((String, String) -> Void)?').scan('data.h?.invoke("r", item)').size).to eq(2)
    expect(emit(static_items, '(() -> Void)?').scan('data.h?.invoke()').size).to eq(4)
  end

  it 'writes the selection before it calls the handler' do
    code = emit(static_items, '((String, String) -> Void)?')
    expect(code.index('viewModel.updateData(mapOf("sel" to "a"))')).to be < code.index('data.h?.invoke("r", "a")')
  end

  it 'calls nothing when no handler is given (control)' do
    code = KjuiTools::Compose::Components::RadioComponent.generate(
      { 'type' => 'Radio', 'id' => 'r' }.merge(static_items), 0, Set.new
    )
    expect(code).not_to include('invoke(')
  end

  it 'calls the handler once per tap with the tapped item, when run' do
    skip "compile: #{KotlinCompiler.unavailable_reason}" if KotlinCompiler.unavailable_reason

    static = emit(static_items, '((String, String) -> Void)?')
    bound = emit(bound_items, '((String, String) -> Void)?')
    source = <<~KT
      val taps = mutableListOf<() -> Unit>()
      interface Modifier { companion object : Modifier }
      class Dp
      val Int.dp: Dp get() = Dp()
      class SemanticsScope { var testTagsAsResourceId = false }
      fun Modifier.testTag(tag: String): Modifier = this
      fun Modifier.semantics(block: SemanticsScope.() -> Unit): Modifier = this
      fun Modifier.fillMaxWidth(): Modifier = this
      fun Modifier.clickable(enabled: Boolean = true, onClick: () -> Unit): Modifier { taps += onClick; return this }
      fun Modifier.width(width: Dp): Modifier = this
      class Color { companion object { val Black = Color() } }
      interface Alignment { interface Vertical; companion object { val CenterVertically: Vertical = object : Vertical {} } }
      fun Column(modifier: Modifier = Modifier, content: () -> Unit) { content() }
      fun Row(verticalAlignment: Alignment.Vertical? = null, modifier: Modifier = Modifier, content: () -> Unit) { content() }
      class RadioButtonColors
      object RadioButtonDefaults { fun colors(selectedColor: Color = Color()) = RadioButtonColors() }
      fun RadioButton(selected: Boolean, onClick: () -> Unit, colors: RadioButtonColors = RadioButtonColors()) { taps += onClick }
      class ColorScheme { val primary = Color() }
      object MaterialTheme { val colorScheme = ColorScheme() }
      fun jsonUITintOr(fallback: Color): Color = fallback
      fun Spacer(modifier: Modifier) {}
      fun Text(text: String, color: Color = Color()) {}
      class Data(val sel: String = "", val list: List<String> = listOf("x", "y"), val h: ((String, String) -> Unit)? = null)
      class ViewModel { val writes = mutableListOf<String>(); fun updateData(values: Map<String, Any?>) { writes += values.values.map { it.toString() } } }
      fun staticGroup(data: Data, viewModel: ViewModel) {
      #{static}
      }
      fun boundGroup(data: Data, viewModel: ViewModel) {
      #{bound}
      }
      fun tapAll(draw: (Data, ViewModel) -> Unit): String {
          val calls = mutableListOf<String>()
          val vm = ViewModel()
          taps.clear()
          draw(Data(h = { id, value -> calls += "$id:$value" }), vm)
          taps.forEach { it() }
          return "taps=${taps.size} calls=$calls writes=${vm.writes}"
      }
      fun main() {
          println(tapAll(::staticGroup))
          println(tapAll(::boundGroup))
      }
    KT
    run = KotlinCompiler.run(source)
    expect(run.errors).to eq([])
    # Each item is registered twice (row, button); every tap writes and calls once.
    expect(run.output.lines.map(&:strip)).to eq([
      'taps=4 calls=[r:a, r:a, r:b, r:b] writes=[a, a, b, b]',
      'taps=4 calls=[r:x, r:x, r:y, r:y] writes=[x, x, y, y]'
    ])
  end
end
