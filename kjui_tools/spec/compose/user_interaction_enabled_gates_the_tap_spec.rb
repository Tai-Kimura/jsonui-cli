# frozen_string_literal: true

require 'compose/compose_builder'
require 'compose/helpers/modifier_builder'
require 'core/tap_accessibility'
require 'core/image_accessibility'
require 'json'
require 'set'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# `userInteractionEnabled` gates the click as canTap does (the tap rule,
# shared/core/tap_accessibility.rb): `false` on the node, or on a node around
# it, is no click — and so no Role.Button — and a binding on either attaches
# the click while it resolves true. The node's own stop stays the pointer
# blocker (build_interaction_blocker): it consumed a touch, while TalkBack's
# double tap calls the click's action directly, and the click was announced as
# a button.
#
# The arms compare whole emissions: the node under the flag against the same
# node with canTap set to what the flag says, on every type the tap rule gives
# a shape and kjui draws, and on the onClick a Button or a control calls — on
# the node and inside a View that carries the flag.
RSpec.describe 'kjui userInteractionEnabled gates the click as canTap does' do
  tap = JsonUIShared::TapAccessibility

  extra = {
    'Image' => { 'srcName' => 'x' }, 'CircleImage' => { 'srcName' => 'x' }, 'CircleImageView' => { 'srcName' => 'x' },
    'ImageView' => { 'srcName' => 'x' }, 'Img' => { 'srcName' => 'x' },
    'NetworkImage' => { 'url' => 'https://e/x.png' }, 'Label' => { 'text' => 't' },
    'Text' => { 'text' => 't' }, 'IconLabel' => { 'text' => 't' }, 'Button' => { 'text' => 't' },
    'Switch' => { 'isOn' => '@{on}' }, 'CheckBox' => { 'label' => 't', 'isOn' => '@{on}' }
  }

  # The per-file counters a build resets (ComposeBuilder), so two emissions
  # compare as the same file would.
  counters = %w[TextComponent TextFieldComponent TextViewComponent ButtonComponent ConstraintLayoutComponent]
  emit = lambda do |node|
    counters.each { |c| KjuiTools::Compose::Components.const_get(c).reset_counter! }
    comp = JSON.parse(JSON.generate(node))
    JsonUIShared::ImageAccessibility.annotate!(comp, source_path: 'probe.json')
    tap.annotate!(comp)
    KjuiTools::Compose::ComposeBuilder.new.send(:generate_component, comp, 0)
  end
  node = ->(type, more = {}) { { 'type' => type, 'id' => 'n', 'onClick' => '@{onTap}' }.merge(extra[type] || {}).merge(more) }
  inside = ->(flag, child) { { 'type' => 'View', 'id' => 'p', 'userInteractionEnabled' => flag, 'child' => [child] } }

  # Not drawn by kjui's generate_component (a TODO comment: CircleView, and the
  # image aliases, which the build normalizes before it). Pinned, so a type
  # that starts clicking joins the arms below.
  not_clicking = %w[CircleView CircleImageView ImageView Img]
  types = (tap::KNOWN_TYPES - tap::INTERACTIVE_TYPES).uniq - not_clicking

  it 'reads every type the rule gives a shape, and pins the ones that draw no click' do
    expect(types).to include('View', 'Label', 'Image', 'IconLabel', 'NetworkImage')
    expect(types.size).to be >= 11
    silent = (tap::KNOWN_TYPES - tap::INTERACTIVE_TYPES).uniq.reject { |t| emit.call(node.call(t)).include?('data.onTap') }
    expect(silent).to match_array(not_clicking)
  end

  # A Button's onClick, and a control's call from its own operation
  # (operation_click_call): gated as canTap gates them.
  (types + %w[Button Switch CheckBox]).each do |type|
    describe type do
      it 'with no flag clicks (the arms below are not empty)' do
        expect(emit.call(node.call(type))).to include('data.onTap')
      end

      it 'userInteractionEnabled: false emits what canTap: false emits: no click, no role' do
        code = emit.call(node.call(type, 'userInteractionEnabled' => false))
        expect(code).to eq(emit.call(node.call(type, 'userInteractionEnabled' => false, 'canTap' => false)))
        expect(code).not_to include('data.onTap')
        expect(code).not_to include('Role.Button')
      end

      it 'inside a View with userInteractionEnabled: false, the same' do
        code = emit.call(inside.call(false, node.call(type)))
        expect(code).to eq(emit.call(inside.call(false, node.call(type, 'canTap' => false))))
        expect(code).not_to include('data.onTap')
        expect(code).not_to include('Role.Button')
      end

      it 'a bound userInteractionEnabled emits what a bound canTap on the same value emits' do
        code = emit.call(node.call(type, 'userInteractionEnabled' => '@{u}'))
        expect(code).to eq(emit.call(node.call(type, 'userInteractionEnabled' => '@{u}', 'canTap' => '@{u}')))
        expect(code).to include('(data.u ?: false)')
      end

      it 'inside a View with a bound userInteractionEnabled, the same' do
        code = emit.call(inside.call('@{u}', node.call(type)))
        expect(code).to eq(emit.call(inside.call('@{u}', node.call(type, 'canTap' => '@{u}'))))
      end
    end
  end

  it 'a click beside a View with userInteractionEnabled: false keeps its click and its role' do
    code = emit.call({ 'type' => 'View', 'id' => 'r', 'child' => [
                       inside.call(false, node.call('Label', 'id' => 'a', 'onClick' => '@{onA}')),
                       node.call('Label', 'id' => 'b', 'onClick' => '@{onB}')
                     ] })
    expect(code).not_to include('data.onA')
    expect(code.scan(/\.clickable\(role = Role\.Button\) \{ data\.onB\?\.invoke\(\) \}/).size).to eq(1)
  end

  # canTap and each bound flag around the click, outermost first, joined once.
  it 'joins a bound canTap and the bound flags around the click into one condition' do
    code = emit.call({ 'type' => 'View', 'id' => 'o', 'userInteractionEnabled' => '@{a}', 'child' => [
                       inside.call('@{b}', node.call('Label', 'canTap' => '@{c}', 'userInteractionEnabled' => '@{a}'))
                     ] })
    expect(code).to include('.then(if ((data.c ?: false) && (data.a ?: false) && (data.b ?: false)) Modifier.clickable(')
  end

  # The gated clickables type-check against Compose's signature, beside an
  # ungated one.
  it 'emits clickables that compile' do
    trees = [
      node.call('Label', 'userInteractionEnabled' => '@{u}'),
      inside.call('@{u}', node.call('View', 'canTap' => '@{c}', 'child' => [{ 'type' => 'Label', 'text' => 'x' }])),
      { 'type' => 'View', 'userInteractionEnabled' => '@{a}',
        'child' => [inside.call('@{b}', node.call('Image', 'canTap' => '@{c}'))] },
      node.call('Label')
    ]
    chains = []
    trees.each do |tree|
      tree = JSON.parse(JSON.generate(tree))
      tap.annotate!(tree)
      tap.walk(tree) do |n|
        clickable = KjuiTools::Compose::Helpers::ModifierBuilder.build_clickable(n, Set.new)
                                                                .select { |m| m.include?('clickable') }
        chains << "Modifier#{clickable.join}" unless clickable.empty?
      end
    end
    expect(chains.size).to eq(4)
    expect(chains.count { |c| c.include?('.then(if (') }).to eq(3)
    body = chains.each_with_index.map { |c, i| "fun tap#{i}(data: Data): Modifier = #{c}" }.join("\n")
    stubs = ComposeStubUniverse.clickable(chains.join("\n"))
                               .sub(/class Data\((.*)\)/) { "class Data(#{Regexp.last_match(1)}, val u: Boolean? = null, val a: Boolean? = null, val b: Boolean? = null, val c: Boolean? = null)" }
    expect(<<~KOTLIN).to compile_as_kotlin
      #{stubs}
      fun Modifier.then(other: Modifier): Modifier = this
      #{body}
    KOTLIN
  end
end
