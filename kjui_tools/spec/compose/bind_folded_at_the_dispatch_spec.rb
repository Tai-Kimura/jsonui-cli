# frozen_string_literal: true

require 'compose/compose_builder'
require 'core/bind_fold'
require 'core/attribute_validator'
require 'json'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# `bind` is folded into the attribute it stands for on the node a built-in
# component draws — its style merged, its responsive branch resolved — at the
# dispatch (ComposeBuilder#generate_component, which every responsive branch
# reaches merged; JsonUIShared::BindFold). No component
# reads `bind` itself. The layout normalizer leaves a node with a style or
# responsive overrides for this fold: folded before the merge, a layout `bind`
# beside a style's `isOn: true` was drawn bound (measured on a normalized
# layout), and a style's lone `bind` on a Date SelectBox was not drawn at all.
RSpec.describe 'kjui codegen: bind folded at the dispatch' do
  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  emit = lambda do |node|
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@responsive_counter, 0)
    builder.instance_variable_set(:@responsive_functions, [])
    builder.send(:generate_component, JSON.parse(JSON.generate(node)), 0).to_s
  end

  vectors = File.expand_path('../../../shared/core/bind_fold_vectors.json', __dir__)

  it 'draws each style case as the table says (the style merged, then folded)' do
    skip 'shared vectors not present in this layout' unless File.exist?(vectors)

    cases = JSON.parse(File.read(vectors))['style_cases']
    expect(cases.size).to be >= 2
    date, switch = cases
    merged = ->(c) { c['styles'].fetch(c['node']['style']).merge(c['node']).reject { |k, _| k == 'style' } }
    # a style's lone bind on a Date box: the box reads and writes the binding
    expect(emit.call(merged.call(date))).to include('value = data.day,', '"day" to newValue')
    # a style's isOn beside a layout bind: the static value, no binding
    code = emit.call(merged.call(switch))
    expect(code).not_to include('data.on')
    expect(code).to include('checked = seeded')
  end

  # A lone bind on each section the table names reaches the component as its
  # value attribute.
  {
    { 'type' => 'Switch' } => 'data.b',
    { 'type' => 'Toggle' } => 'data.b',
    { 'type' => 'CheckBox' } => 'data.b',
    { 'type' => 'Check' } => 'data.b',
    { 'type' => 'Slider' } => 'data.b',
    { 'type' => 'Segment', 'items' => %w[x y] } => 'data.b',
    { 'type' => 'Progress' } => 'data.b',
    { 'type' => 'SelectBox', 'items' => %w[x y] } => 'data.b',
    { 'type' => 'SelectBox', 'selectItemType' => 'Date' } => 'data.b',
    { 'type' => 'Radio', 'options' => %w[x y] } => 'data.b',
    { 'type' => 'TextField' } => 'data.b',
    { 'type' => 'TextView' } => 'data.b'
  }.each do |node, expected|
    it "binds a lone bind on #{node.values_at('type', 'selectItemType').compact.join(' ')}" do
      expect(emit.call(node.merge('bind' => '@{b}'))).to include(expected)
    end
  end

  # With no value and no bind — and with a static one — every section the
  # table names still draws (a reference to the removed `bind` read was left
  # in the Slider and raised NameError for a Slider without a value).
  it 'draws each section with no value, and with a static one' do
    [
      { 'type' => 'Switch' }, { 'type' => 'Toggle' }, { 'type' => 'CheckBox' }, { 'type' => 'Check' },
      { 'type' => 'Slider' }, { 'type' => 'Segment', 'items' => %w[x y] }, { 'type' => 'Progress' },
      { 'type' => 'SelectBox', 'items' => %w[x y] }, { 'type' => 'SelectBox', 'selectItemType' => 'Date' },
      { 'type' => 'Radio', 'options' => %w[x y] }, { 'type' => 'TextField' }, { 'type' => 'TextView' }
    ].each do |node|
      expect { emit.call(node) }.not_to raise_error, node.inspect
      static = JsonUIShared::BindFold.attributes_for(node['type'], node).first
      value = { 'selectedIndex' => 1, 'value' => 0.5, 'progress' => 0.5 }.fetch(static, static == 'isOn' ? true : 'x')
      expect { emit.call(node.merge(static => value)) }.not_to raise_error, "#{node.inspect} #{static}"
    end
  end

  # Each responsive branch is folded as it is drawn: a branch that gives the
  # Switch its own value draws it, and the other branch draws the binding.
  it 'folds each responsive branch as it is drawn' do
    code = emit.call('type' => 'Switch', 'bind' => '@{b}', 'responsive' => { 'compact' => { 'isOn' => true } })
    compact, other = code.split('} else {', 2)
    expect(compact).to include('checked = seeded')
    expect(compact).not_to include('data.b')
    expect(other).to include('data.b')
  end

  # generate_non_responsive_component (the branch drawer) draws only types the
  # table does not name, and hands every other type to generate_component,
  # where the fold is.
  it 'draws no type the table names outside generate_component' do
    src = File.read(File.expand_path('../../lib/compose/compose_builder.rb', __dir__))
    body = src[/def generate_non_responsive_component.*?\n      end\n/m]
    drawn = body.scan(/when (.+)$/).flatten.flat_map { |w| w.scan(/'([A-Za-z]+)'/).flatten }
    expect(drawn).to include('Label', 'Button')
    table = %w[Switch Toggle CheckBox Check Checkbox Slider Segment Progress SelectBox Radio TextField TextView]
    expect(drawn & table).to eq([])
    expect(body).to include('generate_component(json_data')
  end

  # selectItemType as written (the SSoT enum is ["Normal", "Date"]): "date" is
  # not a Date box on any path — the fold takes the list box's value, the box is
  # drawn as a list, and the validator names the value.
  it 'reads "date" as a list box in the fold, the draw and the validator alike' do
    node = { 'type' => 'SelectBox', 'selectItemType' => 'date', 'items' => %w[x y], 'bind' => '@{b}' }
    expect(JsonUIShared::BindFold.fold(node)).to include('selectedValue' => '@{b}')
    code = emit.call(node)
    expect(code).to include('SelectBox(')
    expect(code).not_to include('DateSelectBox(')
    expect(code).to include('value = data.b,')
    validator = KjuiTools::Core::AttributeValidator.new(:compose)
    validator.validate(node)
    expect(validator.warnings.join("\n")).to include("has invalid value 'date'. Valid values: Normal, Date")
    date = emit.call(node.merge('selectItemType' => 'Date'))
    expect(date).to include('DateSelectBox(', 'value = data.b,')
  end

  # The folded nodes draw Kotlin that compiles: a lone bind on a Switch, a
  # Slider and a Progress, and a style's lone bind on a Date SelectBox, bound
  # through the attribute each folds to.
  it 'draws Kotlin that compiles for folded nodes' do
    merged = lambda do |c|
      c['styles'].fetch(c['node']['style']).merge(c['node']).reject { |k, _| k == 'style' }
    end
    date = JSON.parse(File.read(vectors))['style_cases'].first
    code = [
      emit.call('type' => 'Switch', 'bind' => '@{on}'),
      emit.call('type' => 'Slider', 'bind' => '@{level}'),
      emit.call('type' => 'Progress', 'bind' => '@{done}'),
      emit.call(merged.call(date))
    ].join("\n")
    expect(code).to include('data.on', 'data.level', 'data.done', 'data.day')
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(code)}
      class Data(val on: Boolean = false, val level: Float = 0f, val done: Float = 0f, val day: String = "")
      class ViewModel { fun updateData(values: Map<String, Any?>) {} }
      fun screen(data: Data, viewModel: ViewModel) {
      #{code}
      }
    KOTLIN
  end

  # The dispatch takes an app's component by its spelling as written before
  # the fold, so the component is handed its node as written. A spelling the
  # app did not register is drawn and folded by the built-in — also when the
  # built-in's type is one the app registered (Toggle, drawn as Switch).
  it 'hands an app component (component_mappings) its node as written' do
    seen = []
    app = Class.new { define_singleton_method(:generate) { |json, *| seen << json.dup; '// the app draws Switch' } }
    allow(KjuiTools::Compose::ComposeBuilder).to receive(:custom_component_class) { |type| type == 'Switch' ? app : nil }
    expect(emit.call('type' => 'Switch', 'bind' => '@{b}')).to include('// the app draws Switch')
    # as written: its `bind` kept, no `isOn` (the dispatch's own marks, `_…`, aside)
    expect(seen.map { |json| json.reject { |key, _| key.start_with?('_') } }).to eq([{ 'type' => 'Switch', 'bind' => '@{b}' }])
    toggle = emit.call('type' => 'Toggle', 'bind' => '@{b}')
    expect(toggle).to include('data.b')
    expect(toggle).not_to include('// the app draws Switch')
    expect(seen.size).to eq(1)
  end

  # No component reads `bind`. Code only — a comment naming it does not count.
  # table_component.rb is not reached (Table is drawn as a Collection, whose
  # `bind` the table does not name and the validator names).
  it 'is read by no component but the unreached TableComponent' do
    token = /\['bind'\]|\["bind"\]/
    hits = lambda do |text, name|
      # map + compact, not filter_map: Ruby 2.6 (the consumer floor, a CI
      # leg) has no filter_map
      text.lines.each_with_index.map do |line, i|
        next if line.strip.start_with?('#')

        "#{name}:#{i + 1}" if line.sub(/#.*/, '') =~ token
      end.compact
    end
    expect(hits.call("          elsif json_data['bind'] && x\n", 'read').size).to eq(1)
    expect(hits.call("          # json_data['bind'] was read here\n", 'comment').size).to eq(0)

    lib = File.expand_path('../../lib/compose', __dir__)
    files = Dir.glob(File.join(lib, '**', '*.rb'))
    expect(files.size).to be > 40
    found = files.flat_map { |f| hits.call(File.read(f), f.delete_prefix("#{lib}/")) }
    expect(found.map { |h| h.split(':').first }.uniq).to eq(['components/table_component.rb'])
  end
end
