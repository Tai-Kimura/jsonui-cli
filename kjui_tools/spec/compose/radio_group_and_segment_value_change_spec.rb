# frozen_string_literal: true

require 'set'
require 'compose/compose_builder'
require 'compose/components/radio_component'
require 'compose/components/segment_component'
require_relative '../support/kotlin_compiler'

# Two declared forms whose handler kjui did not call as declared, found by the
# runtime handler census (conf_ci, 2026-10-03):
#
# - kjui-radio-group-form-never-calls-onvaluechange: a Radio of a `group`
#   wrote the selection on tap and called no onValueChange (0 calls on kjui
#   codegen and KotlinJsonUI Dynamic). It is now called with this radio's
#   value — `value` when declared, else its id — after the selection is
#   written and before onClick, as both iOS faces call it (jsonui-cli
#   f96b340e, SwiftJsonUI 7ea1e4a).
# - kjui-segment-valuechange-binding-writes-the-braces: `valueChange` is
#   declared `string`, and both a bare name and a binding are its spellings;
#   it was written `data.<raw>?.invoke()` — `data.@{h}?.invoke()` for a
#   binding, no value for a one-parameter handler. Neither compiled. It is
#   now called as its declaration takes it, the index as its value.
#
# The arms run the emitted tap on the JVM: the handler's calls and their order
# against the selection's write and onClick.
RSpec.describe 'kjui: a group Radio and a Segment valueChange call their handler as declared' do
  RG_RESOLVER = KjuiTools::Compose::Helpers::ResourceResolver

  def with_defs(defs)
    RG_RESOLVER.data_definitions = defs
    yield
  ensure
    RG_RESOLVER.data_definitions = {}
  end

  def radio(node, handler_class)
    with_defs('h' => { 'name' => 'h', 'class' => handler_class }) do
      KjuiTools::Compose::Components::RadioComponent.generate(
        { 'type' => 'Radio', 'id' => 'r1', 'group' => 'g', 'text' => 'A', 'onValueChange' => '@{h}', 'onClick' => '@{k}' }.merge(node),
        0, Set.new
      )
    end
  end

  def segment(value_change, handler_class)
    with_defs('h' => { 'name' => 'h', 'class' => handler_class }) do
      KjuiTools::Compose::Components::SegmentComponent.generate(
        { 'type' => 'Segment', 'id' => 's', 'items' => %w[a b], 'selectedIndex' => 0, 'valueChange' => value_change }, 0, Set.new
      )
    end
  end

  it 'a group Radio: writes, calls onValueChange with its value, then onClick' do
    # Through 1.9.5: onClick = { radioGroups["g"] = "r1"; data.k?.invoke() }.
    expect(radio({}, '((Any) -> Void)?')).to include('onClick = { radioGroups["g"] = "r1"; data.h?.invoke("r1"); data.k?.invoke() }')
    expect(radio({ 'value' => 'v1' }, '((Any) -> Void)?')).to include('radioGroups["g"] = "v1"; data.h?.invoke("v1"); data.k?.invoke()')
    expect(radio({ 'selectedValue' => '@{sel}' }, '(() -> Void)?')).to include('data.h?.invoke(); data.k?.invoke()')
  end

  it 'a group Radio with no onValueChange calls only onClick (control)' do
    code = with_defs({}) do
      KjuiTools::Compose::Components::RadioComponent.generate(
        { 'type' => 'Radio', 'id' => 'r1', 'group' => 'g', 'text' => 'A', 'onClick' => '@{k}' }, 0, Set.new
      )
    end
    expect(code).to include('onClick = { radioGroups["g"] = "r1"; data.k?.invoke() }')
  end

  it 'a Segment valueChange, bare or bound, is called as declared' do
    expect(segment('@{h}', '(() -> Void)?')).not_to include('@{')
    expect(segment('@{h}', '(() -> Void)?')).to include('data.h?.invoke()')
    expect(segment('@{h}', '((Any) -> Void)?')).to include('data.h?.invoke(1)')
    expect(segment('h', '((Any) -> Void)?')).to include('data.h?.invoke(1)')
    # The legacy bare selector with no declaration stays a bare call (camelized).
    with_defs({}) do
      code = KjuiTools::Compose::Components::SegmentComponent.generate(
        { 'type' => 'Segment', 'id' => 's', 'items' => %w[a b], 'selectedIndex' => 0, 'valueChange' => 'on_seg' }, 0, Set.new
      )
      expect(code).to include('data.onSeg?.invoke()')
    end
  end

  it 'runs: one call per tap, in order, with the value' do
    skip "compile: #{KotlinCompiler.unavailable_reason}" if KotlinCompiler.unavailable_reason

    group_tap = radio({}, '((Any) -> Void)?')[/onClick = (\{ radioGroups.*\})/, 1]
    bound_seg = segment('@{h}', '((Any) -> Void)?')
    seg_taps = bound_seg.scan(/^\s*(data\.h\?\.invoke\(\d\))$/).flatten
    raise "no group tap in the emitted Radio" unless group_tap
    raise "no Segment calls: #{bound_seg}" if seg_taps.empty?

    source = <<~KT
      val log = mutableListOf<String>()
      class Data(val h: ((Any) -> Unit)? = { log += "h:$it" }, val k: (() -> Unit)? = { log += "k" })
      fun main() {
          val data = Data()
          val radioGroups = mutableMapOf<String, String>()
          val tap: () -> Unit = #{group_tap}
          tap()
          println("radio=$log selection=${radioGroups["g"]}")
          log.clear()
          #{seg_taps.join("\n    ")}
          println("segment=$log")
      }
    KT
    run = KotlinCompiler.run(source)
    expect(run.errors).to eq([])
    expect(run.output.lines.map(&:strip)).to eq(['radio=[h:r1, k] selection=r1', 'segment=[h:0, h:1]'])
  end
end
