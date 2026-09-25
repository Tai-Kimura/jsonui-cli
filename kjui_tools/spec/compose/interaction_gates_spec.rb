# frozen_string_literal: true

require 'compose/compose_builder'
require 'compose/helpers/modifier_builder'
require 'core/tap_accessibility'
require 'core/image_accessibility'
require 'json'
require 'set'
require_relative '../support/kotlin_compiler'

# `userInteractionEnabled: false` stops the node and what is in it, and
# `enabled: false` stops every handler of the node (attribute_definitions.json
# common; the tap rule reads a disabled long press as not operating) — static
# or bound.
#
# Compose has no allowsHitTesting: build_interaction_blocker consumes the
# events in the Initial pass. Nine components built no clickable, which is
# where the blocker came from — Button, CheckBox, Radio, Switch, Segment,
# Toggle, TabView, Embed and a ConstraintLayout container — so under the flag a
# Button acted and a Switch switched. And the long-press detector watches the
# Initial pass from outside the blocker and the clickable: it fired under both
# flags, as the pan did under `enabled` (measured, API 35 emulator,
# KotlinJsonUI conformance-host InteractionGateProbeTest).
RSpec.describe 'kjui interaction gates' do
  blocker = 'awaitPointerEvent(PointerEventPass.Initial).changes.forEach { it.consume() }'

  defs_path = File.expand_path('../../../shared/core/attribute_definitions.json', __dir__)
  defs = JSON.parse(File.read(defs_path))
  types = (defs.keys - %w[common]).select { |k| defs[k].is_a?(Hash) && !k.start_with?('_', '$') }.sort

  extra = {
    'Image' => { 'srcName' => 'x' }, 'CircleImage' => { 'srcName' => 'x' },
    'NetworkImage' => { 'url' => 'https://e/x.png' }, 'Label' => { 'text' => 't' },
    'Text' => { 'text' => 't' }, 'IconLabel' => { 'text' => 't' }, 'Button' => { 'text' => 't' },
    'SelectBox' => { 'items' => ['a'] }, 'Segment' => { 'items' => ['a'] }, 'Embed' => { 'screen' => 'S' },
    'TextField' => { 'text' => '@{t}' }, 'TextView' => { 'text' => '@{t}' },
    'TabView' => { 'tabs' => [{ 'title' => 'a' }] }
  }

  emit = lambda do |node|
    comp = JSON.parse(JSON.generate(node))
    JsonUIShared::ImageAccessibility.annotate!(comp, source_path: 'probe.json')
    JsonUIShared::TapAccessibility.annotate!(comp)
    KjuiTools::Compose::ComposeBuilder.new.send(:generate_component, comp, 0)
  end
  node = ->(type, more = {}) { { 'type' => type, 'id' => 'n' }.merge(extra[type] || {}).merge(more) }

  # Declared, and not drawn by kjui: the emission is a TODO comment. Pinned,
  # so a type that starts being drawn joins the arms below.
  not_drawn = %w[CircleView EditText Input]

  it 'reads every type the declaration knows' do
    expect(types.size).to be >= 29
    drawn = types.reject { |type| emit.call(node.call(type)).start_with?('// TODO: Implement component type') }
    expect(types - drawn).to match_array(not_drawn)
  end

  (types - not_drawn).each do |type|
    it "#{type} under userInteractionEnabled false carries the blocker" do
      expect(emit.call(node.call(type, 'userInteractionEnabled' => false))).to include(blocker)
    end

    it "#{type} with no flag carries none" do
      expect(emit.call(node.call(type))).not_to include(blocker)
    end
  end

  # The node's own long press, pan and pinch: either flag shuts them.
  gestures = { 'onLongPress' => 'longPressed', 'onPan' => 'detectDragGestures', 'onPinch' => 'calculateZoom' }
  flags = { 'userInteractionEnabled' => 'u', 'enabled' => 'on' }

  gestures.each do |event, marker|
    it "#{event} with no flag is attached" do
      expect(emit.call(node.call('View', event => '@{onG}'))).to include(marker)
    end

    flags.each do |flag, var|
      it "#{event} under #{flag} false is not attached" do
        code = emit.call(node.call('View', event => '@{onG}', flag => false))
        expect(code).not_to include(marker)
        expect(code).not_to include('onG')
      end

      it "#{event} under a bound #{flag} runs its handler only while it holds" do
        code = emit.call(node.call('View', event => '@{onG}', flag => "@{#{var}}"))
        gate = "(data.#{var} ?: false)"
        if event == 'onLongPress'
          expect(code).to include("if (longPressed && #{gate}) {")
        else
          expect(code).to include("if (#{gate}) data.onG?.invoke()")
        end
      end
    end
  end

  # The gates are what changed in these emissions: the lines that carry them,
  # as emitted, compile. (The whole emission — pointerInput, the detectors —
  # compiled on device in conformance-host InteractionGateProbeTest.)
  it 'the gated calls compile' do
    hold = emit.call(node.call('View', 'onLongPress' => '@{onG}', 'userInteractionEnabled' => '@{u}', 'enabled' => '@{on}'))
    drag = emit.call(node.call('View', 'onPan' => '@{onG}', 'enabled' => '@{on}'))
    zoom = emit.call(node.call('View', 'onPinch' => '@{onG}', 'userInteractionEnabled' => '@{u}'))
    lines = [
      hold[/^\s*(if \(longPressed && .*\) \{)$/, 1],
      hold[/^\s*(data\.onG\?\.invoke\(\))$/, 1],
      '}',
      drag[/^\s*(if \(.*\) data\.onG\?\.invoke\(\))$/, 1],
      zoom[/^\s*(if \(.*\) data\.onG\?\.invoke\(\))$/, 1]
    ]
    expect(lines).to all(be_a(String))
    expect(<<~KOTLIN).to compile_as_kotlin
      class Data(val onG: (() -> Unit)? = null, val u: Boolean? = null, val on: Boolean? = null)
      fun gated(data: Data, longPressed: Boolean) {
      #{lines.map { |l| "    #{l}" }.join("\n")}
      }
    KOTLIN
  end

  it 'joins the two flags into one gate' do
    code = emit.call(node.call('View', 'onLongPress' => '@{onG}', 'userInteractionEnabled' => '@{u}', 'enabled' => '@{on}'))
    expect(code).to include('if (longPressed && (data.u ?: false) && (data.on ?: false)) {')
    expect(KjuiTools::Compose::Helpers::ModifierBuilder.gesture_gate('userInteractionEnabled' => '@{u}', 'enabled' => false))
      .to eq('false')
    expect(KjuiTools::Compose::Helpers::ModifierBuilder.gesture_gate({})).to be_nil
  end
end
