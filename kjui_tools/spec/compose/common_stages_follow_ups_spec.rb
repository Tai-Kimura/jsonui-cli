# frozen_string_literal: true

require 'compose/compose_builder'
require 'compose/helpers/modifier_builder'
require 'core/tap_accessibility'
require 'core/image_accessibility'
require 'json'
require 'set'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# The follow-ups to docs/bugs/kjui-dynamic-components-that-skip-the-common-modifiers.md
# (B1–B8 and the Table item), each over its family: every emitter of a type,
# not the one branch the report named. The sweeps below were run before the
# change as their positive control; the counts are in the ticket.
RSpec.describe 'kjui codegen: the common stages, follow-ups' do
  emit = lambda do |node|
    comp = JSON.parse(JSON.generate(node))
    JsonUIShared::ImageAccessibility.annotate!(comp, source_path: 'p.json')
    JsonUIShared::TapAccessibility.annotate!(comp)
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@responsive_counter, 0)
    builder.instance_variable_set(:@responsive_functions, [])
    builder.send(:generate_component, comp, 0).to_s
  end
  count = ->(code, marker) { code.scan(marker).size }
  blocker = 'awaitPointerEvent(PointerEventPass.Initial).changes.forEach { it.consume() }'

  # Every type the codegen draws, and the other emitters of the types that
  # have more than one (a node per branch). The label's first word is the type.
  drawn = {
    'TextField' => { 'text' => '@{t}' }, 'TextField margins' => { 'text' => '@{t}', 'margins' => [1, 1, 1, 1] },
    'TextView' => { 'text' => '@{t}' }, 'TextView margins' => { 'text' => '@{t}', 'margins' => [1, 1, 1, 1] },
    'Button' => { 'text' => 't' }, 'Label' => { 'text' => 't' }, 'View' => {},
    'Image' => { 'srcName' => 'ic_a' }, 'NetworkImage' => { 'url' => 'https://example.invalid/x.png' },
    'CircleImage' => { 'srcName' => 'ic_a' },
    'Switch' => {}, 'Switch label' => { 'label' => 'L' }, 'Toggle' => {},
    'CheckBox' => {}, 'CheckBox label' => { 'label' => 'L' }, 'CheckBox icons' => { 'src' => 'ic_a', 'selectedIcon' => 'ic_b' },
    'Radio' => { 'text' => 'r' }, 'Radio options' => { 'options' => %w[a b], 'bind' => '@{sel}' },
    'Radio items' => { 'items' => %w[a b] },
    'Slider' => {}, 'Progress' => {}, 'Indicator' => {}, 'SelectBox' => { 'items' => %w[a b] },
    'Segment' => { 'items' => %w[a b] },
    'ScrollView' => { 'child' => [{ 'type' => 'Label', 'text' => 'c' }] },
    'SafeAreaView' => { 'child' => [{ 'type' => 'Label', 'text' => 'c' }] },
    'SafeAreaView constraints' => {
      'child' => [{ 'type' => 'Label', 'id' => 'a', 'text' => 'c' }, { 'type' => 'Label', 'text' => 'd', 'alignTopOfView' => 'a' }]
    },
    'Collection' => { 'items' => [] }, 'Collection flow' => { 'items' => [], 'layout' => 'flow' },
    'Collection paging' => { 'items' => '@{list}', 'layout' => 'horizontal', 'paging' => true },
    'Collection lazy-none' => { 'items' => [], 'lazy' => 'none' },
    'Collection lazy-none-horizontal' => { 'items' => [], 'lazy' => 'none', 'layout' => 'horizontal' },
    'Collection sections' => { 'sections' => [{ 'cell' => 'item_cell' }] },
    'WebView' => { 'url' => 'about:blank' }, 'Web' => { 'url' => 'about:blank' },
    'TabView' => { 'tabs' => [{ 'title' => 'a' }, { 'title' => 'b' }] }, 'Embed' => { 'screen' => 'missing' },
    'GradientView' => { 'gradient' => ['#FF0000', '#0000FF'] }, 'Blur' => {}, 'IconLabel' => { 'text' => 't' }
  }
  node_of = ->(label, extra = drawn[label]) { { 'type' => label.split.first }.merge(extra) }

  # --- B1 ------------------------------------------------------------------
  # The pager applied no clickable stage: no call, no `enabled`, no blocker,
  # no long press. Every Collection emitter now applies it, between the
  # background and the padding.
  it 'B1: every Collection emitter applies the clickable stage' do
    labels = drawn.keys.grep(/\ACollection/)
    expect(labels.size).to eq(6)
    missing = labels.flat_map do |label|
      node = node_of.call(label)
      plain = emit.call(node)
      {
        'onClick' => [node.merge('onClick' => '@{onTap}'), 'data.onTap?.invoke()'],
        'enabled' => [node.merge('onClick' => '@{onTap}', 'enabled' => false), '.semantics { disabled() }'],
        'userInteractionEnabled' => [node.merge('userInteractionEnabled' => false), blocker],
        'onLongPress' => [node.merge('onLongPress' => '@{onHold}'), 'data.onHold?.invoke()']
      }.reject { |_, (with, marker)| count.call(emit.call(with), marker) > count.call(plain, marker) }
       .map { |stage, _| "#{label} #{stage}" }
    end
    expect(missing).to be_empty
  end

  # --- B2 ------------------------------------------------------------------
  # offset and alpha sat after the background: the shadow, the circle, its
  # border and background stayed where they were and did not fade.
  it 'B2: CircleImage moves and fades with its decoration — offset, alpha after the size, before the shadow and the circle' do
    [{}, { 'width' => 40, 'height' => 40 }].each do |size|
      code = emit.call(node_of.call('CircleImage').merge(
                         'offsetX' => 3, 'offsetY' => 3, 'alpha' => 0.5, 'shadow' => '#000000|0|2|0.5|4',
                         'borderColor' => '#FF0000', 'borderWidth' => 2, 'background' => '#3366CC'
                       ).merge(size))
      order = [size.empty? ? '.size(48.dp)' : '.requiredWidth(40.dp)', '.absoluteOffset(x = 3.dp, y = 3.dp)',
               '.alpha(0.5f)', '.dropShadow(', '.clip(CircleShape)', '.border(2.dp,', '.background(Color(']
      at = order.map { |marker| code.index(marker) }
      expect(at).to all(be_a(Integer)), code
      expect(at).to eq(at.sort), "#{order.zip(at).inspect}\n#{code}"
    end
  end

  # --- B3 ------------------------------------------------------------------
  # A stage is emitted once. The TextView gave a declared height twice
  # (`.requiredHeight(53.dp).height(53.dp)`), and with margins the field
  # carried a second long-press detector and blocker under the Box's.
  it 'B3: no type or branch emits the size or a gesture stage twice' do
    doubled = drawn.keys.flat_map do |label|
      code = emit.call(node_of.call(label).merge('width' => 111, 'height' => 53, 'onLongPress' => '@{onHold}',
                                                 'userInteractionEnabled' => '@{u}'))
      {
        'height' => count.call(code, /\.(?:requiredHeight|height)\(53\.dp\)/),
        'width' => count.call(code, /\.(?:requiredWidth|width)\(111\.dp\)/),
        'long press' => count.call(code, 'data.onHold?.invoke()'),
        'blocker' => count.call(code, 'if (!((data.u ?: false))) {')
      }.select { |_, n| n > 1 }.map { |what, n| "#{label}: #{what} ×#{n}" }
    end
    expect(doubled).to be_empty
  end

  it 'B3: a TextView keeps each declared height, once' do
    { 120 => '.requiredHeight(120.dp)', 'matchParent' => '.fillMaxHeight()', 'wrapContent' => '.wrapContentHeight()' }
      .each do |height, marker|
        [nil, [1, 1, 1, 1]].each do |margins|
          node = { 'type' => 'TextView', 'text' => '@{t}', 'width' => 200, 'height' => height }
          node['margins'] = margins if margins
          code = emit.call(node)
          expect(count.call(code, marker)).to eq(1), code
          expect(code).not_to match(/\.height\(120\.dp\)/) if height == 120
        end
      end
    # no height: the text area's own 120dp
    expect(count.call(emit.call('type' => 'TextView', 'text' => '@{t}', 'width' => 200), '.height(120.dp)')).to eq(1)
  end

  # --- B5 ------------------------------------------------------------------
  # ComposeBuilder routes Toggle with Switch; ToggleComponent had no caller
  # outside its own specs.
  it 'B5: a Toggle is drawn by SwitchComponent, and ToggleComponent is gone' do
    lib = File.expand_path('../../lib', __dir__)
    expect(File).not_to exist(File.join(lib, 'compose/components/toggle_component.rb'))
    sources = Dir.glob(File.join(lib, '**', '*.rb')).map { |path| File.read(path) }
    # (DynamicToggleComponent is KotlinJsonUI's, named in a comment.)
    expect(sources.grep(/(?<!Dynamic)ToggleComponent\b|toggle_component/)).to be_empty
    %w[@{on} true].each do |on|
      expect(emit.call('type' => 'Toggle', 'isOn' => on, 'onValueChange' => '@{c}'))
        .to eq(emit.call('type' => 'Switch', 'isOn' => on, 'onValueChange' => '@{c}'))
    end
  end

  # --- B6 ------------------------------------------------------------------
  # onLongPress / onPan / onPinch are declared on `common`. The controls that
  # call onClick from their operation and the containers that build the click
  # alone (TabView, Embed, SafeAreaView) dropped all three, Button the pan and
  # the pinch. Each is at the click slot and shut like the other gestures
  # (gesture_gate): userInteractionEnabled or enabled false emits none, a
  # binding gates the call.
  gestures = {
    'long press' => [{ 'onLongPress' => '@{onHold}' }, 'data.onHold?.invoke()'],
    'pan' => [{ 'onPan' => '@{onDrag}' }, 'data.onDrag?.invoke()'],
    'pinch' => [{ 'onPinch' => '@{onZoom}' }, 'data.onZoom?.invoke()']
  }

  it 'B6: every type and branch carries its long press, pan and pinch' do
    missing = drawn.keys.product(gestures.keys).reject do |label, gesture|
      attrs, marker = gestures[gesture]
      count.call(emit.call(node_of.call(label).merge(attrs)), marker) == 1
    end
    expect(missing.map { |l, g| "#{l} #{g}" }).to be_empty
  end

  it 'B6: userInteractionEnabled or enabled false emits none, and a binding gates the call' do
    open = drawn.keys.product(gestures.keys).reject do |label, gesture|
      attrs, marker = gestures[gesture]
      node = node_of.call(label).merge(attrs)
      shut = [{ 'userInteractionEnabled' => false }, { 'enabled' => false }].all? do |gate|
        count.call(emit.call(node.merge(gate)), marker).zero?
      end
      # bound: the call sits under the gate — the conjunction is the
      # nearest condition before it (on the same line, or the long press's
      # `if (longPressed && …) {` just above).
      gated = emit.call(node.merge('enabled' => '@{on}', 'userInteractionEnabled' => '@{u}'))
      call_at = gated.index(marker)
      shut && call_at && gated[[call_at - 120, 0].max...call_at].include?('(data.u ?: false) && (data.on ?: false))')
    end
    expect(open.map { |l, g| "#{l} #{g}" }).to be_empty
  end

  # --- B7 ------------------------------------------------------------------
  # `enabled` reached the Scaffold's semantics and no tab: a disabled TabView
  # still switched. And the tab's index was put into the setter with
  # `gsub('it', index)`, so a bound name holding "it" was rewritten.
  it 'B7: a disabled TabView does not switch tabs — each item carries the enabled' do
    tabs = [{ 'title' => 'a' }, { 'title' => 'b' }, { 'title' => 'c' }]
    expect(count.call(emit.call('type' => 'TabView', 'tabs' => tabs, 'enabled' => false), 'enabled = false,')).to eq(3)
    expect(count.call(emit.call('type' => 'TabView', 'tabs' => tabs, 'enabled' => '@{on}'), 'enabled = (data.on ?: false),')).to eq(3)
    expect(emit.call('type' => 'TabView', 'tabs' => tabs)).not_to include('enabled =')
  end

  it 'B7: a tab writes the bound selection it names, whatever the name holds' do
    code = emit.call('type' => 'TabView', 'tabs' => [{ 'title' => 'a' }, { 'title' => 'b' }], 'selectedIndex' => '@{editIndex}')
    expect(code).to include('onClick = { viewModel.updateData(mapOf("editIndex" to 0)) },',
                            'onClick = { viewModel.updateData(mapOf("editIndex" to 1)) },')
    local = emit.call('type' => 'TabView', 'tabs' => [{ 'title' => 'a' }, { 'title' => 'b' }])
    expect(local).to include('onClick = { selectedTab = 0 },', 'onClick = { selectedTab = 1 },')
  end

  # --- B8 ------------------------------------------------------------------
  # The `shape =` argument and the corner clips wrote the layout's spelling:
  # a bound cornerRadius came out as `RoundedCornerShape(@{r}.dp)`.
  # SelectBox takes the radius as an Int argument (`cornerRadius = @{r}`).
  # The Dp form is `data.r.dp`, or `(data.r?.dp ?: 0.dp)` where the property
  # may be null (BoundValue.dp).
  corner_types = %w[Button TextField TextView WebView Blur GradientView]

  it 'B8: a bound cornerRadius is an expression on every type that writes its own corner' do
    corner_types.each do |label|
      bound = emit.call(node_of.call(label).merge('cornerRadius' => '@{r}'))
      expect(bound).not_to include('@{'), bound
      expect(bound).to match(/RoundedCornerShape\((?:data\.r\.dp|\(data\.r\?\.dp \?: 0\.dp\))\)/), bound
      static = emit.call(node_of.call(label).merge('cornerRadius' => 6))
      expect(static).to include('RoundedCornerShape(6.dp)'), static
    end
    select = emit.call(node_of.call('SelectBox').merge('cornerRadius' => '@{r}'))
    expect(select).to match(/cornerRadius = (?:data\.r|\(data\.r \?: 0\)),/), select
    expect(emit.call(node_of.call('SelectBox').merge('cornerRadius' => 6))).to include('cornerRadius = 6,')
  end

  it 'B8: no drawn type writes a bound value of any common attribute as layout text' do
    leaks = drawn.keys.flat_map do |label|
      code = emit.call(node_of.call(label).merge('cornerRadius' => '@{r}', 'enabled' => '@{on}', 'alpha' => '@{a}',
                                                 'offsetX' => '@{x}', 'userInteractionEnabled' => '@{u}'))
      code.lines.select { |line| line.include?('@{') }.map { |line| "#{label}: #{line.strip}" }
    end
    expect(leaks).to be_empty
  end

  # --- Table ---------------------------------------------------------------
  # A Table is drawn by CollectionComponent, and subcompose_node? read it as
  # always Lazy. It now answers as the Collection does — and a ScrollView
  # spelled canonically, which it did not list, read as eager: its parent
  # asked it for IntrinsicSize.Min, the shape that throws at run time.
  lazy_shapes = {
    'ScrollView' => { 'type' => 'ScrollView', 'child' => [{ 'type' => 'Label', 'text' => 'x' }] },
    'Scroll' => { 'type' => 'Scroll', 'child' => [{ 'type' => 'Label', 'text' => 'x' }] },
    'Table' => { 'type' => 'Table', 'items' => '@{rows}' },
    'Table lazy none' => { 'type' => 'Table', 'items' => '@{rows}', 'lazy' => 'none' },
    'Table flow' => { 'type' => 'Table', 'items' => '@{rows}', 'layout' => 'flow' },
    'Table paging' => { 'type' => 'Table', 'items' => '@{rows}', 'layout' => 'horizontal', 'paging' => true },
    'Table wrapContent' => { 'type' => 'Table', 'items' => '@{rows}', 'height' => 'wrapContent' },
    'Collection' => { 'type' => 'Collection', 'items' => '@{rows}' },
    'Collection lazy none' => { 'type' => 'Collection', 'items' => '@{rows}', 'lazy' => 'none' },
    'Collection flow' => { 'type' => 'Collection', 'items' => '@{rows}', 'layout' => 'flow' },
    'View over a ScrollView' => { 'type' => 'View', 'child' => [{ 'type' => 'ScrollView', 'child' => [{ 'type' => 'Label', 'text' => 'x' }] }] },
    'Label' => { 'type' => 'Label', 'text' => 'x' }
  }
  lazy_emit = /\b(?:Lazy(?:Column|Row|VerticalGrid|HorizontalGrid|VerticalStaggeredGrid|HorizontalStaggeredGrid)|HorizontalPager)\(/

  it 'Table: subcompose_node? answers as the emitter draws — Lazy exactly where the code is' do
    answers = lazy_shapes.map do |label, node|
      [label, KjuiTools::Compose::Helpers::ModifierBuilder.subcompose_node?(JSON.parse(JSON.generate(node))),
       emit.call(node).match?(lazy_emit)]
    end
    expect(answers.map(&:last).uniq.size).to eq(2) # both answers occur
    expect(answers.reject { |_, said, drew| said == drew }.map(&:first)).to be_empty
  end

  it 'Table: no parent asks a Lazy child for IntrinsicSize.Min' do
    crash = lazy_shapes.flat_map do |label, kid|
      %w[vertical horizontal].map do |orientation|
        axis = orientation == 'vertical' ? 'width' : 'height'
        code = emit.call('type' => 'View', 'orientation' => orientation, 'child' => [kid.merge(axis => 'matchParent')])
        "#{label} in #{orientation}" if code.match?(lazy_emit) && code.include?('IntrinsicSize.Min')
      end
    end.compact
    expect(crash).to be_empty
    # and an eager one still gets it (the arm is not blind)
    eager = emit.call('type' => 'View', 'orientation' => 'vertical',
                      'child' => [lazy_shapes['Table flow'].merge('width' => 'matchParent')])
    expect(eager).to include('IntrinsicSize.Min')
  end

  it 'Table: a Lazy node under `children` counts, as under `child`' do
    builder = KjuiTools::Compose::Helpers::ModifierBuilder
    scroll = lazy_shapes['ScrollView']
    expect(builder.subcompose_node?('type' => 'View', 'children' => [scroll])).to be(true)
    expect(builder.subcompose_node?('type' => 'View', 'child' => scroll)).to be(true)
    expect(builder.subcompose_node?('type' => 'View', 'children' => [{ 'type' => 'Label' }])).to be(false)
  end

  # --- compile --------------------------------------------------------------
  # Every type and branch with the gestures, a bound enabled / interaction
  # gate, a bound cornerRadius and (TabView) a bound selection whose name holds
  # "it" — type-checked against ComposeStubUniverse.common_stages: "well-typed
  # Kotlin", not "valid Compose".
  it 'compiles every type with the gestures, the bound gates and a bound cornerRadius' do
    # The emitters that call Compose names the stub universe does not declare
    # (ConstraintLayout, FlowRow, HorizontalPager, CollectionStack) are not in
    # this run — read off the emission, and named: no compile arm reaches them.
    unstubbed = /\b(?:ConstraintLayout|FlowRow|HorizontalPager|CollectionStack)\b/
    uncovered = drawn.keys.select { |label| emit.call(node_of.call(label)).match?(unstubbed) }
    expect(uncovered).to eq(['SafeAreaView constraints', 'Collection flow', 'Collection paging', 'Collection sections'])
    functions = (drawn.keys - uncovered).each_with_index.map do |label, i|
      node = node_of.call(label).merge('onLongPress' => '@{onHold}', 'onPan' => '@{onDrag}', 'onPinch' => '@{onZoom}',
                                       'enabled' => '@{on}', 'userInteractionEnabled' => '@{u}', 'cornerRadius' => '@{r}')
      node['selectedIndex'] = '@{editIndex}' if label == 'TabView'
      "// #{label}\nfun emitted#{i}(data: Data, viewModel: ViewModel) {\n#{emit.call(node)}\n}"
    end
    emitted = functions.join("\n\n")
    expect(emitted.scan('data.onZoom?.invoke()').size).to eq(drawn.size - uncovered.size)
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(emitted)}
      class Data(
          val onHold: (() -> Unit)? = null, val onDrag: (() -> Unit)? = null, val onZoom: (() -> Unit)? = null,
          val on: Boolean = true, val u: Boolean? = null, val r: Int = 6, val editIndex: Int = 0,
          val t: String = "", val sel: String = "", val selectedRadiogroup: String = "",
          val list: List<Any> = emptyList()
      )
      class ViewModel { fun updateData(values: Map<String, Any?>) {} }
      #{emitted}
    KOTLIN
  end
end
