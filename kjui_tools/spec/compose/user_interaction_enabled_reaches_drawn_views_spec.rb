# frozen_string_literal: true

require 'compose/compose_builder'
require 'compose/helpers/modifier_builder'
require 'compose/interaction_stop_index'
require 'core/tap_accessibility'
require 'core/image_accessibility'
require 'json'
require 'set'
require 'tmpdir'
require 'fileutils'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# `userInteractionEnabled` stops a node and everything in it, and the tap rule
# says no click for what it holds (annotate!). What it draws in a composable
# of its own — a Collection's cells, headers and footers, an Embed's screen, a
# TabView tab's view — is another layout: annotate! does not reach it, and its
# clicks kept Role.Button (measured at jsonui-cli 0ad0d32e, before 1.9.0: a cell with
# onClick inside a Collection inside a View with the flag false was emitted
# with `.clickable(role = Role.Button)` and nothing that knew of the stop).
#
# The stop is handed down at run time, as the Dynamic runtime hands it down:
# the stopping node provides KotlinJsonUI's LocalInteractionStopped, and the
# layouts it can reach (InteractionStopIndex, over the whole project) attach
# their clicks while it is false. Every other layout is emitted as it was.
RSpec.describe 'kjui userInteractionEnabled reaches what is drawn in a composable of its own' do
  after { KjuiTools::Compose::Helpers::ModifierBuilder.reads_interaction_local = false }

  counters = %w[TextComponent TextFieldComponent TextViewComponent ButtonComponent ConstraintLayoutComponent]
  emit = lambda do |node, reads: false|
    counters.each { |c| KjuiTools::Compose::Components.const_get(c).reset_counter! }
    KjuiTools::Compose::Helpers::ModifierBuilder.reads_interaction_local = reads
    comp = JSON.parse(JSON.generate(node))
    JsonUIShared::ImageAccessibility.annotate!(comp, source_path: 'probe.json')
    JsonUIShared::TapAccessibility.annotate!(comp)
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@required_imports, Set.new)
    builder.instance_variable_set(:@responsive_counter, 0)
    code = builder.send(:generate_component, comp, 1)
    [code, builder.instance_variable_get(:@required_imports)]
  ensure
    KjuiTools::Compose::Helpers::ModifierBuilder.reads_interaction_local = false
  end

  collection = { 'type' => 'Collection', 'id' => 'list', 'cellClasses' => ['row_cell'], 'items' => '@{rows}' }
  stopping = ->(flag, child, more = {}) { { 'type' => 'View', 'id' => 'stop', 'userInteractionEnabled' => flag, 'child' => [child] }.merge(more) }
  static_open = 'CompositionLocalProvider(LocalInteractionStopped provides (true)) {'
  bound_open = 'CompositionLocalProvider(LocalInteractionStopped provides (LocalInteractionStopped.current || !(data.u ?: false))) {'

  describe 'InteractionStopIndex, over a layouts directory' do
    around do |example|
      Dir.mktmpdir do |dir|
        @dir = dir
        example.run
      end
    end

    def write(name, tree)
      File.write(File.join(@dir, "#{name}.json"), JSON.generate(tree))
    end

    it 'reaches a cell through an include, and an embedded screen, and nothing else' do
      write('screen', { 'type' => 'View', 'userInteractionEnabled' => '@{u}',
                        'child' => [{ 'include' => 'part' }, { 'type' => 'Embed', 'screen' => 'card' }] })
      write('part', { 'type' => 'View', 'child' => [{ 'type' => 'Collection', 'cellClasses' => ['row_cell'] }] })
      write('row_cell', { 'type' => 'View', 'onClick' => '@{onRow}' })
      write('card', { 'type' => 'View', 'onClick' => '@{onOpen}' })
      write('other', { 'type' => 'Collection', 'cellClasses' => ['free_cell'] })
      write('free_cell', { 'type' => 'View', 'onClick' => '@{onRow}' })
      expect(KjuiTools::Compose::InteractionStopIndex.build(@dir).to_a).to match_array(%w[row_cell card])
    end

    it 'is empty with no directory' do
      expect(KjuiTools::Compose::InteractionStopIndex.build(nil)).to be_empty
    end

    it 'decides, per layout, whether its clicks read the stop' do
      write('screen', stopping.call(false, collection))
      write('row_cell', { 'type' => 'View', 'onClick' => '@{onRow}' })
      write('free', { 'type' => 'View', 'onClick' => '@{onRow}' })
      builder = KjuiTools::Compose::ComposeBuilder.new
      builder.instance_variable_set(:@layouts_dir, @dir)
      builder.send(:begin_interaction_local, File.join(@dir, 'row_cell.json'))
      expect(KjuiTools::Compose::Helpers::ModifierBuilder.reads_interaction_local).to be(true)
      builder.send(:begin_interaction_local, File.join(@dir, 'free.json'))
      expect(KjuiTools::Compose::Helpers::ModifierBuilder.reads_interaction_local).to be(false)
    end
  end

  describe 'the stopping node' do
    it 'with false, provides the stop around itself, once' do
      code, imports = emit.call(stopping.call(false, collection))
      expect(code.scan(static_open).size).to eq(1)
      expect(code.lstrip).to start_with(static_open)
      expect(imports).to include(:composition_local_provider, :local_interaction_stopped)
    end

    it 'with a binding, provides the stop around it or the binding' do
      code, = emit.call(stopping.call('@{u}', collection))
      expect(code.scan(bound_open).size).to eq(1), code
    end

    it 'a Collection or an Embed with the flag provides it too' do
      expect(emit.call(collection.merge('userInteractionEnabled' => false)).first).to include(static_open)
      expect(emit.call({ 'type' => 'Embed', 'id' => 'e', 'screen' => 'card', 'userInteractionEnabled' => false }).first)
        .to include(static_open)
    end

    it 'holding nothing drawn elsewhere, or with no flag, provides nothing' do
      expect(emit.call(stopping.call(false, { 'type' => 'Label', 'id' => 'l', 'text' => 't' })).first)
        .not_to include('LocalInteractionStopped')
      expect(emit.call({ 'type' => 'View', 'id' => 'v', 'child' => [collection] }).first).not_to include('LocalInteractionStopped')
    end

    it 'a weighted stopping node keeps its weight inside the provider' do
      code, = emit.call({ 'type' => 'View', 'orientation' => 'horizontal', 'child' => [
                          stopping.call(false, collection, 'weight' => 1, 'width' => 0)
                        ] })
      provider = code.index(static_open)
      expect(provider).not_to be_nil
      expect(code.index('.weight(', provider)).not_to be_nil
    end
  end

  describe 'a layout a stop can reach' do
    extra = {
      'Image' => { 'srcName' => 'x' }, 'CircleImage' => { 'srcName' => 'x' },
      'NetworkImage' => { 'url' => 'https://e/x.png' }, 'Label' => { 'text' => 't' },
      'Text' => { 'text' => 't' }, 'IconLabel' => { 'text' => 't' }
    }
    tap = JsonUIShared::TapAccessibility
    not_clicking = %w[CircleView CircleImageView ImageView Img]
    types = (tap::KNOWN_TYPES - tap::INTERACTIVE_TYPES).uniq - not_clicking
    node = ->(type, more = {}) { { 'type' => type, 'id' => 'n', 'onClick' => '@{onTap}' }.merge(extra[type] || {}).merge(more) }

    types.each do |type|
      it "#{type}: its click is attached while no stop is handed down" do
        code, imports = emit.call(node.call(type), reads: true)
        expect(code).to include('.then(if (!LocalInteractionStopped.current) Modifier.clickable(')
        expect(imports).to include(:local_interaction_stopped)
      end

      it "#{type}: in a layout no stop can reach, it is emitted as it was" do
        expect(emit.call(node.call(type)).first).not_to include('LocalInteractionStopped')
      end
    end

    it 'joins it after a bound canTap and the bound flags in the file' do
      code, = emit.call(stopping.call('@{u}', node.call('Label', 'canTap' => '@{c}')), reads: true)
      expect(code).to include('.then(if (((data.c ?: false) && (data.u ?: false)) && !LocalInteractionStopped.current) Modifier.clickable(')
    end
  end

  # A control's own operation and a Button's onClick call the declared onClick
  # from a lambda, where a CompositionLocal cannot be read: the leaf is
  # wrapped in `LocalInteractionStopped.current.let { jsonuiInteractionStopped
  # -> … }` (read in the composable's scope) and the lambda gates on the
  # captured value.
  describe "a control's call and a Button's onClick in a layout a stop can reach" do
    controls = {
      'Button' => { 'text' => 't' }, 'Switch' => { 'isOn' => '@{on}' }, 'Toggle' => { 'isOn' => '@{on}' },
      'CheckBox' => { 'isOn' => '@{on}' }, 'Radio items' => { 'type' => 'Radio', 'items' => %w[a b], 'selectedValue' => '@{sel}' },
      'Radio options' => { 'type' => 'Radio', 'options' => %w[a b], 'bind' => '@{sel}' },
      'Segment' => { 'items' => %w[a b], 'selectedIndex' => '@{idx}' }, 'Slider' => { 'value' => '@{v}' },
      'SelectBox' => { 'items' => %w[a b], 'selectedIndex' => '@{idx}' }
    }
    capture = 'LocalInteractionStopped.current.let { jsonuiInteractionStopped ->'
    gated = /if \(!jsonuiInteractionStopped\) \{ data\.onTap\?\.invoke\(\) \}/
    node_for = ->(label, more) { { 'type' => label.split.first, 'id' => 'n', 'onClick' => '@{onTap}' }.merge(more) }

    controls.each do |label, more|
      it "#{label}: the leaf captures the stop and every call gates on it" do
        code, imports = emit.call(node_for.call(label, more), reads: true)
        expect(code.lstrip).to start_with(capture)
        expect(code.scan(capture).size).to eq(1)
        expect(code.scan(gated).size).to be >= 1
        expect(code.scan('data.onTap?.invoke()').size).to eq(code.scan(gated).size), code
        expect(imports).to include(:local_interaction_stopped)
      end

      it "#{label}: in a layout no stop can reach, it is emitted as it was" do
        code, = emit.call(node_for.call(label, more))
        expect(code).not_to include('jsonuiInteractionStopped')
        expect(code).to include('data.onTap?.invoke()')
      end
    end

    # Leaves only: a container's code holds its children's, so wrapping it
    # when a child captures would open a second `let` around the first — the
    # same name shadowed, for nothing.
    it 'a container holding a wrapped control is not wrapped around it: one capture, on the control' do
      code, = emit.call({ 'type' => 'View', 'id' => 'v', 'child' => [node_for.call('Button', controls['Button'])] }, reads: true)
      expect(code.scan(capture).size).to eq(1), code
      expect(code.lstrip).not_to start_with(capture)
    end

    it 'a container is not wrapped: its click reads the local where the modifier is built' do
      code, = emit.call({ 'type' => 'View', 'id' => 'v', 'onClick' => '@{onTap}',
                          'child' => [{ 'type' => 'Label', 'text' => 'x' }] }, reads: true)
      expect(code).not_to include(capture)
      expect(code).to include('!LocalInteractionStopped.current')
    end

    # Both sides, run: the gated call is made while no stop is handed down,
    # and not while one is.
    it 'the gated call is made when the stop is off and not when it is on' do
      code, = emit.call(node_for.call('Switch', controls['Switch']), reads: true)
      statement = code[gated]
      source = <<~KOTLIN
        var calls = 0
        class Data { val onTap: (() -> Unit)? = { calls++ } }
        fun fire(data: Data, jsonuiInteractionStopped: Boolean) { #{statement} }
        fun main() {
            val data = Data()
            fire(data, false)
            val open = calls
            fire(data, true)
            println("open=$open shut=${calls - open}")
        }
      KOTLIN
      result = KotlinCompiler.run(source)
      skip("compile_as_kotlin: #{KotlinCompiler.unavailable_reason}") if KotlinCompiler.unavailable_reason
      expect(result.errors).to eq([])
      expect(result.output.strip).to eq('open=1 shut=0')
    end

    it 'every wrapped control compiles, the capture in scope of its lambdas' do
      functions = controls.map.with_index do |(label, more), i|
        code, = emit.call(node_for.call(label, more), reads: true)
        "// #{label}\nfun emitted#{i}(data: Data, viewModel: ViewModel) {\n#{code}\n}"
      end
      emitted = functions.join("\n\n")
      expect(emitted.scan(capture).size).to eq(controls.size)
      expect(<<~KOTLIN).to compile_as_kotlin
        #{ComposeStubUniverse.common_stages(emitted)}
        class Data(
            val onTap: (() -> Unit)? = null, val on: Boolean = false, val sel: String = "",
            val idx: Int = 0, val v: Double = 0.0, val selectedRadiogroup: String = ""
        )
        class ViewModel { fun updateData(values: Map<String, Any?>) {} }
        #{emitted}
      KOTLIN
    end
  end

  # generate_component, and what it hands a responsive node to, are the
  # builder's exits for a node's code. Each exit either hands the stop down
  # itself (provide_interaction_stop), hands the node to another of these
  # methods, or returns nothing (a data-only entry). Counted from the source,
  # not listed by hand: an exit added without the stop is red here.
  describe "the builder's exits for a node's code" do
    source = File.read(File.expand_path('../../lib/compose/compose_builder.rb', __dir__), encoding: 'UTF-8')
    ast = RubyVM::AbstractSyntaxTree.parse(source)
    emitters = %i[generate_component generate_responsive_component generate_view_responsive_inline
                  generate_non_responsive_component]
    nodes = lambda do |n, &blk|
      next unless n.is_a?(RubyVM::AbstractSyntaxTree::Node)

      blk.call(n)
      n.children.each { |c| nodes.call(c, &blk) }
    end
    last_exprs = lambda do |n|
      next [] unless n.is_a?(RubyVM::AbstractSyntaxTree::Node)

      case n.type
      when :BLOCK then last_exprs.call(n.children.last)
      when :IF, :UNLESS then [n.children[1], n.children[2]].compact.flat_map { |c| last_exprs.call(c) }
      else [n]
      end
    end
    defs = {}
    nodes.call(ast) { |n| defs[n.children[0]] = n if n.type == :DEFN && emitters.include?(n.children[0]) }
    classify = lambda do |expr, body|
      case expr.type
      when :STR then expr.children[0].empty? ? :nothing : :unclassified
      when :FCALL, :VCALL
        name = expr.children[0]
        next :hands_stop_down if name == :provide_interaction_stop
        next :delegated if emitters.include?(name)

        :unclassified
      when :CALL
        next :unclassified unless expr.children[1] == :join && expr.children[0].type == :LVAR

        var = expr.children[0].children[0]
        pushed = []
        nodes.call(body) do |n|
          pushed << n.children[2].children[0] if n.type == :OPCALL && n.children[1] == :<< &&
                                                  n.children[0].type == :LVAR && n.children[0].children[0] == var
        end
        pushed.all? { |p| p.type == :FCALL && (p.children[0] == :indent || emitters.include?(p.children[0])) } ? :joined : :unclassified
      else :unclassified
      end
    end
    exits = defs.flat_map do |name, d|
      body = d.children[1].children[2]
      returned = []
      nodes.call(body) { |n| returned << n.children[0] if n.type == :RETURN && n.children[0] }
      (returned + last_exprs.call(body)).map { |e| [name, e.first_lineno, classify.call(e, body)] }
    end
    handing_calls = []
    nodes.call(ast) { |n| handing_calls << n.first_lineno if n.type == :FCALL && n.children[0] == :provide_interaction_stop }

    it 'finds every emitting method' do
      expect(defs.keys).to match_array(emitters)
    end

    it 'classifies every exit' do
      unclassified = exits.select { |_, _, kind| kind == :unclassified }
      expect(unclassified).to eq([]), exits.map { |e| e.join(' ') }.join("\n")
    end

    it 'counts one exit that hands the stop down for each call that does' do
      handing = exits.count { |_, _, kind| kind == :hands_stop_down }
      expect(handing).to eq(handing_calls.size), "exits #{exits.inspect}, calls at #{handing_calls.inspect}"
      expect(handing).to be >= 4
    end
  end

  describe 'a responsive node' do
    responsive = lambda do |node, compact_attrs|
      node.merge('responsive' => { 'compact' => compact_attrs })
    end

    it 'hands the stop down from each branch, with the branch\'s own flag' do
      code, = emit.call(responsive.call(stopping.call(false, collection), { 'userInteractionEnabled' => true }))
      expect(code.scan(static_open).size).to eq(1), code
      code, = emit.call(responsive.call(stopping.call(true, collection), { 'userInteractionEnabled' => false }))
      expect(code.scan(static_open).size).to eq(1), code
    end

    it 'a responsive Button in a layout a stop can reach captures the stop in each branch' do
      button = { 'type' => 'Button', 'id' => 'b', 'text' => 't', 'onClick' => '@{onTap}' }
      code, = emit.call(responsive.call(button, { 'text' => 'compact' }), reads: true)
      expect(code.scan('LocalInteractionStopped.current.let { jsonuiInteractionStopped ->').size).to eq(2), code
    end
  end

  # The emitted provider openings and the gated click, against Compose's shapes
  # (stubs): `provides` is infix, the provided value parenthesised; the local is
  # read in the composable scope a modifier is built in; a weight on the
  # wrapped node still resolves in the Row's scope (the provider's content
  # lambda has no receiver).
  it 'the provider, the gated click and a weight inside the provider compile' do
    _, = emit.call(stopping.call(false, collection))
    click = emit.call(node = { 'type' => 'Label', 'id' => 'n', 'text' => 't', 'onClick' => '@{onTap}' }, reads: true)
              .first[/\.then\(if \(!LocalInteractionStopped\.current\) Modifier\.clickable\(role = Role\.Button\) \{ data\.onTap\?\.invoke\(\) \} else Modifier\)/]
    expect(click).to be_a(String)
    source = <<~KOTLIN
      interface Modifier { companion object : Modifier }
      class Role private constructor() { companion object { val Button = Role() } }
      fun Modifier.clickable(enabled: Boolean = true, onClickLabel: String? = null, role: Role? = null,
                             onClick: () -> Unit): Modifier = this
      class Data(val onTap: (() -> Unit)? = null, val u: Boolean? = null)
      fun Modifier.then(other: Modifier): Modifier = this
      class ProvidedValue<T>(val value: T)
      class ProvidableCompositionLocal<T>(private val default: T) {
          val current: T get() = default
          infix fun provides(value: T): ProvidedValue<T> = ProvidedValue(value)
      }
      val LocalInteractionStopped = ProvidableCompositionLocal(false)
      fun CompositionLocalProvider(value: ProvidedValue<*>, content: () -> Unit) = content()
      @DslMarker annotation class LayoutScopeMarker
      @LayoutScopeMarker interface RowScope { fun Modifier.weight(w: Float): Modifier = this }
      object RowScopeInstance : RowScope
      fun Row(content: RowScope.() -> Unit) = RowScopeInstance.content()
      fun Box(modifier: Modifier = Modifier, content: () -> Unit = {}) = content()
      fun clicked(data: Data): Modifier = Modifier#{click}
      fun provided(data: Data) {
          Row {
              #{static_open}
                  Box(modifier = Modifier.weight(1f)) { }
              }
              #{bound_open}
                  Box(modifier = Modifier.weight(1f)) { }
              }
          }
      }
    KOTLIN
    expect(source).to compile_as_kotlin
  end
end
