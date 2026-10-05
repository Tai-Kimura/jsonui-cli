# frozen_string_literal: true

require 'set'
require 'json'
require 'compose/compose_builder'
require 'compose/components/container_component'
require 'compose/helpers/modifier_builder'
require_relative '../support/kotlin_compiler'

# kjui-oversized-child-is-centred-and-cut-to-its-parent: a declared size is
# requiredWidth / requiredHeight, and an over-constrained required size is
# coerced and its content centred — a 300 child of a 200 Box drew at
# (−50, −50) whatever the gravity. The container now hands each child with a
# numeric size where it places it ([h, v] bias), and the size stage anchors
# the declared box there with an unbounded wrapContent. KotlinJsonUI Dynamic
# computes the same biases (DynamicContainerComponent.boxBias / columnBias /
# rowBias / axisBias); its device arms are OversizedChildPlacementTest.
RSpec.describe 'kjui codegen: an oversized child sits where its container places it' do
  def key = KjuiTools::Compose::Helpers::ModifierBuilder::OVERFLOW_BIAS_KEY

  def bias(layout, gravity, child, json_data = {})
    children = [child]
    KjuiTools::Compose::Components::ContainerComponent.send(:inject_overflow_bias!, children, layout, gravity, json_data)
    children.first[key]
  end

  let(:big) { { 'type' => 'View', 'width' => 300, 'height' => 300 } }

  describe 'a Box' do
    it 'puts the child at its corner by default' do
      expect(bias('Box', nil, big.dup)).to eq([-1.0, -1.0])
    end

    it 'centres it when its gravity is center' do
      expect(bias('Box', 'center', big.dup)).to eq([0.0, 0.0])
    end

    it 'puts it at the end when its gravity is right and bottom' do
      expect(bias('Box', %w[right bottom], big.dup)).to eq([1.0, 1.0])
    end

    # The wrapper follows what this Box's contentAlignment emit says, which
    # resolves each axis centre-first (resolve_box_alignment); the per-axis
    # main-axis rule of a Column / Row is start-first. A gravity naming both
    # left and centerHorizontal is where the two readings part.
    it 'reads the Box\'s emitted contentAlignment, not the start-first axis rule' do
      expect(bias('Box', %w[left centerHorizontal], big.dup)).to eq([0.0, -1.0])
    end

    it 'lets the child\'s own placement win' do
      expect(bias('Box', 'center', big.merge('alignRight' => true))).to eq([1.0, -1.0])
    end

    it 'leaves a bound placement to the container (decided at run time)' do
      expect(bias('Box', 'center', big.merge('alignRight' => '@{r}'))).to eq([0.0, 0.0])
    end
  end

  describe 'a Column or Row' do
    it 'takes a Column\'s cross-axis alignment and main-axis gravity' do
      expect(bias('Column', %w[centerHorizontal bottom], big.dup)).to eq([0.0, 1.0])
      expect(bias('Column', nil, big.merge('alignRight' => true))).to eq([1.0, -1.0])
    end

    it 'anchors a gravity-less rightToLeft Column at the trailing edge, as it places its children' do
      expect(bias('Column', nil, big.dup, 'direction' => 'rightToLeft')).to eq([1.0, -1.0])
    end

    it 'takes a Row\'s cross-axis alignment and main-axis gravity' do
      expect(bias('Row', %w[centerVertical right], big.dup)).to eq([1.0, 0.0])
      expect(bias('Row', nil, big.merge('alignBottom' => true))).to eq([-1.0, 1.0])
    end
  end

  it 'gives only a child with a numeric size the placement' do
    expect(bias('Box', 'center', { 'type' => 'View', 'width' => 'matchParent', 'height' => 'wrapContent' })).to be_nil
    expect(bias('Box', 'center', { 'type' => 'View', 'width' => '@{w}' })).to be_nil
    expect(bias('Box', 'center', { 'type' => 'View', 'width' => '120' })).to eq([0.0, 0.0])
  end

  describe 'the size stage' do
    def size(node) = KjuiTools::Compose::Helpers::ModifierBuilder.build_size(node, nil, Set.new)

    it 'puts the unbounded wrapContent in front of each required size' do
      expect(size(big.merge(key => [0.0, 1.0]))).to eq([
        '.wrapContentWidth(align = BiasAlignment.Horizontal(0.0f), unbounded = true)',
        '.requiredWidth(300.dp)',
        '.wrapContentHeight(align = BiasAlignment.Vertical(1.0f), unbounded = true)',
        '.requiredHeight(300.dp)'
      ])
    end

    it 'leaves a node the container did not place as it was (control)' do
      expect(size(big.dup)).to eq(['.requiredWidth(300.dp)', '.requiredHeight(300.dp)'])
    end

    it 'does the same for a frame' do
      out = size({ 'type' => 'View', 'frame' => { 'width' => 300, 'height' => 300 }, key => [1.0, -1.0] })
      expect(out.first).to eq('.wrapContentWidth(align = BiasAlignment.Horizontal(1.0f), unbounded = true)')
    end
  end

  # Ruling S (2026-10-05): a fixed-size row's children are placed in sequence
  # and overflow past its edge. Compose measured them against the space left,
  # so the child crossing the edge was coerced and every later one moved up
  # (padding 8: box_f at 172, web and iOS 208). KotlinJsonUI Dynamic:
  # mainAxisOverflowWrapper.
  describe 'a fixed-size row of fixed-size children' do
    def wrap(node) = KjuiTools::Compose::Components::ContainerComponent.send(:main_axis_overflow_wrapper, node, node['orientation'] == 'vertical' ? 'Column' : 'Row', node['child'])
    let(:kid) { { 'type' => 'View', 'width' => 40, 'height' => 40 } }

    it 'is measured unbounded along its axis, anchored by its gravity' do
      expect(wrap({ 'orientation' => 'horizontal', 'width' => 200, 'child' => [kid, kid] }))
        .to eq('.wrapContentWidth(align = BiasAlignment.Horizontal(-1.0f), unbounded = true)')
      expect(wrap({ 'orientation' => 'horizontal', 'width' => 200, 'gravity' => 'centerHorizontal', 'child' => [kid] }))
        .to eq('.wrapContentWidth(align = BiasAlignment.Horizontal(0.0f), unbounded = true)')
      expect(wrap({ 'orientation' => 'vertical', 'height' => 200, 'gravity' => 'bottom', 'child' => [kid] }))
        .to eq('.wrapContentHeight(align = BiasAlignment.Vertical(1.0f), unbounded = true)')
    end

    it 'keeps the bound for a distribution, a non-fixed row, or a child sized by weight or content' do
      expect(wrap({ 'orientation' => 'horizontal', 'width' => 200, 'distribution' => 'equalSpacing', 'child' => [kid] })).to be_nil
      expect(wrap({ 'orientation' => 'horizontal', 'width' => 'matchParent', 'child' => [kid] })).to be_nil
      expect(wrap({ 'orientation' => 'horizontal', 'width' => 200, 'child' => [kid, { 'type' => 'Label', 'text' => 't' }] })).to be_nil
      expect(wrap({ 'orientation' => 'horizontal', 'width' => 200, 'child' => [kid, kid.merge('weight' => 1)] })).to be_nil
    end

    it 'puts the wrapper innermost, after the padding' do
      layout = { 'type' => 'View', 'id' => 'row', 'orientation' => 'horizontal', 'width' => 200, 'height' => 200, 'padding' => 8,
                 'child' => [kid.merge('id' => 'a'), kid.merge('id' => 'b')] }
      code = KjuiTools::Compose::ComposeBuilder.new.send(:generate_component, layout, 0, 'Box')
      head = code.split('Row(').last.split(') {').first
      expect(head.index('.padding(')).to be < head.index('.wrapContentWidth(align = BiasAlignment.Horizontal(-1.0f), unbounded = true)')
    end
  end

  # User rulings 2026-10-05: fillEqually splits what a declared child leaves
  # (60 / 120 / 120); bottomToTop stacks from the bottom edge.
  describe 'distribution and direction rulings' do
    def build(layout) = KjuiTools::Compose::ComposeBuilder.new.send(:generate_component, layout, 0, 'Box')

    it 'gives a fillEqually child that declares its width no share' do
      kids = [{ 'type' => 'View', 'id' => 'a', 'width' => 60, 'height' => 40 },
              { 'type' => 'Label', 'id' => 'b', 'text' => 'B' }, { 'type' => 'Label', 'id' => 'c', 'text' => 'C' }]
      KjuiTools::Compose::Components::ContainerComponent.send(:distribute_main_axis!, kids, 'fillEqually', 'Row')
      expect(kids.map { |k| k['weight'] }).to eq([nil, 1, 1])
      expect(kids.first).not_to have_key('__distributionWeight')
    end

    it 'stacks a bottomToTop Column from the bottom edge' do
      code = build({ 'type' => 'View', 'id' => 'col', 'orientation' => 'vertical', 'direction' => 'bottomToTop',
                     'width' => 200, 'height' => 200, 'child' => [{ 'type' => 'View', 'id' => 'a', 'width' => 40, 'height' => 40 }] })
      expect(code).to include('verticalArrangement = Arrangement.Bottom')
      expect(code).to include('.wrapContentHeight(align = BiasAlignment.Vertical(1.0f), unbounded = true)')
    end

    it 'keeps the spacing on a bottomToTop Column, aligned to the bottom' do
      code = build({ 'type' => 'View', 'id' => 'col', 'orientation' => 'vertical', 'direction' => 'bottomToTop', 'spacing' => 8,
                     'child' => [{ 'type' => 'Label', 'id' => 'a', 'text' => 'A' }] })
      expect(code).to include('verticalArrangement = Arrangement.spacedBy(8.dp, Alignment.Bottom)')
      expect(code).not_to include('Arrangement.Bottom')
    end

    it 'stacks a rightToLeft Row from the right edge' do
      code = build({ 'type' => 'View', 'id' => 'row', 'orientation' => 'horizontal', 'direction' => 'rightToLeft',
                     'width' => 200, 'height' => 200, 'child' => [{ 'type' => 'View', 'id' => 'a', 'width' => 40, 'height' => 40 }] })
      expect(code).to include('horizontalArrangement = Arrangement.End')
      expect(code).to include('.wrapContentWidth(align = BiasAlignment.Horizontal(1.0f), unbounded = true)')
    end

    it 'lets a horizontal gravity place a rightToLeft Row (control)' do
      code = build({ 'type' => 'View', 'id' => 'row', 'orientation' => 'horizontal', 'direction' => 'rightToLeft', 'gravity' => 'left',
                     'child' => [{ 'type' => 'Label', 'id' => 'a', 'text' => 'A' }] })
      expect(code).not_to include('Arrangement.End')
    end

    it 'lets a vertical gravity place a bottomToTop Column (control)' do
      code = build({ 'type' => 'View', 'id' => 'col', 'orientation' => 'vertical', 'direction' => 'bottomToTop', 'gravity' => 'top',
                     'child' => [{ 'type' => 'Label', 'id' => 'a', 'text' => 'A' }] })
      expect(code).not_to include('Arrangement.Bottom')
    end
  end

  it 'compiles: a centred Box holding an oversized child, through the builder' do
    layout = { 'type' => 'View', 'id' => 'box', 'width' => 200, 'height' => 200, 'gravity' => 'center',
               'child' => [{ 'type' => 'View', 'id' => 'kid', 'width' => 300, 'height' => 300 }] }
    code = KjuiTools::Compose::ComposeBuilder.new.send(:generate_component, layout, 1, 'Box')
    expect(code).to include('.wrapContentWidth(align = BiasAlignment.Horizontal(0.0f), unbounded = true)')
    expect(<<~KT).to compile_as_kotlin
      interface Modifier { companion object : Modifier }
      val Int.dp: Int get() = this
      fun Modifier.requiredWidth(d: Int): Modifier = this
      fun Modifier.requiredHeight(d: Int): Modifier = this
      fun Modifier.testTag(t: String): Modifier = this
      class SemanticsPropertyReceiver { var testTagsAsResourceId: Boolean = false }
      fun Modifier.semantics(properties: SemanticsPropertyReceiver.() -> Unit): Modifier = this
      interface Alignment { companion object { val Center: Alignment = object : Alignment {} } }
      class BiasAlignment { class Horizontal(val bias: Float); class Vertical(val bias: Float) }
      fun Modifier.wrapContentWidth(align: BiasAlignment.Horizontal, unbounded: Boolean): Modifier = this
      fun Modifier.wrapContentHeight(align: BiasAlignment.Vertical, unbounded: Boolean): Modifier = this
      interface BoxScope
      fun Box(modifier: Modifier = Modifier, contentAlignment: Alignment? = null, content: BoxScope.() -> Unit = {}) {}
      fun BoxScope.host() {
      #{code}
      }
    KT
  end
end
