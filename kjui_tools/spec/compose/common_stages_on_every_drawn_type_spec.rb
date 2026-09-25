# frozen_string_literal: true

require 'compose/compose_builder'
require 'core/tap_accessibility'
require 'core/image_accessibility'
require 'json'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# The common stages — attribute_definitions.json `common`: id (testTag),
# margins, width/height, offsetX/Y, alpha, shadow, background, cornerRadius,
# borderColor/borderWidth, onClick, enabled, userInteractionEnabled, paddings —
# reach the Compose emission of every type kjui draws. Ruling (a) of
# docs/bugs/kjui-dynamic-components-that-skip-the-common-modifiers.md: the SSoT
# declares them on `common`, so they apply to every type.
#
# RANGE is that ticket's final range: the 96 (type, stage) cells kjui_tools at
# 24f7fad0 dropped, as measured by
# docs/bugs/fixtures/kjui-stage-family/kstage_codegen.rb (md5 5bd0e815…) and
# tabled by family_table.py there. BASE and STAGES are that script's nodes and
# attributes, so a cell here and a row there name the same emission.
#
# A cell holds when the stage's own modifier, spelled with the stage's values,
# occurs MORE often with the stage than without it. "The emission changed" is
# not enough — a background alone changes it, which is why cornerRadius is
# judged against the background stage and enabled against the clickable
# stage, as the script judges them. Margins are judged by position: the outer
# spacing sits before (outside) the size, or it pads the inside of it — two
# of the 96 cells (CircleImage, SafeAreaView) emitted them, inside.
RSpec.describe 'kjui codegen: the common stages reach every type it draws' do
  base = {
    'TextField' => { 'text' => '@{t}' }, 'Button' => { 'text' => 't', 'onClick' => '@{onOther}' },
    'Image' => { 'srcName' => 'ic_star_filled' }, 'NetworkImage' => { 'url' => 'https://example.invalid/x.png' },
    'CircleImage' => { 'srcName' => 'ic_star_filled' }, 'Switch' => {}, 'CheckBox' => {},
    'Radio' => { 'text' => 'r' }, 'Slider' => {}, 'Progress' => {}, 'Indicator' => {},
    'SelectBox' => { 'items' => %w[a b] }, 'Segment' => { 'items' => %w[a b] }, 'Toggle' => {},
    'ScrollView' => { 'child' => [{ 'type' => 'Label', 'text' => 'c' }] },
    'SafeAreaView' => { 'child' => [{ 'type' => 'Label', 'text' => 'c' }] },
    'Collection' => { 'items' => [] }, 'WebView' => { 'url' => 'about:blank' }, 'Web' => { 'url' => 'about:blank' },
    'TabView' => { 'tabs' => [{ 'title' => 'a' }, { 'title' => 'b' }] }, 'Embed' => { 'screen' => 'missing' },
    'GradientView' => { 'gradient' => ['#FF0000', '#0000FF'] }, 'Blur' => {}, 'IconLabel' => { 'text' => 't' },
    'TextView' => { 'text' => '@{t}' }
  }

  stages = {
    'testTag' => { 'id' => 'n' }, 'margins' => { 'margins' => [7, 7, 7, 7] }, 'size' => { 'width' => 111, 'height' => 53 },
    'offset' => { 'offsetX' => 3, 'offsetY' => 3 }, 'alpha' => { 'alpha' => 0.5 },
    'shadow' => { 'shadow' => '#000000|0|2|0.5|4' }, 'background' => { 'background' => '#3366CC' },
    'cornerRadius' => { 'background' => '#3366CC', 'cornerRadius' => 6 },
    'border' => { 'borderColor' => '#FF0000', 'borderWidth' => 2 }, 'clickable' => { 'onClick' => '@{onTap}' },
    'enabled' => { 'onClick' => '@{onTap}', 'enabled' => false },
    'userInteraction' => { 'userInteractionEnabled' => false }, 'padding' => { 'paddings' => [5, 5, 5, 5] }
  }
  against = { 'cornerRadius' => 'background', 'enabled' => 'clickable' }

  blocker = 'awaitPointerEvent(PointerEventPass.Initial).changes.forEach { it.consume() }'
  # Each stage's own modifier with the stage's own values. Every one must
  # occur more often with the stage than in what it is judged against.
  markers = {
    'testTag' => ['.testTag("n")'],
    'margins' => ['.padding(top = 7.dp, end = 7.dp, bottom = 7.dp, start = 7.dp)'],
    'size' => ['.requiredWidth(111.dp)', '.requiredHeight(53.dp)'],
    'offset' => ['.absoluteOffset(x = 3.dp, y = 3.dp)'],
    'alpha' => ['.alpha(0.5f)'],
    'shadow' => ['.dropShadow(shape = ',
                 'shadow = Shadow(radius = 4.0.dp, color = Color(android.graphics.Color.parseColor("#000000")), ' \
                 'offset = DpOffset(0.0.dp, 2.0.dp), alpha = 0.5f))'],
    'background' => ['.background(Color(android.graphics.Color.parseColor("#3366CC")))'],
    'cornerRadius' => ['.clip(RoundedCornerShape(6.dp))'],
    'border' => ['.border(2.dp, Color(android.graphics.Color.parseColor("#FF0000")), RectangleShape)'],
    'clickable' => [/\.clickable(?:\([^)]*\))? \{ data\.onTap\?\.invoke\(\) \}/],
    'enabled' => [/\.clickable\(enabled = false[,)]/, '.semantics { disabled() }'],
    'userInteraction' => [blocker],
    'padding' => ['.padding(top = 5.dp, end = 5.dp, bottom = 5.dp, start = 5.dp)']
  }

  all_but_ui = %w[testTag margins size offset alpha shadow background cornerRadius border clickable enabled padding]
  range = {
    'TextField' => %w[shadow], 'Button' => %w[shadow],
    'Image' => %w[shadow background cornerRadius border], 'NetworkImage' => %w[shadow],
    'CircleImage' => %w[margins size shadow cornerRadius],
    'Switch' => %w[size shadow background cornerRadius border clickable],
    'CheckBox' => %w[size shadow background cornerRadius border clickable],
    'Radio' => %w[testTag size offset alpha shadow background cornerRadius border clickable enabled userInteraction padding],
    'Slider' => %w[shadow background cornerRadius border], 'Progress' => %w[shadow background cornerRadius border],
    'Indicator' => %w[size shadow background cornerRadius border], 'SelectBox' => %w[shadow],
    'Segment' => %w[shadow cornerRadius border clickable],
    'Toggle' => %w[size shadow background cornerRadius border clickable],
    'ScrollView' => %w[shadow], 'SafeAreaView' => %w[margins alpha shadow clickable enabled], 'Collection' => %w[shadow],
    'WebView' => %w[shadow border], 'Web' => %w[shadow cornerRadius],
    'TabView' => all_but_ui,
    'Embed' => %w[alpha shadow background cornerRadius border clickable enabled],
    'GradientView' => %w[shadow background border], 'Blur' => %w[shadow border], 'IconLabel' => %w[shadow],
    'TextView' => %w[shadow]
  }

  # The other emitters of the same types — the table's node reaches one
  # branch each, and every branch of a type draws that type.
  variants = {
    'Switch with a label' => { 'type' => 'Switch', 'label' => 'L' },
    'Toggle with a label' => { 'type' => 'Toggle', 'label' => 'L' },
    'CheckBox with a label' => { 'type' => 'CheckBox', 'label' => 'L' },
    'CheckBox with icons' => { 'type' => 'CheckBox', 'src' => 'ic_a', 'selectedIcon' => 'ic_b' },
    'Radio options' => { 'type' => 'Radio', 'options' => %w[a b], 'bind' => '@{sel}' },
    'Radio items' => { 'type' => 'Radio', 'items' => %w[a b] },
    'Collection flow' => { 'type' => 'Collection', 'items' => [], 'layout' => 'flow' },
    'Collection paging' => { 'type' => 'Collection', 'items' => '@{list}', 'layout' => 'horizontal', 'paging' => true },
    'Collection lazy none' => { 'type' => 'Collection', 'items' => [], 'lazy' => 'none' },
    'Collection lazy none horizontal' => { 'type' => 'Collection', 'items' => [], 'lazy' => 'none', 'layout' => 'horizontal' },
    'Collection sections' => { 'type' => 'Collection', 'sections' => [{ 'cell' => 'item_cell' }] },
    'SafeAreaView with constraints' => {
      'type' => 'SafeAreaView',
      'child' => [{ 'type' => 'Label', 'id' => 'a', 'text' => 'c' }, { 'type' => 'Label', 'text' => 'd', 'alignTopOfView' => 'a' }]
    },
    'TextField with margins' => { 'type' => 'TextField', 'text' => '@{t}', 'margins' => [1, 1, 1, 1] },
    'TextView with margins' => { 'type' => 'TextView', 'text' => '@{t}', 'margins' => [1, 1, 1, 1] }
  }

  emit = lambda do |node|
    comp = JSON.parse(JSON.generate(node))
    JsonUIShared::ImageAccessibility.annotate!(comp, source_path: 'p.json')
    JsonUIShared::TapAccessibility.annotate!(comp)
    KjuiTools::Compose::ComposeBuilder.new.send(:generate_component, comp, 0).to_s
  end
  count = ->(code, marker) { code.scan(marker).size }

  it 'holds the 96 cells of the final range, over 25 types' do
    expect(range.size).to eq(25)
    expect(range.values.sum(&:size)).to eq(96)
    expect(range.values.flatten - stages.keys).to be_empty
  end

  size_at = ->(code) { code.index(/\.requiredWidth\(111\.dp\)|\.requiredHeight\(53\.dp\)|\.size\(111\.dp/) }

  # One example per cell: the red one names the type and the stage. Margins
  # are declared with the size and must come out before it.
  cell_arm = lambda do |label, node, stage|
    it "#{label} emits #{stage}" do
      subject = stage == 'margins' ? node.merge(stages['size']) : node
      with = emit.call(subject.merge(stages[stage]))
      ref = emit.call(against[stage] ? subject.merge(stages[against[stage]]) : subject)
      if stage == 'margins'
        margin_at = with.index(markers['margins'].first)
        expect(margin_at).not_to be_nil, "#{label}: no margins\n#{with}"
        expect(size_at.call(with)).not_to be_nil, "#{label}: no size\n#{with}"
        expect(margin_at).to be < size_at.call(with), "#{label}: the margins sit inside the size\n#{with}"
      end
      markers[stage].each do |marker|
        expect(count.call(with, marker)).to be > count.call(ref, marker),
                                            "#{label} #{stage}: #{marker.inspect} occurs " \
                                            "#{count.call(with, marker)} times with the stage, " \
                                            "#{count.call(ref, marker)} without\n#{with}"
      end
    end
  end

  range.each do |type, cells|
    cells.each { |stage| cell_arm.call(type, { 'type' => type }.merge(base[type]), stage) }
  end

  variants.each do |label, node|
    range[node['type']].each { |stage| cell_arm.call(label, node, stage) }
  end

  # Margins are the outer spacing on every type that draws both: before the
  # size, never inside it (the two INSIDE cells above, and no other).
  it 'puts the margins outside the size on every type and branch' do
    nodes = base.map { |type, extra| [type, { 'type' => type }.merge(extra)] } + variants.to_a
    inside = nodes.map do |label, node|
      code = emit.call(node.merge(stages['size'], stages['margins']))
      margin_at = code.index(markers['margins'].first)
      [label, margin_at, size_at.call(code)]
    end
    expect(inside.select { |_, m, z| m.nil? || z.nil? }.map(&:first)).to be_empty
    expect(inside.reject { |_, m, z| m < z }.map(&:first)).to be_empty
  end

  # SafeAreaView's background and click cover the whole node: both before
  # the system-bar padding (after it they would stop at the insets), as the
  # dynamic component orders them — on both of its helpers.
  it 'puts SafeAreaView background and click before the system-bar padding' do
    [base['SafeAreaView'], variants['SafeAreaView with constraints'].reject { |k, _| k == 'type' }].each do |extra|
      code = emit.call({ 'type' => 'SafeAreaView' }.merge(extra, stages['background'], stages['clickable']))
      bars = code.index('Modifier.systemBarsPadding()')
      expect(bars).not_to be_nil, code
      expect(code.index('.background(Color(')).to be < bars
      expect(code.index('.clickable')).to be < bars
    end
  end

  # A shadow inside a clip is cut away with it: the shadow sits outside every
  # clip of the chain (CircleImage's circle, and the corner clip).
  it 'puts every shadow outside the clips' do
    range.select { |_, cells| cells.include?('shadow') }.each_key do |type|
      code = emit.call({ 'type' => type }.merge(base[type]).merge(stages['shadow'], stages['cornerRadius']))
      shadow = code.index('.dropShadow(')
      clip = code.index('.clip(')
      expect(shadow).not_to be_nil, type
      expect(shadow).to be < clip, "#{type}: the shadow follows a clip\n#{code}" if clip
    end
  end

  # The outline of a shadow is the shape the component draws, where that is
  # not the node's own box: CircleImage is clipped to a circle; Button,
  # TextField / TextView (CustomTextField) and SelectBox draw rounded corners
  # of their own when no cornerRadius is declared — Button its `shape =`
  # argument, CustomTextField `shape ?: RoundedCornerShape(Configuration
  # .TextField.defaultCornerRadius.dp)`, SelectBox `cornerRadius: Int = 8`
  # (KotlinJsonUI library). A RectangleShape shadow would sit square behind
  # them. With cornerRadius declared, the drawn shape is the declared one.
  outlines = {
    'CircleImage' => %w[CircleShape CircleShape],
    'Button' => ['RoundedCornerShape(Configuration.Button.defaultCornerRadius.dp)', 'RoundedCornerShape(6.dp)'],
    'TextField' => ['RoundedCornerShape(Configuration.TextField.defaultCornerRadius.dp)', 'RoundedCornerShape(6.dp)'],
    'TextView' => ['RoundedCornerShape(Configuration.TextField.defaultCornerRadius.dp)', 'RoundedCornerShape(6.dp)'],
    'SelectBox' => ['RoundedCornerShape(8.dp)', 'RoundedCornerShape(6.dp)']
  }
  # Where the emit names the drawn shape itself, it is the same one.
  drawn = {
    'Button' => ['shape = RoundedCornerShape(Configuration.Button.defaultCornerRadius.dp)', 'shape = RoundedCornerShape(6.dp)'],
    'TextField' => [nil, 'shape = RoundedCornerShape(6.dp)'], 'TextView' => [nil, 'shape = RoundedCornerShape(6.dp)'],
    'SelectBox' => [nil, 'cornerRadius = 6,'], 'CircleImage' => ['.clip(CircleShape)', '.clip(CircleShape)']
  }
  outlines.each do |type, (plain, rounded)|
    [[plain, {}, 0], [rounded, { 'cornerRadius' => 6 }, 1]].each do |shape, radius, i|
      it "#{type} casts its shadow in #{shape}#{radius.empty? ? '' : ' (cornerRadius 6)'}" do
        code = emit.call({ 'type' => type }.merge(base[type], stages['shadow'], radius))
        expect(code).to include(".dropShadow(shape = #{shape}, ")
        expect(code).to include(drawn[type][i]) if drawn[type][i]
      end
    end
  end

  # The components that emit the blocker ahead of their margins take the
  # click alone: one click and one blocker. `enabled` stays where it was —
  # the control's own parameter on Switch, Toggle, CheckBox and Segment (no
  # disabled() semantics added), the disabled() semantics where the node has
  # no such parameter.
  gated = {
    'Switch' => 0, 'Toggle' => 0, 'CheckBox' => 0, 'Segment' => 0,
    'Radio' => 1, 'TabView' => 1, 'Embed' => 1, 'SafeAreaView' => 1
  }
  gated.each do |type, disabled|
    it "#{type} carries one click, one blocker and #{disabled} disabled() under every gate" do
      code = emit.call({ 'type' => type }.merge(base[type], stages['clickable'], stages['userInteraction'],
                                                 'enabled' => false))
      expect(count.call(code, '.clickable(')).to eq(1)
      expect(count.call(code, blocker)).to eq(1)
      expect(count.call(code, 'disabled()')).to eq(disabled)
    end
  end

  %w[Switch Toggle CheckBox Segment].each do |type|
    it "#{type} under enabled false alone keeps it on the control's parameter" do
      code = emit.call({ 'type' => type }.merge(base[type], 'enabled' => false))
      expect(code).to include('enabled = false')
      expect(code).not_to include('.clickable')
      expect(code).not_to include('disabled()')
    end
  end

  # The emits, whole, with every stage declared at once, type-check against
  # Compose's names and types (spec/support/compose_stub_universe.rb
  # `common_stages`). ⚠️ Against stubs: this says "well-typed Kotlin", not
  # "valid Compose" (see emitted_kotlin_reaches_a_compiler_spec.rb).
  it 'compiles every type with every stage declared' do
    every = stages.values.reduce({}) { |acc, attrs| acc.merge(attrs) }
    compiled = base.map { |type, extra| [type, { 'type' => type }.merge(extra)] }.to_h
    compiled.merge!(variants.slice('Switch with a label', 'CheckBox with a label', 'CheckBox with icons',
                                   'Radio options', 'Radio items'))
    # the TextField / TextView bases reach their margins branch with every
    # stage; these reach the other one
    compiled['TextField without margins'] = { 'type' => 'TextField', 'text' => '@{t}', '-' => %w[margins] }
    compiled['TextView without margins'] = { 'type' => 'TextView', 'text' => '@{t}', '-' => %w[margins] }
    functions = compiled.map.with_index do |(label, node), i|
      drop = node['-'] || []
      attrs = node.reject { |k, _| k == '-' }.merge(every).reject { |k, _| drop.include?(k) }
      "// #{label}\nfun emitted#{i}(data: Data, viewModel: ViewModel) {\n#{emit.call(attrs)}\n}"
    end
    emitted = functions.join("\n\n")
    expect(emitted.scan('.dropShadow(').size).to be >= compiled.size
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(emitted)}
      class Data(
          val onTap: (() -> Unit)? = null, val onOther: (() -> Unit)? = null,
          val t: String = "", val nIsFocused: Boolean = false,
          val sel: String = "", val selectedRadiogroup: String = ""
      )
      class ViewModel { fun updateData(values: Map<String, Any?>) {} }
      #{emitted}
    KOTLIN
  end
end
