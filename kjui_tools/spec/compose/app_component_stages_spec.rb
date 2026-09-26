# frozen_string_literal: true

require 'json'
require 'set'
require 'compose/compose_builder'
require 'core/type_synonyms'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# App components standing in for ones in a project's components/extensions
# directory, each emitting what a converter of that kind emits.
module AppStageProbes
  # The `kjui g converter` scaffold's kind: none of the common stages.
  class Bare
    def self.generate(_json, _depth, _imports, _parent)
      'ProbeBare(modifier = Modifier)'
    end
  end

  # Calls the node's onClick itself (a parameter of its composable).
  class Taps
    def self.generate(json, _depth, _imports, _parent)
      "ProbeTaps(onClick = { data.#{json['onClick'][2..-2]}?.invoke(\"\") })"
    end
  end

  # Fades itself.
  class Fades
    def self.generate(_json, _depth, _imports, _parent)
      'ProbeFades(modifier = Modifier.alpha(0.5f))'
    end
  end

  # A container that calls none of the node's handlers; its child does call one
  # of the same name, in the child's own block.
  class Holds
    def self.generate(json, _depth, _imports, _parent)
      { code: 'ProbeHolds {', children: json['child'], closing: "\n}", json_data: json }
    end
  end
end

# kjui codegen applies the common stages an app's component does not apply
# itself — its tap, long press (and pan, pinch), their gates, and its alpha —
# around it, as it applies them to a built-in component. The `kjui g
# converter` scaffold applies none of them, so an app's component tapped,
# faded and was long-pressed in Debug (KotlinJsonUI Dynamic applies them) and
# did none of it in release. What the component's own code already does is
# left to it: a handler it calls by its data name, `.alpha(` — read in the code
# it emitted for the node, not in its children's.
RSpec.describe 'kjui codegen: the common stages around an app component' do
  probes = { 'ProbeBare' => AppStageProbes::Bare, 'ProbeTaps' => AppStageProbes::Taps,
             'ProbeFades' => AppStageProbes::Fades, 'ProbeHolds' => AppStageProbes::Holds }

  before do
    allow(KjuiTools::Compose::ComposeBuilder).to receive(:custom_component_class) { |t| probes[t] }
    allow(KjuiTools::Compose::ComposeBuilder).to receive(:custom_component_types).and_return(probes.keys)
    JsonUIShared::TypeSynonyms.app_types = probes.keys
  end

  after { JsonUIShared::TypeSynonyms.app_types = [] }

  def emit(node)
    builder = KjuiTools::Compose::ComposeBuilder.allocate
    builder.instance_variable_set(:@required_imports, Set.new)
    builder.send(:generate_component, JSON.parse(JSON.generate(node)), 1)
  end

  stages = { 'onClick' => '@{tapS}', 'onLongPress' => '@{pressS}', 'alpha' => 0.5 }

  it 'applies the tap, the long press and the alpha around a component that applies none' do
    code = emit({ 'type' => 'ProbeBare' }.merge(stages))
    expect(code).to include('ProbeBare(modifier = Modifier)') # the component's own call (control)
    expect(code).to start_with('    Box(')
    expect(code).to include('data.tapS').and include('data.pressS').and include('.alpha(0.5f)')
  end

  it 'leaves a handler the component calls itself to it, and still applies the one it does not' do
    code = emit({ 'type' => 'ProbeTaps' }.merge(stages))
    expect(code.scan('data.tapS').size).to eq(1)
    expect(code).to include('data.pressS')
  end

  it 'reads the component\'s own code only: the same handler name in its child\'s block is not the component\'s' do
    child = { 'type' => 'Button', 'text' => 'b', 'onClick' => '@{tapS}' }
    code = emit({ 'type' => 'ProbeHolds', 'onClick' => '@{tapS}', 'child' => [child] })
    expect(code.scan('data.tapS').size).to eq(2) # the child's and the one around the component
    expect(code).to start_with('    Box(')
  end

  it 'leaves an alpha the component applies itself to it' do
    code = emit({ 'type' => 'ProbeFades', 'alpha' => 0.5 })
    expect(code.scan('.alpha(').size).to eq(1)
  end

  it 'adds nothing to a component whose node has none of the stages' do
    expect(emit({ 'type' => 'ProbeBare' })).to eq('ProbeBare(modifier = Modifier)')
  end

  it 'emits Kotlin that compiles around the component' do
    code = emit({ 'type' => 'ProbeBare' }.merge(stages))
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(code)}
      fun ProbeBare(modifier: Modifier = Modifier) {}
      class Data(val tapS: (() -> Unit)? = null, val pressS: (() -> Unit)? = null)
      class ViewModel
      fun emitted(data: Data, viewModel: ViewModel) {
      #{code}
      }
    KOTLIN
  end
end
