# frozen_string_literal: true

require 'set'
require 'compose/components/switch_component'
require 'compose/components/radio_component'
require 'compose/components/scrollview_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'
require_relative '../../support/kotlin_compiler'

# Layout boxes the frame-parity inventory (2026-10-05, Android x web) found
# away from their declaration, on the codegen face. KotlinJsonUI Dynamic makes
# the same decisions in the same words (DynamicSwitchComponent.labelFillsRow,
# DynamicRadioComponent.rendersAsItem, DynamicScrollViewComponent).
RSpec.describe 'kjui codegen: layout boxes the frame-parity inventory found off' do
  before { KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {} }

  # kjui-labelled-switch-fills-the-parent-width-under-wrapcontent: a weighted
  # label makes Compose's Row take its whole max width, so under wrapContent a
  # labelled Switch drew 1280 wide where web wraps to label + switch.
  describe 'labelled Switch' do
    def switch(node)
      KjuiTools::Compose::Components::SwitchComponent
        .generate({ 'type' => 'Switch', 'label' => 'Sample' }.merge(node), 0, Set.new)
    end

    it 'gives the label no weight under a wrapContent width' do
      expect(switch('width' => 'wrapContent')).not_to include('Modifier.weight(1f)')
    end

    it 'gives the label no weight when no width is declared' do
      expect(switch({})).not_to include('Modifier.weight(1f)')
    end

    it 'weights the label when the width is decided (the Switch goes to the far edge)' do
      expect(switch('width' => 300)).to include('modifier = Modifier.weight(1f)')
      expect(switch('width' => 'matchParent')).to include('modifier = Modifier.weight(1f)')
      expect(switch('widthWeight' => 1)).to include('modifier = Modifier.weight(1f)')
      expect(switch('width' => 'wrap_content')).not_to include('Modifier.weight(1f)')
    end

    # kjui-dynamic-toggle-is-not-drawn-as-its-canonical-switch: Toggle is
    # Switch's alias and is drawn by the same emit, so it follows the same rule.
    it 'gives a Toggle the same rule' do
      toggle = ->(node) { KjuiTools::Compose::Components::SwitchComponent.generate({ 'type' => 'Toggle', 'label' => 'Sample' }.merge(node), 0, Set.new) }
      expect(toggle.call('width' => 'wrapContent')).not_to include('Modifier.weight(1f)')
      expect(toggle.call('width' => 'matchParent')).to include('modifier = Modifier.weight(1f)')
    end

    it 'weights the label for a trailing label too' do
      expect(switch('width' => 'matchParent', 'labelPosition' => 'trailing')).to include('modifier = Modifier.weight(1f)')
    end

    it 'compiles the label both ways (the unweighted one ends without a dangling comma)' do
      label = ->(node) { KjuiTools::Compose::Components::SwitchComponent.build_label_code({ 'type' => 'Switch', 'label' => 'Sample' }.merge(node), 1, Set.new) }
      expect(<<~KT).to compile_as_kotlin
        class TextUnit
        val Int.sp: TextUnit get() = TextUnit()
        interface Modifier { companion object : Modifier }
        interface RowScope { fun Modifier.weight(w: Float): Modifier = this }
        fun Text(text: String, fontSize: TextUnit? = null, modifier: Modifier = Modifier) {}
        fun RowScope.wrapped() {
        #{label.call('width' => 'wrapContent', 'fontSize' => 14)}
        #{label.call('width' => 300)}
        }
      KT
    end
  end

  # kjui-radio-without-a-label-draws-nothing: with no text and no options the
  # options branch emitted an empty Column, 0 high.
  describe 'Radio with no text' do
    def radio(node)
      KjuiTools::Compose::Components::RadioComponent
        .generate({ 'type' => 'Radio', 'id' => 'r', 'width' => 200 }.merge(node), 0, Set.new)
    end

    it 'draws its RadioButton' do
      expect(radio({})).to include('RadioButton(')
    end

    it 'stays a group when it lists options (control)' do
      out = radio('options' => %w[a b])
      expect(out).to include('Column(')
      expect(out).to include('"a"')
    end
  end

  describe 'ScrollView' do
    def scroll(node)
      KjuiTools::Compose::Components::ScrollViewComponent
        .generate({ 'type' => 'ScrollView', 'id' => 's' }.merge(node), 0, Set.new)
    end

    # kjui-scrollview-center-anchor-is-off-by-4: scrollBy reports
    # `delta − leftover` in float32; near 1e9 floats are 64 apart, so a 1200 px
    # extent came back as 1216 and the centre started 4 dp short.
    it 'scrolls to the end by 2^24, exact in float32' do
      code = scroll('defaultScrollAnchor' => 'center')[:code]
      expect(code).to include('.scrollBy(16777216f)')
      expect(code).not_to include('1e9f')
      expect(code).to include('.scrollBy(-consumed / 2f)')
    end

    it 'float32 is exact for 2^24 − extent and not for 1e9 − extent' do
      f32 = ->(x) { [x].pack('f').unpack1('f') }
      extent = 1200
      expect(16_777_216 - f32.call(16_777_216 - extent)).to eq(extent)
      expect(1_000_000_000 - f32.call(1_000_000_000 - extent)).to eq(1216)
    end

    # kjui-horizontal-scrollview-clamps-content-height-to-the-viewport: a
    # LazyRow measures its items with the viewport height as the max, so
    # content declaring 600 in a 200-high ScrollView was cut and centred.
    it 'puts a horizontal ScrollView\'s children in an unbounded, top-anchored Row' do
      result = scroll('orientation' => 'horizontal')
      expect(result[:code]).to include('Row(modifier = Modifier.wrapContentHeight(align = Alignment.Top, unbounded = true)) {')
      expect(result[:closing].scan('}').size).to eq(3)
      expect(result[:child_depth_offset]).to eq(1)
    end

    it 'wraps each paged child the same way' do
      result = scroll('orientation' => 'horizontal', 'paging' => true)
      expect(result[:child_wrapper][:open]).to eq('item { Row(modifier = Modifier.wrapContentHeight(align = Alignment.Top, unbounded = true)) {')
      expect(result[:child_wrapper][:close]).to eq('} }')
    end

    it 'compiles: the horizontal emit with the anchor, one child inside the Row' do
      result = scroll('orientation' => 'horizontal', 'defaultScrollAnchor' => 'center')
      expect(<<~KT).to compile_as_kotlin
        interface Modifier { companion object : Modifier }
        fun Modifier.testTag(t: String): Modifier = this
        class SemanticsPropertyReceiver { var testTagsAsResourceId: Boolean = false }
        fun Modifier.semantics(properties: SemanticsPropertyReceiver.() -> Unit): Modifier = this
        class Alignment { class Vertical; companion object { val Top = Vertical() } }
        fun Modifier.wrapContentHeight(align: Alignment.Vertical, unbounded: Boolean): Modifier = this
        class LazyListState { suspend fun scrollBy(d: Float): Float = d }
        fun rememberLazyListState(): LazyListState = LazyListState()
        fun Modifier.keyboardAvoidance(state: LazyListState, clearance: Int): Modifier = this
        fun LaunchedEffect(key: Any?, block: suspend () -> Unit) {}
        interface LazyListScope { fun item(content: () -> Unit) }
        fun LazyRow(state: LazyListState, modifier: Modifier, content: LazyListScope.() -> Unit) {}
        interface RowScope
        fun Row(modifier: Modifier, content: RowScope.() -> Unit) {}
        fun Child() {}
        fun host() {
        #{result[:code]}
        Child()
        #{result[:closing]}
        }
      KT
    end

    it 'leaves a vertical ScrollView as it was (control)' do
      result = scroll({})
      expect(result[:code]).not_to include('wrapContentHeight')
      expect(result[:closing].scan('}').size).to eq(2)
      expect(result).not_to have_key(:child_depth_offset)
    end
  end
end
