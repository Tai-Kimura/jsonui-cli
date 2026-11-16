# frozen_string_literal: true

require 'ripper'
require 'json'
require 'tmpdir'
require 'compose/compose_builder'
require 'compose/include_expander'
require 'core/layout_path'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# The emitted Kotlin is a function of the layout. A Radio item with no id was
# named `"radio_#{rand(1000)}"` — its selection value — so every build of the
# same layout emitted different Kotlin, and two items could draw the same
# number (docs/bugs/kjui-radio-default-id-is-random.md). The name is now the
# item's position (shared/core/layout_path.rb, JsonUIShared::LayoutPath):
# `radio_0_2_1`, the same on every build and unique within the view. The
# rule is shared with the sjui codegen: both run
# shared/core/layout_path_vectors.json.
RSpec.describe 'kjui Radio default id is its position in the layout' do
  shared = File.expand_path('../../../shared/core', __dir__)
  lib = File.expand_path('../../lib', __dir__)

  # --- the rule: the shared vectors -------------------------------------
  vectors_path = File.join(shared, 'layout_path_vectors.json')

  it 'stamps every path the shared vectors expect' do
    skip 'shared/core/layout_path_vectors.json not present in this layout' unless File.exist?(vectors_path)

    cases = JSON.parse(File.read(vectors_path))['cases']
    expect(cases.size).to be >= 8
    cases.each do |c|
      layout = JSON.parse(JSON.generate(c['layout']))
      Dir.mktmpdir('layout_path_vectors') do |dir|
        (c['includes'] || {}).each { |name, body| File.write(File.join(dir, "#{name}.json"), JSON.generate(body)) }
        layout = KjuiTools::Compose::IncludeExpander.process_includes(layout, dir, nil, dir) if c['includes']
      end
      JsonUIShared::LayoutPath.stamp!(layout)
      paths = {}
      walk = lambda do |node|
        next unless node.is_a?(Hash)

        paths[node['id']] = node[JsonUIShared::LayoutPath::KEY] if node['id']
        JsonUIShared::LayoutPath.children(node).each { |child| walk.call(child) }
      end
      walk.call(layout)
      expect(paths.slice(*c['expect'].keys)).to eq(c['expect']), c['name']
    end
  end

  # --- the family: nothing nondeterministic reaches the emitter -----------
  # Code tokens only (Ripper), so a comment or a string that names `rand`
  # does not count: the random source, a clock, a pid, an object's identity.
  # Counters are the other half of the family and are read by the build
  # arm below (they reset per layout at the build entry points).
  idents = %w[rand srand shuffle sample object_id __id__]
  consts = %w[Random SecureRandom]
  clock = { 'Time' => %w[now new], 'Date' => %w[today], 'DateTime' => %w[now], 'Process' => %w[pid clock_gettime] }
  sources_in = lambda do |source, name|
    toks = Ripper.lex(source).reject { |_, t, _, _| %i[on_sp on_ignored_nl on_nl].include?(t) }
    toks.each_with_index.map do |((line, _), type, text, _), i|
      hit = (type == :on_ident && idents.include?(text) && toks[i - 1][1] != :on_symbeg) ||
            (type == :on_const && consts.include?(text)) ||
            (type == :on_const && clock[text] && toks[i + 1] && toks[i + 1][1] == :on_period &&
             toks[i + 2] && clock[text].include?(toks[i + 2][2]))
      "#{name}:#{line}: #{text}" if hit
    end.compact
  end

  it 'the scan tells a call from a comment or a string (both sides)' do
    expect(sources_in.call(%(id = "radio_\#{rand(1000)}"\n), 'call').size).to eq(1)
    expect(sources_in.call(%(t = Time.now\n), 'clock').size).to eq(1)
    expect(sources_in.call(%(# it was rand(1000)\nx = "rand(1000) Time.now"\n), 'text')).to be_empty
  end

  # The Compose emitter and the core it calls. (lib/xml is the frozen XML
  # path: its one clock stamps a drawable-cache file, not emitted code.)
  it 'no emitter source draws on randomness, a clock, a pid or an identity' do
    files = %w[compose core].flat_map { |d| Dir.glob(File.join(lib, d, '**', '*.rb')) }.sort
    expect(files.size).to be > 80
    hits = files.flat_map { |path| sources_in.call(File.read(path), path.sub("#{lib}/", '')) }
    expect(hits).to be_empty, hits.join("\n")
  end

  # --- the emit ----------------------------------------------------------
  # A builder as the build entry leaves it (the responsive counter is set
  # there, not in the constructor).
  emit = lambda do |node|
    comp = JSON.parse(JSON.generate(node))
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@responsive_counter, 0)
    builder.instance_variable_set(:@responsive_functions, [])
    builder.send(:generate_component, comp, 0).to_s
  end
  # The name an item writes on selection: to the group's Data property, or —
  # for a group the layout does not bind — to the view's own map
  # (RadioComponent, LocalRadioGroupSelections).
  values = lambda do |code|
    code.scan(/(?:"selectedRadiogroup" to |radioGroups\["default"\] = )"(radio_[\d_]+)"/).flatten.uniq
  end

  group = {
    'type' => 'View', 'orientation' => 'vertical',
    'child' => [
      { 'type' => 'Radio', 'text' => 'first' },
      { 'type' => 'View', 'child' => [{ 'type' => 'Radio', 'text' => 'nested' }] },
      { 'type' => 'Radio', 'text' => 'first' },
      { 'type' => 'Radio', 'id' => 'named', 'text' => 'named' }
    ]
  }

  it 'names each id-less item by its position, and an explicit id wins' do
    code = emit.call(group)
    expect(values.call(code)).to eq(%w[radio_0_0 radio_0_1_0 radio_0_2])
    expect(code).to include('radioGroups["default"] = "named"')
  end

  it 'emits the same bytes for the same layout, every time' do
    expect(emit.call(group)).to eq(emit.call(group))
  end

  it 'a responsive branch keeps the item where it is' do
    layout = { 'type' => 'View', 'child' => [
      { 'type' => 'Label', 'text' => 'x' },
      { 'type' => 'View', 'child' => [{ 'type' => 'Radio', 'text' => 'r' }],
        'responsive' => { 'regular' => { 'padding' => 4 } } }
    ] }
    expect(values.call(emit.call(layout))).to eq(%w[radio_0_1_0])
  end

  # Two whole builds of one layout, through the build's own entry point
  # (build_file: style merge, include expansion, the stamp, the counters'
  # reset), each into a clean directory: the generated view is byte-identical.
  describe 'two builds of the same layout' do
    let(:temp_dir) { Dir.mktmpdir('radio_position_build') }
    let(:layouts_dir) { File.join(temp_dir, 'src/main/assets/Layouts') }
    let(:view_dir) { File.join(temp_dir, 'src/main/kotlin/com/example/app/views') }
    let(:config) do
      { 'source_directory' => 'src/main', 'layouts_directory' => 'assets/Layouts',
        'view_directory' => 'kotlin/com/example/app/views', 'package_name' => 'com.example.app',
        'project_path' => temp_dir }
    end

    before do
      FileUtils.mkdir_p(layouts_dir)
      FileUtils.mkdir_p(view_dir)
      allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
      allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
      allow(KjuiTools::Core::ProjectFinder).to receive(:get_package_name).and_return('com.example.app')
      allow(Dir).to receive(:pwd).and_return(temp_dir)
    end

    after { FileUtils.rm_rf(temp_dir) }

    it 'are byte-identical' do
      File.write(File.join(layouts_dir, 'radio_screen.json'), JSON.pretty_generate(
        group.merge('type' => 'SafeAreaView', 'data' => [{ 'name' => 'title', 'class' => 'String' }])
      ))
      generated = File.join(view_dir, 'radio_screen', 'RadioScreenGeneratedView.kt')
      builds = 2.times.map do
        FileUtils.rm_rf(File.dirname(generated))
        expect { KjuiTools::Compose::ComposeBuilder.new.build_file(File.join(layouts_dir, 'radio_screen.json')) }
          .to output(/./).to_stdout
        File.read(generated)
      end
      expect(values.call(builds.first)).to eq(%w[radio_0_0 radio_0_1_0 radio_0_2])
      expect(builds.last).to eq(builds.first)
    end
  end

  # The items, as emitted, type-check (stubs: ComposeStubUniverse
  # .common_stages — "well-typed Kotlin", not "valid Compose").
  it 'compiles the id-less items' do
    tree = JSON.parse(JSON.generate(group))
    JsonUIShared::LayoutPath.stamp!(tree)
    items = JsonUIShared::LayoutPath.children(tree).select { |c| c['type'] == 'Radio' }
    emitted = items.each_with_index.map do |item, i|
      "fun item#{i}(data: Data, viewModel: ViewModel) {\n#{KjuiTools::Compose::ComposeBuilder.new.send(:generate_component, item, 0)}\n}"
    end.join("\n\n")
    expect(emitted).to include('"radio_0_0"', '"radio_0_2"')
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(emitted)}
      class Data(val selectedRadiogroup: String = "")
      class ViewModel { fun updateData(values: Map<String, Any?>) {} }
      #{emitted}
    KOTLIN
  end
end
