# frozen_string_literal: true

require 'compose/compose_builder'
require 'core/tap_accessibility'
require 'json'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# A control calls its declared onClick from its own operation, after it — not
# from an outer `.clickable`
# (docs/bugs/kjui-dynamic-components-that-skip-the-common-modifiers.md, item A).
#
# Why, read from the Compose ui 1.12.0 / material3 1.4.0 sources (not
# measured: this library has no JVM Compose tests, and KotlinJsonUI's are
# androidTest):
# - Switch and Checkbox put the caller's modifier and their own toggleable
#   on ONE node (`modifier.then(toggleableModifier)`); SelectBox its own
#   `.clickable`; CustomTextField gives the modifier to the BasicTextField.
# - LayoutNode.calculateSemanticsConfiguration applies semantics tailToHead
#   (innermost first), and SemanticsConfiguration.set replaces an earlier
#   AccessibilityAction with a later one.
# So an outer `.clickable` took over the node's OnClick action: TalkBack's
# double tap ran the handler and did not operate the control (nor focus the
# field), while a touch operated it and never reached the handler.
#
# The tap rule (shared/core/tap_accessibility.rb) gives these types the
# shape `none` — "a control already, left as it was". canTap gates the call;
# `enabled` is the control's own parameter, so a disabled control neither
# operates nor calls. A text field's own tap focuses it and iOS codegen calls
# no onClick there, so TextField / TextView call none.
RSpec.describe 'kjui controls call onClick from their own operation' do
  call = 'data.onTap?.invoke()'
  gated = 'if ((data.gate ?: false)) { data.onTap?.invoke() }'

  emit = lambda do |node|
    comp = JSON.parse(JSON.generate(node))
    JsonUIShared::TapAccessibility.annotate!(comp)
    KjuiTools::Compose::ComposeBuilder.new.send(:generate_component, comp, 0).to_s
  end
  count = ->(code, marker) { code.scan(marker).size }

  # Each control, the number of places its operation happens (a Radio option
  # is selected from its row or its button), and where the call must sit.
  op = lambda do |opening|
    /#{opening}\{(?:[^{}]|\{[^{}]*\})*#{Regexp.escape(call)}[^{}]*\}/m
  end
  controls = {
    'Switch' => [{ 'type' => 'Switch' }, 1, op.call('onCheckedChange = ')],
    'Switch with a label' => [{ 'type' => 'Switch', 'label' => 'L' }, 1, op.call('onCheckedChange = ')],
    'Toggle' => [{ 'type' => 'Toggle' }, 1, op.call('onCheckedChange = ')],
    'CheckBox' => [{ 'type' => 'CheckBox' }, 1, op.call('onCheckedChange = ')],
    'CheckBox with a label' => [{ 'type' => 'CheckBox', 'label' => 'L' }, 1, op.call('onCheckedChange = ')],
    'CheckBox with icons' => [{ 'type' => 'CheckBox', 'src' => 'a', 'selectedIcon' => 'b' }, 1, op.call('onCheckedChange = ')],
    'Radio' => [{ 'type' => 'Radio', 'text' => 'r' }, 1, op.call('onClick = ')],
    'Radio options' => [{ 'type' => 'Radio', 'options' => %w[a b], 'bind' => '@{sel}' }, 4,
                        /(?:\.clickable(?:\(enabled = [^)]*\))? |onClick = )\{[^{}]*#{Regexp.escape(call)}/m],
    'Radio items' => [{ 'type' => 'Radio', 'items' => %w[a b], 'selectedValue' => '@{sel}' }, 4,
                      /(?:\.clickable(?:\(enabled = [^)]*\))? |onClick = )\{[^{}]*#{Regexp.escape(call)}/m],
    'Segment' => [{ 'type' => 'Segment', 'items' => %w[a b], 'bind' => '@{idx}' }, 2, op.call('onClick = ')],
    'Slider' => [{ 'type' => 'Slider' }, 1, op.call('onValueChangeFinished = ')],
    'SelectBox' => [{ 'type' => 'SelectBox', 'items' => %w[a b] }, 1, op.call('onValueChange = ')],
    'SelectBox with a binding' => [{ 'type' => 'SelectBox', 'items' => %w[a b], 'selectedItem' => '@{pick}' }, 1,
                                   op.call('onValueChange = ')]
  }

  controls.each do |label, (node, places, where)|
    describe label do
      let(:with_click) { emit.call(node.merge('onClick' => '@{onTap}')) }

      it 'is a tap of shape `none` in the tap rule' do
        tree = JSON.parse(JSON.generate(node.merge('onClick' => '@{onTap}')))
        expect(JsonUIShared::TapAccessibility.shape(tree)).to eq('none')
      end

      it 'calls onClick from its own operation, once per place, with no outer clickable around it' do
        expect(count.call(with_click, call)).to eq(places), with_click
        expect(count.call(with_click, where)).to eq(places), with_click
        expect(with_click).not_to match(/\.clickable\b[^{]*\{ #{Regexp.escape(call)} \}/)
      end

      it 'under canTap false still operates and does not call' do
        code = emit.call(node.merge('onClick' => '@{onTap}', 'canTap' => false))
        expect(code).not_to include(call)
        expect(code).to eq(emit.call(node))
      end

      it 'under a bound canTap calls while it holds' do
        code = emit.call(node.merge('onClick' => '@{onTap}', 'canTap' => '@{gate}'))
        expect(count.call(code, gated)).to eq(places), code
        expect(count.call(code, call)).to eq(places)
      end

      it 'under enabled false is disabled on its own parameter, so it neither operates nor calls' do
        code = emit.call(node.merge('onClick' => '@{onTap}', 'enabled' => false))
        expect(code).to match(/\benabled = false\b/), code
        expect(code).not_to match(/\.clickable\b[^{]*\{ #{Regexp.escape(call)} \}/)
      end
    end
  end

  # The call comes after the control's own update and its onValueChange.
  it 'calls onClick after the value is written and onValueChange has run' do
    switch = emit.call('type' => 'Switch', 'isOn' => '@{on}', 'onValueChange' => '@{onChange}', 'onClick' => '@{onTap}')
    expect(switch).to include(
      'onCheckedChange = { newValue -> viewModel.updateData(mapOf("on" to newValue)); data.onChange?.invoke(); ' \
      "#{call} }"
    )
    radio = emit.call('type' => 'Radio', 'text' => 'r', 'onClick' => '@{onTap}')
    expect(radio).to include(%(onClick = { viewModel.updateData(mapOf("selectedRadiogroup" to "radio_0")); #{call} }))
    segment = emit.call('type' => 'Segment', 'items' => %w[a], 'bind' => '@{idx}', 'onClick' => '@{onTap}')
    expect(segment).to match(/viewModel\.updateData\(mapOf\("idx" to 0\)\)\n\s*#{Regexp.escape(call)}\n/)
  end

  # A text field's own tap focuses it. iOS codegen calls no onClick there; an
  # outer clickable took the focus action from TalkBack. So: no call, no
  # clickable — the gestures and the blocker stay.
  [{ 'type' => 'TextField', 'text' => '@{t}' }, { 'type' => 'TextView', 'text' => '@{t}' },
   { 'type' => 'TextField', 'text' => '@{t}', 'margins' => [1, 1, 1, 1] },
   { 'type' => 'TextView', 'text' => '@{t}', 'margins' => [1, 1, 1, 1] }].each do |node|
    it "#{node['type']}#{node['margins'] ? ' with margins' : ''} calls no onClick and carries no clickable" do
      held = emit.call(node.merge('onClick' => '@{onTap}', 'onLongPress' => '@{onHold}'))
      shut = emit.call(node.merge('onClick' => '@{onTap}', 'userInteractionEnabled' => false))
      [held, shut].each do |code|
        expect(code).not_to include(call)
        expect(code).not_to include('.clickable')
      end
      expect(held).to include('longPressed')
      expect(shut).to include('awaitPointerEvent(PointerEventPass.Initial).changes.forEach { it.consume() }')
    end
  end

  # A container keeps its tap: the tap rule's `none` there is "holds a
  # control", and the clickable sits on the container's own node, not on a
  # control's.
  %w[View TabView Embed SafeAreaView].each do |type|
    it "#{type} (a container) keeps its clickable" do
      node = { 'type' => type, 'onClick' => '@{onTap}' }
      node['tabs'] = [{ 'title' => 'a' }] if type == 'TabView'
      node['screen'] = 'other' if type == 'Embed'
      expect(emit.call(node)).to match(/\.clickable\b[^{]*\{ #{Regexp.escape(call)} \}/)
    end
  end

  # Every routed emit, with the gate and `enabled` bound, type-checks (stubs:
  # ComposeStubUniverse.common_stages — "well-typed Kotlin", not "valid
  # Compose").
  it 'compiles every control with its onClick routed' do
    emitted = controls.each_with_index.map do |(label, (node, _, _)), i|
      code = emit.call(node.merge('onClick' => '@{onTap}', 'canTap' => '@{gate}', 'enabled' => '@{on}'))
      "// #{label}\nfun control#{i}(data: Data, viewModel: ViewModel) {\n#{code}\n}"
    end.join("\n\n")
    expect(emitted.scan(gated).size).to eq(controls.values.sum { |(_, places, _)| places })
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(emitted)}
      class Data(
          val onTap: (() -> Unit)? = null, val gate: Boolean? = null, val on: Boolean = true,
          val sel: String = "", val idx: Int = 0, val pick: String = "", val selectedRadiogroup: String = ""
      )
      class ViewModel { fun updateData(values: Map<String, Any?>) {} }
      #{emitted}
    KOTLIN
  end
end
