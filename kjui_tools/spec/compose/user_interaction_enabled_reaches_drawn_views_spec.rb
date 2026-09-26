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
