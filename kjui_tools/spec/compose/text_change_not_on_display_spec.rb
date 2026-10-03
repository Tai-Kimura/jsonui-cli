# frozen_string_literal: true

require 'set'
require 'compose/compose_builder'
require 'compose/components/textfield_component'
require 'compose/components/textview_component'
require_relative '../support/kotlin_compiler'

# kjui-text-change-is-called-on-display-without-a-text-binding: a TextField /
# TextView whose `text` is not a binding called onTextChange once when the
# screen was drawn — `LaunchedEffect(state.text) { <handler> }` runs on its
# first composition, and this branch had no bound value to compare against.
# Measured on conf_ci (census cs_0029 / cs_0030 / cs_0067 / cs_0068): 1 call
# before any input on kjui codegen, 0 on KotlinJsonUI Dynamic. The branch now
# collects the text's changes — snapshotFlow, whose first emission is the
# value it starts from, with that first one dropped.
#
# The run below stands in a flow for snapshotFlow that emits as snapshotFlow
# does (the starting text, then each edit); the device measurement is the
# census's (the commit names it).
RSpec.describe 'kjui onTextChange without a text binding: an edit, not the display' do
  TEXT_CHANGE_RESOLVER = KjuiTools::Compose::Helpers::ResourceResolver

  around do |example|
    TEXT_CHANGE_RESOLVER.data_definitions = { 'h' => { 'name' => 'h', 'class' => '((String) -> Void)?' } }
    example.run
  ensure
    TEXT_CHANGE_RESOLVER.data_definitions = {}
  end

  def emit(type, node = {})
    imports = Set.new
    code = KjuiTools::Compose::Components.const_get("#{type}Component")
                                         .generate({ 'type' => type, 'id' => 'f', 'onTextChange' => '@{h}' }.merge(node), 0, imports)
    [code, imports]
  end

  %w[TextField TextView].each do |type|
    it "#{type}: collects the text's changes after its first value" do
      code, imports = emit(type)
      # Through 1.9.5: LaunchedEffect(textFieldState_f.text) { val newValue = ...; data.h?.invoke(newValue) }
      expect(code).to include('LaunchedEffect(textFieldState_f) { snapshotFlow { textFieldState_f.text.toString() }.drop(1).collect { newValue -> data.h?.invoke(newValue) } }')
      expect(code).not_to include('LaunchedEffect(textFieldState_f.text)')
      expect(imports).to include(:snapshot_flow, :flow_drop)
    end

    it "#{type}: a bare handler name is told the same way" do
      code, = emit(type, 'onTextChange' => 'h')
      # The bare name is called as its declaration takes it — here
      # `(String) -> Void`, the text (kjui-bare-ontextchange-ignores-the-
      # declared-shape; it was `invoke()`, which did not compile).
      expect(code).to include('snapshotFlow { textFieldState_f.text.toString() }.drop(1).collect { newValue -> data.h?.invoke(newValue) }')
    end

    it "#{type}: the bound form keeps its comparison (control)" do
      code, = emit(type, 'text' => '@{t}')
      expect(code).to include('if (newValue != data.t)')
      expect(code).not_to include('snapshotFlow')
    end
  end

  it 'calls the handler for the edit and not for the starting text, when run' do
    skip "compile: #{KotlinCompiler.unavailable_reason}" if KotlinCompiler.unavailable_reason

    # The text effect, whichever form it takes (the old one runs here too).
    line = emit('TextField').first.lines.find { |l| l.include?('LaunchedEffect(textFieldState_f') }.strip
    source = <<~KT
      import kotlinx.coroutines.CoroutineScope
      import kotlinx.coroutines.flow.Flow
      import kotlinx.coroutines.flow.drop
      import kotlinx.coroutines.flow.flow
      import kotlinx.coroutines.runBlocking

      class TextFieldState(var text: CharSequence)
      val edits = mutableListOf<String>()
      // As snapshotFlow emits: the value the block reads now, then each change.
      fun <T> snapshotFlow(block: () -> T): Flow<T> = flow {
          emit(block())
          for (edit in edits) { textFieldState_f.text = edit; emit(block()) }
      }
      lateinit var effect: suspend CoroutineScope.() -> Unit
      fun LaunchedEffect(key1: Any?, block: suspend CoroutineScope.() -> Unit) { effect = block }
      class Data(val h: ((String) -> Unit)? = null)
      val textFieldState_f = TextFieldState("")

      fun main() {
          val calls = mutableListOf<String>()
          val data = Data { calls += it }
          #{line}
          runBlocking { effect() }
          println("drawn=" + calls.map { "'$it'" })
          edits += "ab"
          runBlocking { effect() }
          println("edited=" + calls.map { "'$it'" })
      }
    KT
    run = KotlinCompiler.run(source)
    expect(run.errors).to eq([])
    # Through 1.9.5: drawn=[''] — the drawn screen alone called it.
    expect(run.output.lines.map(&:strip)).to eq(["drawn=[]", "edited=['ab']"])
  end
end
