# frozen_string_literal: true

require 'compose/compose_builder'
require 'core/tap_accessibility'
require 'core/image_accessibility'
require 'json'
require 'set'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# `safeAreaInsetPositions`: the six declared words mean one thing on every
# path (4f ruling, 2026-09-26) — top / bottom that edge, leading / trailing
# where reading starts / ends (WindowInsetsSides.Start / End), vertical top
# and bottom, all every edge — and any other word reserves no edge.
#
# kjui read them two ways: a plain node took `vertical`, SafeAreaView did not;
# neither took `leading` / `trailing`; SafeAreaView turned `all` minus a
# TabView's bottom into `start` / `end` and drew nothing for them; and
# `bottom` was `navigationBarsPadding`, which reserves the navigation bar on
# whichever side it sits (a side, in landscape).
RSpec.describe 'kjui codegen: safeAreaInsetPositions' do
  emit = lambda do |node|
    comp = JSON.parse(JSON.generate(node))
    JsonUIShared::ImageAccessibility.annotate!(comp, source_path: 'p.json')
    JsonUIShared::TapAccessibility.annotate!(comp)
    KjuiTools::Compose::ComposeBuilder.new.send(:generate_component, comp, 0).to_s
  end
  child = [{ 'type' => 'Label', 'text' => 'c' }]
  constrained = [{ 'type' => 'Label', 'id' => 'a', 'text' => 'c' }, { 'type' => 'Label', 'text' => 'd', 'alignTopOfView' => 'a' }]
  # The three paths: a plain node, and SafeAreaView's two builders.
  paths = {
    'View' => ->(positions) { { 'type' => 'View', 'safeAreaInsetPositions' => positions, 'child' => child } },
    'SafeAreaView' => ->(positions) { { 'type' => 'SafeAreaView', 'safeAreaInsetPositions' => positions, 'child' => child } },
    'SafeAreaView with constraints' => lambda { |positions|
      { 'type' => 'SafeAreaView', 'safeAreaInsetPositions' => positions, 'child' => constrained }
    }
  }
  side = ->(code, s) { code.scan(/windowInsetsPadding\(WindowInsets\.systemBars\.only\(([^)]*)\)\)/).flatten.join(' + ').scan(s).size }
  # The sides a path reserves, by what its paddings name.
  reserved = lambda do |code|
    { 'top' => 'WindowInsetsSides.Top', 'bottom' => 'WindowInsetsSides.Bottom',
      'leading' => 'WindowInsetsSides.Start', 'trailing' => 'WindowInsetsSides.End' }
      .select { |_, s| side.call(code, s).positive? }.keys
  end

  expected = {
    %w[top] => %w[top], %w[bottom] => %w[bottom], %w[leading] => %w[leading], %w[trailing] => %w[trailing],
    %w[vertical] => %w[top bottom], %w[all] => %w[top bottom leading trailing],
    %w[top leading] => %w[top leading], %w[vertical trailing] => %w[top bottom trailing]
  }

  paths.each do |label, node|
    expected.each do |words, edges|
      it "#{label} #{words.inspect} reserves #{edges.join(', ')}" do
        expect(reserved.call(emit.call(node.call(words)))).to eq(edges)
      end
    end

    # Both sides of the declaration: the declared word reserves its edge, and
    # a word declared nowhere — or in another case — reserves none.
    it "#{label}: a word declared nowhere, or in another case, reserves no edge" do
      %w[start end left right horizontal Top ALL Leading].each do |word|
        code = emit.call(node.call([word]))
        expect(code).not_to include('windowInsetsPadding'), "#{word}\n#{code}"
        expect(reserved.call(emit.call(node.call(['top', word])))).to eq(%w[top]), word
      end
    end

    # Each edge is that side of the system bars and nothing else: no status,
    # navigation or system bar padding.
    it "#{label}: reserves each edge as that side of the system bars" do
      code = emit.call(node.call(%w[all]))
      expect(code).not_to match(/(?:status|navigation|system)BarsPadding/)
    end

    # The edge an enclosing TabView reserves (LocalSafeAreaConfig) is left to
    # it, on the plain node as on SafeAreaView.
    it "#{label}: leaves top and bottom to an enclosing TabView, never the sides" do
      code = emit.call(node.call(%w[all]))
      config = label == 'View' ? 'LocalSafeAreaConfig.current' : 'safeAreaConfig'
      expect(code).to include(".then(if (!#{config}.ignoreTop) Modifier.windowInsetsPadding(WindowInsets.systemBars.only(WindowInsetsSides.Top)) else Modifier)")
      expect(code).to include(".then(if (!#{config}.ignoreBottom) Modifier.windowInsetsPadding(WindowInsets.systemBars.only(WindowInsetsSides.Bottom)) else Modifier)")
      expect(code).to include('.windowInsetsPadding(WindowInsets.systemBars.only(WindowInsetsSides.Start + WindowInsetsSides.End))')
      expect(code).not_to match(/ignore(?:Left|Right)/)
    end
  end

  # SafeAreaView reserves every edge when it names none; naming only words
  # that reserve nothing is not naming none. A plain node that names none
  # reserves nothing.
  it 'reserves every edge for a SafeAreaView that names none, and nothing for a View' do
    %w[SafeAreaView SafeAreaView\ with\ constraints].each do |label|
      named_none = paths[label].call(nil).reject { |k, _| k == 'safeAreaInsetPositions' }
      expect(reserved.call(emit.call(named_none))).to eq(%w[top bottom leading trailing]), label
      expect(reserved.call(emit.call(paths[label].call([])))).to eq([]), label
      expect(reserved.call(emit.call(paths[label].call(%w[left])))).to eq([]), label
    end
    expect(emit.call({ 'type' => 'View', 'child' => child })).not_to include('windowInsetsPadding')
  end

  # `edges`, the alias spelling, reads the same words and wins.
  it 'reads the edges alias the same way, before safeAreaInsetPositions' do
    code = emit.call({ 'type' => 'SafeAreaView', 'edges' => %w[vertical], 'safeAreaInsetPositions' => %w[leading], 'child' => child })
    expect(reserved.call(code)).to eq(%w[top bottom])
  end

  it 'registers the imports the paddings name' do
    [paths['View'].call(%w[all]), paths['SafeAreaView'].call(%w[top])].each do |node|
      builder = KjuiTools::Compose::ComposeBuilder.new
      imports = Set.new
      builder.instance_variable_set(:@required_imports, imports)
      comp = JSON.parse(JSON.generate(node))
      JsonUIShared::TapAccessibility.annotate!(comp)
      builder.send(:generate_component, comp, 0)
      expect(imports).to include(:safe_area_sides, :safe_area_config), node['type']
    end
    lines = KjuiTools::Compose::Helpers::ImportManager.get_imports_map[:safe_area_sides]
    %w[WindowInsets WindowInsetsSides only systemBars windowInsetsPadding].each do |name|
      expect(lines).to include("import androidx.compose.foundation.layout.#{name}")
    end
  end

  # ⚠️ Against stubs (spec/support/compose_stub_universe.rb `common_stages`):
  # "well-typed Kotlin", not "valid Compose".
  it 'compiles every word on every path' do
    functions = []
    paths.each_value do |node|
      (expected.keys + [%w[left], []]).each do |words|
        functions << "fun emitted#{functions.size}(data: Data, viewModel: ViewModel) {\n#{emit.call(node.call(words))}\n}"
      end
    end
    emitted = functions.join("\n\n")
    expect(emitted.scan('windowInsetsPadding(').size).to be >= expected.size * paths.size
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(emitted)}
      class ConstrainedLayoutReference
      interface ConstraintLayoutScope { fun createRef(): ConstrainedLayoutReference = ConstrainedLayoutReference() }
      fun ConstraintLayout(modifier: Modifier = Modifier, content: ConstraintLayoutScope.() -> Unit) {}
      fun Modifier.fillMaxHeight(): Modifier = this
      class Data(val onTap: (() -> Unit)? = null)
      class ViewModel { fun updateData(values: Map<String, Any?>) {} }
      #{emitted}
    KOTLIN
  end
end
