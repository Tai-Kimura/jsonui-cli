# frozen_string_literal: true

require 'json'
require 'set'
require 'tmpdir'
require 'compose/compose_builder'
require 'compose/generators/converter_generator'
require 'compose/generators/kotlin_component_generator'
require 'compose/generators/dynamic_component_generator'
require 'core/tap_accessibility'
require 'core/image_accessibility'
require 'core/type_synonyms'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# App components standing in for ones in a project's components/extensions
# directory.
module LifecycleProbes
  # The scaffold's kind: calls none of the node's handlers.
  class Bare
    def self.generate(_json, _depth, _imports, _parent)
      'LcBare(modifier = Modifier)'
    end
  end

  # Calls the node's onAppear itself (a parameter of its composable).
  class CallsAppear
    def self.generate(json, _depth, _imports, _parent)
      "LcCalls(onShown = { data.#{json['onAppear'][2..-2]}?.invoke() })"
    end
  end

  # Calls a handler whose name starts like the node's: not the node's.
  class CallsLonger
    def self.generate(json, _depth, _imports, _parent)
      "LcCalls(onShown = { data.#{json['onAppear'][2..-2]}Later?.invoke() })"
    end
  end

  # A container calling none of the node's handlers; its child calls one of
  # the same name, in the child's own block.
  class Holds
    def self.generate(json, _depth, _imports, _parent)
      { code: 'LcHolds {', children: json['child'], closing: "\n}", json_data: json }
    end
  end
end

# onAppear / onDisappear on every type kjui draws, at every exit that draws a
# node (4f's ruling): called when the view enters / leaves the tree it is drawn
# in — inside its visibility wrapper, so a `gone` view (not in the tree) does
# not call them and an `invisible` one does. They were placed only at the start
# of a container's content (handle_container_result): 5 of the 26 types drawn
# (View, ScrollView, GradientView, CircleView, Blur) called them, and neither an
# app's component nor SafeAreaView's constrained View / ScrollView did.
#
# An app's component: a handler its converter already calls for the node, in
# the code it emitted for the node, is its own (ComposeBuilder
# .converter_calls_any? — the judge the tap / long press / alpha stages ask).
RSpec.describe 'kjui codegen: onAppear / onDisappear at every exit' do
  source = File.read(File.expand_path('../../lib/compose/compose_builder.rb', __dir__))
  # The canonical types the dispatch draws: its `when` cases, read off the source.
  drawn_types = source[/def draw_declared_component.*?\n      end\n/m].scan(/^\s+when '([A-Za-z]+)'/).flatten
  base = {
    'TextField' => { 'text' => '@{t}' }, 'Button' => { 'text' => 't' }, 'Label' => { 'text' => 't' },
    'Image' => { 'srcName' => 'ic_a' }, 'NetworkImage' => { 'url' => 'https://example.invalid/x.png' },
    'CircleImage' => { 'srcName' => 'ic_a' }, 'Switch' => {}, 'CheckBox' => {}, 'Radio' => { 'text' => 'r' },
    'Slider' => {}, 'Progress' => {}, 'Indicator' => {}, 'SelectBox' => { 'items' => %w[a b] },
    'Segment' => { 'items' => %w[a b] }, 'ScrollView' => { 'child' => [{ 'type' => 'Label', 'text' => 'c' }] },
    'SafeAreaView' => { 'child' => [{ 'type' => 'Label', 'text' => 'c' }] },
    'View' => { 'child' => [{ 'type' => 'Label', 'text' => 'c' }] },
    'Collection' => { 'items' => '@{rows}', 'cellClasses' => ['ItemCell'] }, 'Web' => { 'url' => 'about:blank' },
    'TabView' => { 'tabs' => [{ 'title' => 'a' }] }, 'Embed' => { 'screen' => 'm' },
    'GradientView' => { 'gradient' => ['#FF0000', '#0000FF'] },
    'CircleView' => { 'child' => [{ 'type' => 'Label', 'text' => 'c' }] },
    'Blur' => {}, 'IconLabel' => { 'text' => 't' }, 'TextView' => { 'text' => '@{t}' }
  }
  lifecycle = { 'onAppear' => '@{appeared}', 'onDisappear' => '@{left}' }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end
  after { KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {} }

  emit = lambda do |node|
    comp = JSON.parse(JSON.generate(node))
    JsonUIShared::ImageAccessibility.annotate!(comp, source_path: 'p.json')
    JsonUIShared::TapAccessibility.annotate!(comp)
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@required_imports, Set.new)
    builder.instance_variable_set(:@responsive_counter, 0)
    builder.instance_variable_set(:@responsive_functions, [])
    builder.send(:generate_component, comp, 0).to_s
  end
  appears = ->(code) { code.scan(/LaunchedEffect\(Unit\) \{\n\s*data\.appeared\?\.invoke\(\)/).size }
  leaves = ->(code) { code.scan(/onDispose \{\n\s*data\.left\?\.invoke\(\)/).size }
  node = ->(type, extra = {}) { { 'type' => type, 'id' => 'n' }.merge(base.fetch(type), lifecycle, extra) }

  # Each exit that draws a node, as the node reaching it.
  exits = {
    'a child' => ->(n) { { 'type' => 'View', 'child' => [n] } },
    "a ScrollView's child" => ->(n) { { 'type' => 'ScrollView', 'child' => [n] } },
    "a SafeAreaView's child" => ->(n) { { 'type' => 'SafeAreaView', 'child' => [n] } },
    "a SafeAreaView's constrained child" => lambda { |n|
      { 'type' => 'SafeAreaView', 'child' => [{ 'type' => 'Label', 'id' => 'a', 'text' => 'x' }, n.merge('alignTopOfView' => 'a')] }
    }
  }

  it 'reads 26 drawn types off the dispatch' do
    expect(drawn_types.size).to eq(26)
    expect(drawn_types - base.keys).to be_empty
  end

  drawn_types.each do |type|
    exits.each do |exit_name, place|
      it "#{type} as #{exit_name} calls onAppear and onDisappear once" do
        code = emit.call(place.call(node.call(type)))
        expect([appears.call(code), leaves.call(code)]).to eq([1, 1]), code
      end
    end

    # A responsive node: each branch is the node as drawn, so each carries
    # them — a size class change draws the other branch, which enters the
    # tree — as a responsive container's branches did. Embed and Collection
    # are drawn as one if / else chain, which carries them once.
    it "#{type} with a responsive branch calls them in each branch drawn" do
      code = emit.call({ 'type' => 'View', 'child' => [node.call(type, 'responsive' => { 'regular' => { 'alpha' => 0.5 } })] })
      want = %w[Embed Collection].include?(type) ? 1 : 2
      expect([appears.call(code), leaves.call(code)]).to eq([want, want]), code
    end

    it "#{type}: the effects are inside its visibility wrapper" do
      code = emit.call({ 'type' => 'View', 'child' => [node.call(type, 'visibility' => '@{vis}')] })
      wrapper = code.index('VisibilityWrapper(')
      expect(wrapper).not_to be_nil, code
      expect(code.index('data.appeared')).to be > wrapper
      expect(code.index('data.left')).to be > wrapper
    end
  end

  # The two sides of the rule, on the specimens that tell them apart: a
  # `gone` view is not in the tree, an `invisible` one is. A static `gone` is
  # not emitted at all — nor its effects; a static `invisible` is drawn in its
  # wrapper at alpha 0, with its effects in it. (A bound visibility: the
  # library's VisibilityWrapper composes no content for `gone`, and the
  # content for `invisible` — the per-type arm above holds the effects inside
  # it.)
  it 'a gone leaf and a gone container call nothing; an invisible one calls them, inside its wrapper' do
    %w[Label View].each do |type|
      # not emitted (a Label), or emitted in a `gone` wrapper that composes
      # no content (a View)
      gone = emit.call({ 'type' => 'View', 'child' => [node.call(type, 'visibility' => 'gone')] })
      if appears.call(gone).zero?
        expect(leaves.call(gone)).to eq(0), gone
      else
        opening = gone.index("VisibilityWrapper(\n")
        expect(opening).not_to be_nil, gone
        expect(gone[opening, 80]).to include('visibility = "gone"'), gone
        expect(gone.index('LaunchedEffect(Unit)')).to be > opening, gone
      end
      invisible = emit.call({ 'type' => 'View', 'child' => [node.call(type, 'visibility' => 'invisible')] })
      expect([appears.call(invisible), leaves.call(invisible)]).to eq([1, 1]), invisible
      opening = invisible.index("VisibilityWrapper(\n")
      expect(invisible[opening, 80]).to include('visibility = "invisible"'), invisible
      expect(invisible.index('LaunchedEffect(Unit)')).to be > opening, invisible
    end
  end

  it 'a responsive Button or Image honours its visibility, as a plain one does' do
    %w[Button Image].each do |type|
      code = emit.call({ 'type' => 'View', 'child' => [node.call(type, 'visibility' => '@{vis}', 'responsive' => { 'regular' => { 'alpha' => 0.5 } })] })
      expect(code.scan('VisibilityWrapper(').size).to eq(2), type
    end
  end

  it 'a TabView honours its visibility' do
    code = emit.call({ 'type' => 'View', 'child' => [node.call('TabView', 'visibility' => '@{vis}')] })
    expect(code.scan('VisibilityWrapper(').size).to eq(1)
  end

  it 'calls nothing for a value that names no handler, and nothing for a type drawn as nothing' do
    code = emit.call({ 'type' => 'View', 'child' => [{ 'type' => 'Label', 'text' => 't', 'onAppear' => ' ', 'onDisappear' => '@{}' }] })
    name = ->(v) { KjuiTools::Compose::Helpers::ModifierBuilder.lifecycle_handler_name(v) }
    expect([name.call(' @{b} '), name.call('b:'), name.call('b'), name.call('@{}'), name.call(' ')]).to eq(['b', 'b', 'b', '', ''])
    expect(code).not_to include('LaunchedEffect')
    expect(code).not_to include('DisposableEffect')
    silent = emit.call({ 'type' => 'View', 'child' => [{ 'type' => 'Spacer' }.merge(lifecycle)] })
    expect(silent).not_to include('data.appeared')
  end

  # --- the judge -------------------------------------------------------------

  describe 'ComposeBuilder.converter_calls_any?' do
    judge = ->(code, names) { KjuiTools::Compose::ComposeBuilder.converter_calls_any?(code, names) }

    it 'is true when the code calls one of the names, false when it calls none' do
      expect(judge.call('X(onShown = { data.appeared?.invoke() })', %w[appeared])).to be(true)
      expect(judge.call('X(modifier = Modifier)', %w[appeared])).to be(false)
    end

    it 'matches a name whole: data.appearedLater is not data.appeared' do
      expect(judge.call('X(onShown = { data.appearedLater?.invoke() })', %w[appeared])).to be(false)
      expect(judge.call('X(onShown = { data.appeared ?: {} })', %w[appeared])).to be(true)
    end

    it 'names nothing for an empty name' do
      expect(judge.call('X(onShown = { data.?.invoke() })', [''])).to be(false)
    end
  end

  # --- an app's component ----------------------------------------------------

  context 'an app component' do
    probes = { 'LcBare' => LifecycleProbes::Bare, 'LcCalls' => LifecycleProbes::CallsAppear,
               'LcLonger' => LifecycleProbes::CallsLonger, 'LcHolds' => LifecycleProbes::Holds }

    before do
      allow(KjuiTools::Compose::ComposeBuilder).to receive(:custom_component_class) { |t| probes[t] }
      allow(KjuiTools::Compose::ComposeBuilder).to receive(:custom_component_types).and_return(probes.keys)
      JsonUIShared::TypeSynonyms.app_types = probes.keys
    end

    after { JsonUIShared::TypeSynonyms.app_types = [] }

    it 'gets them around the component when its converter calls neither' do
      code = emit.call({ 'type' => 'LcBare' }.merge(lifecycle))
      expect([appears.call(code), leaves.call(code)]).to eq([1, 1])
      expect(code.index('LaunchedEffect')).to be < code.index('LcBare(')
    end

    it 'keeps a handler its converter calls itself, and gets the other around it' do
      code = emit.call({ 'type' => 'LcCalls' }.merge(lifecycle))
      expect(code.scan('data.appeared').size).to eq(1) # the converter's own
      expect(appears.call(code)).to eq(0)
      expect(leaves.call(code)).to eq(1)
    end

    it 'reads a name whole: a converter calling appearedLater does not call appeared' do
      code = emit.call({ 'type' => 'LcLonger' }.merge(lifecycle))
      expect(appears.call(code)).to eq(1)
    end

    it "reads the component's own code only: the same handler in its child's block is the child's" do
      child = { 'type' => 'Label', 'text' => 'c', 'onAppear' => '@{appeared}' }
      code = emit.call({ 'type' => 'LcHolds', 'onAppear' => '@{appeared}', 'child' => [child] })
      expect(appears.call(code)).to eq(2) # the child's, and the component's around it
    end

    it 'inside its visibility wrapper' do
      code = emit.call({ 'type' => 'LcBare', 'visibility' => '@{vis}' }.merge(lifecycle))
      expect(code.index('data.appeared')).to be > code.index('VisibilityWrapper(')
    end

    # What `kjui g converter` writes: the component gets them exactly once,
    # and the scaffold adds none of its own.
    it 'gets them exactly once around a converter the scaffold wrote, which adds none' do
      klass = Dir.mktmpdir('kjui_lc') do |dir|
        Dir.chdir(dir) do
          File.write('kjui.config.json', JSON.generate('package_name' => 'probe'))
          scaffold = KjuiTools::Compose::Generators::ConverterGenerator.new('LcScaffold', is_container: false)
                                                                        .send(:converter_template)
                                                                        .gsub(/^\s*require_relative .*$/, '')
          eval(scaffold, TOPLEVEL_BINDING, 'lc_scaffold_component.rb') # rubocop:disable Security/Eval
          KjuiTools::Compose::Components::Extensions.const_get('LcScaffoldComponent')
        end
      end
      alone = klass.generate({ 'type' => 'LcScaffold', 'id' => 'n' }.merge(lifecycle), 0, Set.new)
      expect(alone).not_to include('data.appeared') # the scaffold calls neither
      probes['LcScaffold'] = klass
      allow(KjuiTools::Compose::ComposeBuilder).to receive(:custom_component_types).and_return(probes.keys)
      JsonUIShared::TypeSynonyms.app_types = probes.keys
      code = emit.call({ 'type' => 'LcScaffold' }.merge(lifecycle))
      expect([appears.call(code), leaves.call(code)]).to eq([1, 1])
    end
  end

  # --- the exits, counted -----------------------------------------------------

  # Every method of the builder that wraps a node in its visibility wrapper
  # places the node's lifecycle in it, and the inline constrained containers
  # (which have no wrapper) place it at the start of their content: counted
  # off the source, so an exit added without it is red.
  it 'places the lifecycle in every method that wraps a node, and in the inline containers' do
    methods = source.split(/^      def /).drop(1).to_h { |m| [m[/\A[a-z_?.]+/], m] }
    wrapping = methods.select { |_, body| body.include?('wrap_with_visibility(') }
    expect(wrapping.keys.sort).to eq(%w[generate_component generate_non_responsive_component handle_container_result])
    # every wrap in the file is in one of them (none in a method this missed)
    expect(wrapping.values.sum { |body| body.scan('wrap_with_visibility(').size }).to eq(source.scan('wrap_with_visibility(').size)
    wrapping.each do |name, body|
      expect(body).to match(/lifecycle_at_leaf\(|build_lifecycle_effects\(/), name
    end
    %w[generate_scroll_with_constraints generate_view_with_constraints custom_component_code].each do |name|
      expect(methods.fetch(name)).to match(/lifecycle_effects\(|lifecycle_at_leaf\(/), name
    end
  end

  # ⚠️ Against stubs (spec/support/compose_stub_universe.rb `common_stages`):
  # "well-typed Kotlin", not "valid Compose".
  it 'compiles each type with its effects, and a responsive leaf' do
    compiled = drawn_types.reject { |t| %w[Collection Embed TabView Web SafeAreaView].include?(t) }
    functions = compiled.each_with_index.map do |type, i|
      "fun emitted#{i}(data: Data, viewModel: ViewModel) {\n#{emit.call({ 'type' => 'View', 'child' => [node.call(type, 'visibility' => '@{vis}')] })}\n}"
    end
    functions << "fun emittedResponsive(data: Data, viewModel: ViewModel) {\n#{emit.call({ 'type' => 'View', 'child' => [node.call('Button', 'responsive' => { 'regular' => { 'alpha' => 0.5 } })] })}\n}"
    emitted = functions.join("\n\n")
    expect(appears.call(emitted)).to be >= compiled.size
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(emitted)}
      fun VisibilityWrapper(visibility: String? = null, hidden: Boolean = false, modifier: Modifier = Modifier, content: () -> Unit) {}
      class IntSize(val width: Int, val height: Int)
      class WindowInfo { val containerSize = IntSize(0, 0) }
      object LocalWindowInfo { val current = WindowInfo() }
      class Density { fun Int.toDp(): Dp = Dp(toFloat()) }
      object LocalDensity { val current = Density() }
      fun DisposableEffect(key1: Any?, effect: DisposableEffectScope.() -> DisposableEffectResult) {}
      class DisposableEffectResult
      class DisposableEffectScope { fun onDispose(block: () -> Unit) = DisposableEffectResult() }
      class Data(
          val appeared: (() -> Unit)? = null, val left: (() -> Unit)? = null, val vis: String? = null,
          val t: String = "", val nIsFocused: Boolean = false
      )
      class ViewModel { fun updateData(values: Map<String, Any?>) {} }
      #{emitted}
    KOTLIN
  end
end
