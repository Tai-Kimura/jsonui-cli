# frozen_string_literal: true

require 'json'
require 'set'
require 'compose/compose_builder'
require 'core/type_synonyms'
require_relative '../support/kotlin_compiler'

# App components standing in for ones in a project's components/extensions
# directory.
module ParentScopeProbes
  # The `kjui g converter` scaffold's kind: its own size, padding and margins,
  # no weight and no alignment in the parent (it builds its modifiers with
  # build_size(json, nil) and never calls build_weight / build_alignment).
  class Bare
    def self.generate(_json, _depth, _imports, _parent)
      'ProbeBar(modifier = Modifier.requiredHeight(12.dp).padding(start = 8.dp))'
    end
  end

  # Weights and aligns itself.
  class Owns
    def self.generate(_json, _depth, _imports, _parent)
      'ProbeOwns(modifier = Modifier.weight(1f).align(Alignment.Top))'
    end
  end
end

# kjui-custom-component-converter-drops-weight: an app's component given
# `weight` in a Row / Column got no `.weight(...)` — the scaffold never
# applied it — so it was measured at its own minimum (a Canvas bar ~0 wide)
# where iOS (sjui's scaffold calls apply_modifiers) filled the slot. Its
# alignment in the parent (alignTop / centerVertical in a Row, alignLeft /
# centerHorizontal in a Column, the Box ones) was dropped the same way: the
# census of the SSoT's common attributes on a built-in View and on a
# scaffolded component (2026-10-03) found exactly these two families missing.
#
# Both are the parent's scope, so kjui applies them around the component, in
# the Box its common stages already use; with a weight the Box hands its slot
# to the component as its minimum (propagateMinConstraints), so a converter an
# app keeps from before fills it without being re-scaffolded.
RSpec.describe 'kjui codegen: an app component\'s weight and alignment in its parent' do
  probes = { 'ProbeBar' => ParentScopeProbes::Bare, 'ProbeOwns' => ParentScopeProbes::Owns }

  before do
    allow(KjuiTools::Compose::ComposeBuilder).to receive(:custom_component_class) { |t| probes[t] }
    allow(KjuiTools::Compose::ComposeBuilder).to receive(:custom_component_types).and_return(probes.keys)
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    JsonUIShared::TypeSynonyms.app_types = probes.keys
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  after do
    JsonUIShared::TypeSynonyms.app_types = []
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  def emit(node)
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@required_imports, Set.new)
    builder.instance_variable_set(:@responsive_counter, 0)
    builder.instance_variable_set(:@responsive_functions, [])
    builder.send(:generate_component, JSON.parse(JSON.generate(node)), 0).to_s
  end

  def row(child, orientation = 'horizontal')
    parent = { 'type' => 'View', 'child' => [child] }
    parent['orientation'] = orientation if orientation
    parent
  end

  it 'weights the ticket\'s bar: a Box with the weight hands the slot to the component as its minimum' do
    code = emit(row({ 'type' => 'ProbeBar', 'id' => 'bar', 'weight' => 1, 'height' => 12, 'leftMargin' => 8 }))
    box = code[/Box\(\n\s*modifier = Modifier\n\s*\.weight\(1f\),\n\s*propagateMinConstraints = true\n\s*\) \{\n\s*ProbeBar\(/]
    expect(box).not_to be_nil, code
  end

  it 'weights by heightWeight in a Column' do
    code = emit(row({ 'type' => 'ProbeBar', 'heightWeight' => 2 }, 'vertical'))
    expect(code).to include('.weight(2f)').and include('propagateMinConstraints = true')
  end

  it 'aligns it in its parent, without handing it the slot when it has no weight' do
    code = emit(row({ 'type' => 'ProbeBar', 'alignTop' => true }))
    expect(code).to include('.align(Alignment.Top)')
    expect(code).not_to include('propagateMinConstraints')
  end

  it 'leaves a weight and an alignment the component applies itself to it' do
    code = emit(row({ 'type' => 'ProbeOwns', 'weight' => 1, 'alignTop' => true }))
    expect(code.scan('.weight(').size).to eq(1)
    expect(code.scan('.align(').size).to eq(1)
    expect(code).not_to include('Box(')
  end

  it 'adds nothing outside a Row / Column / Box (no parent scope to weight in)' do
    expect(emit({ 'type' => 'ProbeBar', 'weight' => 1 })).not_to include('.weight(')
  end

  # BoxScope has no weight: a weight there did not compile. A built-in View
  # in a Box gets none either (the census's control below).
  it 'gives no weight in a Box, and still aligns there' do
    code = emit(row({ 'type' => 'ProbeBar', 'weight' => 1, 'alignBottom' => true }, nil))
    expect(code).not_to include('.weight(')
    expect(code).not_to include('propagateMinConstraints')
    expect(code).to include('.align(')
  end

  # Compiled, against Compose's scopes as Compose types them — each marked
  # @LayoutScopeMarker (a DslMarker), so inside a nested scope an outer
  # scope's members are not reachable implicitly (without it a Column's align
  # inside a BoxScope resolved to the outer ColumnScope and compiled here
  # while it failed in an app). RowScope and
  # ColumnScope have `weight`, BoxScope has none; a Row child aligns by an
  # Alignment.Vertical, a Column child by an Alignment.Horizontal, a Box child
  # by an Alignment. A weight in a Box, or a Column's alignment in a Row, does
  # not compile here as it does not in an app.
  def scopes
    <<~KT
      open class Modifier { companion object : Modifier() }
      class Dp(val value: Float)
      val Int.dp: Dp get() = Dp(toFloat())
      fun Modifier.fillMaxWidth(): Modifier = this
      fun Modifier.fillMaxHeight(): Modifier = this
      fun Modifier.requiredHeight(height: Dp): Modifier = this
      fun Modifier.padding(start: Dp = 0.dp, end: Dp = 0.dp): Modifier = this
      interface Alignment {
          interface Vertical
          interface Horizontal
          companion object {
              val Top: Vertical = object : Vertical {}
              val Bottom: Vertical = object : Vertical {}
              val CenterVertically: Vertical = object : Vertical {}
              val Start: Horizontal = object : Horizontal {}
              val End: Horizontal = object : Horizontal {}
              val CenterHorizontally: Horizontal = object : Horizontal {}
              val TopStart: Alignment = object : Alignment {}
              val TopEnd: Alignment = object : Alignment {}
              val BottomStart: Alignment = object : Alignment {}
              val BottomEnd: Alignment = object : Alignment {}
              val CenterStart: Alignment = object : Alignment {}
              val CenterEnd: Alignment = object : Alignment {}
              val Center: Alignment = object : Alignment {}
          }
      }
      class BiasAlignment(val horizontalBias: Float, val verticalBias: Float) : Alignment
      @DslMarker annotation class LayoutScopeMarker
      @LayoutScopeMarker interface RowScope {
          fun Modifier.weight(weight: Float, fill: Boolean = true): Modifier = this
          fun Modifier.align(alignment: Alignment.Vertical): Modifier = this
      }
      @LayoutScopeMarker interface ColumnScope {
          fun Modifier.weight(weight: Float, fill: Boolean = true): Modifier = this
          fun Modifier.align(alignment: Alignment.Horizontal): Modifier = this
      }
      @LayoutScopeMarker interface BoxScope { fun Modifier.align(alignment: Alignment): Modifier = this }
      fun Row(modifier: Modifier = Modifier, content: RowScope.() -> Unit) { object : RowScope {}.content() }
      fun Column(modifier: Modifier = Modifier, content: ColumnScope.() -> Unit) { object : ColumnScope {}.content() }
      fun Box(modifier: Modifier = Modifier, contentAlignment: Alignment = Alignment.TopStart,
              propagateMinConstraints: Boolean = false, content: BoxScope.() -> Unit = {}) { object : BoxScope {}.content() }
      fun ProbeBar(modifier: Modifier = Modifier) {}
      // KotlinJsonUI's VisibilityWrapper: its content is a BoxScope, so a
      // Row / Column child's weight or alignment does not resolve inside it.
      fun VisibilityWrapper(visibility: String? = null, hidden: Boolean = false, modifier: Modifier = Modifier,
                            content: BoxScope.() -> Unit) { object : BoxScope {}.content() }
      // A responsive branch's width read, and a provider with no receiver.
      class IntSize(val width: Int)
      class WindowInfo(val containerSize: IntSize)
      object LocalWindowInfo { val current = WindowInfo(IntSize(0)) }
      class Density { fun Int.toDp(): Dp = Dp(toFloat()) }
      object LocalDensity { val current = Density() }
      class Color(val argb: Int)
      fun parseColor(hex: String): Int = 0
      class ProvidedValue
      object LocalJsonUITint { infix fun provides(value: Color?): ProvidedValue = ProvidedValue() }
      fun CompositionLocalProvider(value: ProvidedValue, content: () -> Unit) { content() }
      class Data(val v: String? = null)
    KT
  end

  def kotlin(code)
    "#{scopes}\nfun emitted(data: Data) {\n#{code.gsub('android.graphics.Color.parseColor', 'parseColor')}\n}\n"
  end

  {
    'a Row (weight, alignTop)' => ['horizontal', { 'weight' => 1, 'alignTop' => true }, '.weight(1f)'],
    'a Column (heightWeight, centerHorizontal)' => ['vertical', { 'heightWeight' => 2, 'centerHorizontal' => true }, '.weight(2f)'],
    'a Box (weight given, alignBottom + alignRight)' => [nil, { 'weight' => 1, 'alignBottom' => true, 'alignRight' => true }, '.align(']
  }.each do |parent, (orientation, attrs, emitted)|
    it "emits Kotlin that compiles in #{parent}" do
      code = emit(row({ 'type' => 'ProbeBar', 'id' => 'bar' }.merge(attrs), orientation))
      expect(code).to include(emitted) # what the arm is about is in the code compiled (control)
      expect(kotlin(code)).to compile_as_kotlin
    end
  end

  # kjui-app-component-align-box-picks-column-alignment-inside-visibility-wrapper:
  # every wrapper kjui puts around an app component, compiled. Of the five
  # (counted in compose_builder: VisibilityWrapper, the tint provider and the
  # interaction-stop provider (CompositionLocalProvider), the stop capture
  # (`let`), a responsive branch (if / else)), VisibilityWrapper alone gives
  # its content a receiver — a BoxScope (KotlinJsonUI declares no other
  # scoped content). The Box's weight / alignment has to reach the wrapper,
  # in the parent's scope: VisibilityHelper hoists the `.weight(` / `.align(`
  # lines of the chain it wraps, and 1.9.8 wrote the Box's single modifier on
  # one line (`Modifier.align(Alignment.Start)`), which it does not read —
  # "actual type is 'Alignment.Horizontal', but 'Alignment' was expected".
  {
    'VisibilityWrapper in a Column (alignLeft)' =>
      [{ 'type' => 'View', 'orientation' => 'vertical', 'child' => [{ 'type' => 'ProbeBar', 'alignLeft' => true, 'visibility' => '@{v}' }] }, '.align(Alignment.Start)'],
    # a weight alone: one modifier is the shape 1.9.8 wrote on one line
    'VisibilityWrapper in a Row (weight)' =>
      [{ 'type' => 'View', 'orientation' => 'horizontal', 'child' => [{ 'type' => 'ProbeBar', 'weight' => 1, 'visibility' => '@{v}' }] }, '.weight(1f)'],
    'a responsive branch and VisibilityWrapper in a Column (the ticket\'s shape)' =>
      [{ 'type' => 'View', 'orientation' => 'vertical', 'child' => [{ 'type' => 'ProbeBar', 'visibility' => '@{v}',
                                                                      'responsive' => { 'regular' => { 'alignLeft' => true }, 'compact' => { 'alignLeft' => true } } }] }, '.align(Alignment.Start)'],
    'the tint provider around a Column (alignLeft, VisibilityWrapper)' =>
      [{ 'type' => 'View', 'orientation' => 'vertical', 'tintColor' => '#FF0000',
         'child' => [{ 'type' => 'ProbeBar', 'alignLeft' => true, 'visibility' => '@{v}' }] }, 'CompositionLocalProvider(']
  }.each do |shape, (node, emitted)|
    it "emits Kotlin that compiles in #{shape}" do
      code = emit(node)
      expect(code).to include(emitted).and include('ProbeBar(') # the shape is in the code compiled (control)
      expect(kotlin(code)).to compile_as_kotlin
    end
  end

  it 'puts the weight on the wrapper and fills it with the Box, so the slot reaches the component' do
    code = emit({ 'type' => 'View', 'orientation' => 'horizontal', 'child' => [{ 'type' => 'ProbeBar', 'weight' => 1, 'visibility' => '@{v}' }] })
    wrapper = code[/VisibilityWrapper\((?:(?!\) \{).)*\) \{/m]
    expect(wrapper).to include('Modifier.weight(1f)')
    box = code[/Box\((?:(?!\) \{).)*\) \{/m]
    expect(box).to include('.fillMaxWidth()').and include('propagateMinConstraints = true')
    expect(box).not_to include('.weight(')
  end

  # The census, kept: for every SSoT common attribute, an app's component gets
  # the parent-scope modifiers (`.weight(` / `.align(`) a built-in leaf gets in
  # a Row, a Column or a Box — no fewer, and no more (a weight in a Box does
  # not compile). The attribute list is read from the SSoT,
  # so one added there is counted without editing this.
  definitions = JSON.parse(File.read(File.expand_path('../../../shared/core/attribute_definitions.json', __dir__)))
  sample = lambda do |name, spec|
    types = Array(spec['type'])
    next 1 if name =~ /weight/i
    next true if types.include?('boolean')
    next 4 if types.include?('number')

    nil
  end
  scoped = ->(code) { code.lines.map(&:strip).select { |l| l.start_with?('.weight(', '.align(', 'modifier = Modifier.weight(', 'modifier = Modifier.align(') } }

  { 'Row' => 'horizontal', 'Column' => 'vertical', 'Box' => nil }.each do |parent, orientation|
    it "gives an app component every parent-scope modifier a built-in View gets in a #{parent}" do
      checked = 0
      missing = definitions['common'].filter_map do |name, spec|
        next unless spec.is_a?(Hash)

        value = sample.call(name, spec)
        next if value.nil?

        built_in = scoped.call(emit(row({ 'type' => 'View', 'id' => 'n', name => value }, orientation)))
        checked += 1 unless built_in.empty?
        app = scoped.call(emit(row({ 'type' => 'ProbeBar', 'id' => 'n', name => value }, orientation)))
        want = built_in.map { |l| l.sub(/\Amodifier = Modifier/, '').chomp(',') }
        have = app.map { |l| l.sub(/\Amodifier = Modifier/, '').chomp(',') }
        "#{name}: built-in #{want} / app #{have}" unless want.sort == have.sort
      end
      expect(checked).to be > 0 # the census reached attributes at all (control)
      expect(missing).to eq([])
    end
  end
end
