# frozen_string_literal: true

require 'set'
require 'compose/components/segment_component'
require_relative '../../support/kotlin_compiler'
require_relative '../../support/compose_stub_universe'

# Each Tab carries the testTag `<id>_tab_<n>` the Android driver's selectTab
# waits for (ActionExecutor.kt executeSelectTab); the Tabs were untagged, so a
# Segment could not be selected from a UI test (ticket jui-segment-tabs-carry-
# no-tab-ids-so-selecttab-cannot-reach-them). The Segment's own
# testTagsAsResourceId covers them.
RSpec.describe 'kjui: a Segment tags each Tab <id>_tab_<n>' do
  def emit(node)
    imports = Set.new
    code = KjuiTools::Compose::Components::SegmentComponent.generate(
      { 'type' => 'Segment', 'selectedIndex' => '@{idx}' }.merge(node), 0, imports
    )
    [code, imports]
  end

  def tags(code)
    code.scan(/modifier = Modifier\.testTag\((.+?)\),$/).flatten
  end

  it 'static items: one literal tag per Tab, in item order' do
    code, imports = emit('id' => 'style_segment', 'items' => %w[app book plain])
    expect(tags(code)).to eq(['"style_segment_tab_0"', '"style_segment_tab_1"', '"style_segment_tab_2"'])
    expect(imports).to include(:test_tag)
  end

  it 'numbers the Tabs as the selection does when an object item is dropped' do
    code, = emit('id' => 's', 'items' => ['a', { 'label' => 'x' }, 'b'])
    expect(tags(code)).to eq(['"s_tab_0"', '"s_tab_1"'])
  end

  it 'tags no Tab without an id, as the Segment gets no tag (control)' do
    code, = emit('items' => %w[a b])
    expect(tags(code)).to eq([])
    expect(code).not_to include('testTag')
  end

  it 'escapes the id as a Kotlin string ($ included)' do
    code, = emit('id' => 'a$b', 'items' => %w[a])
    expect(tags(code)).to eq(['"a\\$b_tab_0"'])
  end

  it 'the tagged Tabs compile' do
    functions = [{ 'id' => 'style_segment', 'items' => %w[app book] }].map.with_index do |node, i|
      code, = emit(node)
      "fun emitted#{i}(data: Data, viewModel: ViewModel) {\n#{code}\n}"
    end
    emitted = functions.join("\n\n")
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(emitted)}
      class Data(val idx: Int = 0)
      class ViewModel { fun updateData(values: Map<String, Any?>) {} }
      #{emitted}
    KOTLIN
  end
end
