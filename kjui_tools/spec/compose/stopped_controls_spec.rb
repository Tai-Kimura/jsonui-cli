# frozen_string_literal: true

require 'compose/compose_builder'
require 'compose/helpers/modifier_builder'
require 'core/tap_accessibility'
require 'core/image_accessibility'
require 'json'
require 'set'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# A control a stop holds (the tap rule's `control?`, which annotate! marks):
# the pointer blocker kept a touch out and nothing else — TalkBack's click is
# not a touch, and it called the control's own operation (probe:
# A11yActivationInsideAStopProbe; iOS measured the same shape). The emit
# (ComposeBuilder#stop_held_control):
# - the control's node reads `disabled()` while it is stopped — Compose's
#   accessibility delegate performs no action on a disabled node, and
#   TalkBack says so; nothing is drawn (`enabled = false` would grey it);
# - what it writes (`viewModel.updateData(…)`) is gated on the same stop.
RSpec.describe 'kjui a control a stop holds' do
  after { KjuiTools::Compose::Helpers::ModifierBuilder.reads_interaction_local = false }

  counters = %w[TextComponent TextFieldComponent TextViewComponent ButtonComponent ConstraintLayoutComponent]
  emit = lambda do |node, reads: false|
    counters.each { |c| KjuiTools::Compose::Components.const_get(c).reset_counter! }
    KjuiTools::Compose::Helpers::ModifierBuilder.reads_interaction_local = reads
    comp = JSON.parse(JSON.generate(node))
    JsonUIShared::ImageAccessibility.annotate!(comp, source_path: 'probe.json')
    JsonUIShared::TapAccessibility.annotate!(comp)
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@required_imports, Set.new)
    builder.instance_variable_set(:@responsive_counter, 0)
    code = builder.send(:generate_component, comp, 1)
    [code, builder.instance_variable_get(:@required_imports)]
  ensure
    KjuiTools::Compose::Helpers::ModifierBuilder.reads_interaction_local = false
  end

  # The controls that write a value, with what they need to convert.
  writers = {
    'Switch' => { 'isOn' => '@{on}' }, 'Toggle' => { 'isOn' => '@{on}' }, 'CheckBox' => { 'isOn' => '@{on}' },
    'Radio' => { 'items' => %w[a b], 'selectedValue' => '@{sel}' }, 'Segment' => { 'items' => %w[a b], 'selectedIndex' => '@{idx}' },
    'Slider' => { 'value' => '@{v}' }, 'SelectBox' => { 'items' => %w[a b], 'selectedIndex' => '@{idx}' },
    'TextField' => { 'text' => '@{t}' }, 'TextView' => { 'text' => '@{t}' }
  }
  node = ->(type, more) { { 'type' => type, 'id' => 'c' }.merge(more) }
  stopping = ->(flag, child) { { 'type' => 'View', 'id' => 'stop', 'userInteractionEnabled' => flag, 'child' => [child] } }
  static_semantics = '.semantics { disabled() }'
  bound_semantics = '.then(if (!((data.u ?: false))) Modifier.semantics { disabled() } else Modifier)'

  # The nodes inside a control a user operates on their own (a Radio's rows
  # and RadioButtons, a Segment's Tabs, a CheckBox's Checkbox): each chain
  # `.clickable` / `.toggleable` / `.selectable`, and each inner composable
  # call with the disabled read it carries (its `modifier` argument, or the
  # element right in front of the chain call) — [what, carries it].
  inner_nodes = lambda do |code, element|
    chains = code.scan(/^(.*?)\.(clickable|toggleable|selectable)\b/).map { |before, what| [what, before.end_with?(element)] }
    # A call carrying the control's own tag is its root, not an inner node.
    calls = code.scan(/\b(RadioButton|Checkbox|Tab)\((.*?)\n\s*\)/m).reject { |_, args| args.include?('testTagsAsResourceId') }.map do |what, args|
      [what, args.include?("modifier = #{element.delete_prefix('.then(').delete_suffix(')').sub(/\A\.semantics/, 'Modifier.semantics')}")]
    end
    chains + calls
  end
  # The wrapped controls and the inner nodes each draws (the rest have none;
  # a CheckBox without a label is its Checkbox, which is its root).
  inner_counts = { 'Radio' => 4, 'Segment' => 2 }

  writers.each do |type, more|
    it "#{type}: inside false, every write is shut and the node reads disabled" do
      code, imports = emit.call(stopping.call(false, node.call(type, more)))
      writes = code.scan('viewModel.updateData(').size
      expect(writes).to be >= 1, code
      expect(code.scan('if (false) viewModel.updateData(').size).to eq(writes), code
      expect(code.scan(static_semantics).size).to eq(1 + inner_counts.fetch(type, 0)), code
      expect(imports).to include(:semantics_disabled)
    end

    it "#{type}: inside false, every node inside it a user operates reads disabled too" do
      code, = emit.call(stopping.call(false, node.call(type, more)))
      nodes = inner_nodes.call(code, static_semantics)
      expect(nodes.size).to eq(inner_counts.fetch(type, 0)), code
      expect(nodes.reject { |_, carries| carries }).to eq([]), code
    end

    it "#{type}: inside a binding, every node inside it reads the binding" do
      code, = emit.call(stopping.call('@{u}', node.call(type, more)))
      nodes = inner_nodes.call(code, bound_semantics)
      expect(nodes.size).to eq(inner_counts.fetch(type, 0)), code
      expect(nodes.reject { |_, carries| carries }).to eq([]), code
    end

    it "#{type}: inside a binding, every write and the disabled read follow it" do
      code, = emit.call(stopping.call('@{u}', node.call(type, more)))
      writes = code.scan('viewModel.updateData(').size
      expect(code.scan('if ((data.u ?: false)) viewModel.updateData(').size).to eq(writes), code
      expect(code).to include(bound_semantics)
    end

    it "#{type}: with false of its own, the same as inside false" do
      code, = emit.call(node.call(type, more).merge('userInteractionEnabled' => false))
      expect(code.scan('if (false) viewModel.updateData(').size).to eq(code.scan('viewModel.updateData(').size)
      expect(code).to include(static_semantics)
    end

    it "#{type}: in a layout a stop can reach, the stop handed down gates both, captured" do
      code, = emit.call(node.call(type, more), reads: true)
      expect(code.lstrip).to start_with('LocalInteractionStopped.current.let { jsonuiInteractionStopped ->'), code
      expect(code.scan('if (!jsonuiInteractionStopped) viewModel.updateData(').size).to eq(code.scan('viewModel.updateData(').size)
      expect(code).to include('.then(if (!(!jsonuiInteractionStopped)) Modifier.semantics { disabled() } else Modifier)')
    end

    it "#{type}: beside no stop, emitted as it was" do
      code, = emit.call(node.call(type, more))
      expect(code).not_to include('if (false) viewModel.updateData(')
      expect(code).not_to include('jsonuiInteractionStopped')
      expect(code).not_to include('disabled()')
    end
  end

  it 'a CheckBox with a label: its Checkbox, a node of its own inside the row, reads disabled too' do
    code, = emit.call(stopping.call(false, node.call('CheckBox', 'isOn' => '@{on}', 'text' => 'cb')))
    expect(inner_nodes.call(code, static_semantics)).to eq([['Checkbox', true]]), code
    code, = emit.call(stopping.call('@{u}', node.call('CheckBox', 'isOn' => '@{on}', 'text' => 'cb')))
    expect(inner_nodes.call(code, bound_semantics)).to eq([['Checkbox', true]]), code
  end

  it 'a Radio of its own (a group member): its RadioButton reads disabled too' do
    code, = emit.call(stopping.call(false, node.call('Radio', 'group' => 'g', 'text' => 'one', 'selectedValue' => '@{sel}')))
    expect(inner_nodes.call(code, static_semantics)).to eq([['RadioButton', true]]), code
  end

  it "an inner composable's own modifier takes the read in front" do
    code, = emit.call(stopping.call(false, node.call('Radio', 'group' => 'g', 'text' => 'one', 'iconSize' => 24, 'selectedValue' => '@{sel}')))
    call = code[/RadioButton\(.*?\n\s*\)/m] or raise code
    expect(call).to include('modifier = Modifier.semantics { disabled() }.size(24.dp)'), code
    expect(call.scan('modifier =').size).to eq(1), code
  end

  # The rule asks the type a node is drawn as (TypeSynonyms.drawn_type, 4f's
  # ruling, jsonui-cli 1.9.0): a Picker is drawn as a SelectBox — a control —
  # and a TableView as a Collection, a container.
  it 'a synonym spelling is the control or the container it is drawn as' do
    code, = emit.call(stopping.call(false, node.call('Picker', 'items' => %w[a b], 'selectedIndex' => '@{idx}')))
    expect(code.scan('viewModel.updateData(').size).to be >= 1
    expect(code.scan('if (false) viewModel.updateData(').size).to eq(code.scan('viewModel.updateData(').size), code
    expect(code).to include(static_semantics)
    code, = emit.call(stopping.call(false, { 'type' => 'TableView', 'id' => 't' }))
    expect(code).not_to include('disabled()')
  end

  it 'a Button inside false reads disabled (its onClick is shut already)' do
    code, = emit.call(stopping.call(false, node.call('Button', 'text' => 't', 'onClick' => '@{onTap}')))
    expect(code).to include('onClick = { }')
    expect(code).to include(static_semantics)
  end

  it 'not on what is not a control: a Label, a container' do
    code, = emit.call(stopping.call(false, { 'type' => 'View', 'child' => [
      { 'type' => 'Label', 'text' => 'x' }, { 'type' => 'ScrollView', 'id' => 's', 'child' => [{ 'type' => 'Label', 'text' => 'y' }] }
    ] }))
    expect(code).not_to include('disabled()')
  end

  # Both sides, run: the gated write is made while the stop is open, and not
  # while it is shut.
  it 'the gated write is made when the stop is open and not when it is shut' do
    code, = emit.call(stopping.call('@{u}', node.call('Switch', writers['Switch'])))
    lambda = code[/onCheckedChange = (\{ newValue -> [^\n]*\})/, 1] or raise code
    source = <<~KOTLIN
      var writes = 0
      class ViewModel { fun updateData(values: Map<String, Any?>) { writes++ } }
      class Data(val u: Boolean?)
      fun fire(data: Data, viewModel: ViewModel) { val onCheckedChange: (Boolean) -> Unit = #{lambda}; onCheckedChange(true) }
      fun main() {
          val vm = ViewModel()
          fire(Data(true), vm)
          val open = writes
          fire(Data(false), vm)
          println("open=$open shut=${writes - open}")
      }
    KOTLIN
    result = KotlinCompiler.run(source)
    skip("compile_as_kotlin: #{KotlinCompiler.unavailable_reason}") if KotlinCompiler.unavailable_reason
    expect(result.errors).to eq([])
    expect(result.output.strip).to eq('open=1 shut=0')
  end

  it 'every held control compiles, the disabled read in its modifier chain' do
    functions = writers.map.with_index do |(type, more), i|
      code, = emit.call(stopping.call('@{u}', node.call(type, more)))
      "// #{type}\nfun emitted#{i}(data: Data, viewModel: ViewModel) {\n#{code}\n}"
    end
    emitted = functions.join("\n\n")
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(emitted)}
      class Data(
          val u: Boolean? = null, val on: Boolean = false, val sel: String = "",
          val idx: Int = 0, val v: Double = 0.0, val t: String = "", val selectedRadiogroup: String = "",
          val cIsFocused: Boolean = false
      )
      class ViewModel { fun updateData(values: Map<String, Any?>) {} }
      #{emitted}
    KOTLIN
  end
end
