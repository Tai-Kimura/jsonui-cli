# frozen_string_literal: true

require 'json'
require 'open3'
require 'rbconfig'
require 'tmpdir'
require 'fileutils'

# A layout written with type-synonym and alias spellings builds exactly what
# the same layout written canonically builds: the same files, byte for byte,
# and the same build log once the log's type names are read as the types they
# are drawn as. The dispatch draws a spelling as its drawn type
# (shared/core/type_synonyms.rb); everything else that classifies a node by
# its type — the Data model, the hooks, the ViewModel base, the imports, the
# focus refs, the a11y roles, the validators — must read it the same way, or
# the drawn element and what it is given disagree.
#
# Measured before this spec (2026-09-26, this spec on jsonui-cli e1713527):
# ProbeData.kt, ProbeViewModel.kt and ProbeGeneratedView.kt differed, and the
# logs by 40 canonical-only and 2 spelled-only lines.
#
# The spellings are every entry of type_synonyms.json and every `_alias_of`
# section of attribute_definitions.json, each placed as written, with the
# handlers the pre-passes read, as a SafeAreaView's child, with a
# responsive override and twice in a View with an id; as a ScrollView's only
# child in an example of its own.
RSpec.describe 'kjui build: a synonym or alias spelling builds what its canonical spelling builds' do
  KJUI_INV_ROOT = File.expand_path('../..', __dir__)
  KJUI_INV_SHARED = File.join(KJUI_INV_ROOT, 'lib', 'core')

  synonyms = JSON.parse(File.read(File.join(KJUI_INV_SHARED, 'type_synonyms.json')))['synonyms']
  definitions = JSON.parse(File.read(File.join(KJUI_INV_SHARED, 'attribute_definitions.json')))
  aliases = definitions.select { |_, v| v.is_a?(Hash) && v['_alias_of'].is_a?(String) }.transform_values { |v| v['_alias_of'] }
  rows = synonyms.map { |sp, e| [sp, e['render_as'] || e['canonical'], e.reject { |k, _| %w[canonical render_as].include?(k) }] } +
         aliases.map { |sp, target| [sp, target, {}] }

  # What each drawn type needs to draw, with a binding the pre-passes read.
  needs = lambda do |target, i|
    v = "v#{i}"
    {
      'Label' => { 'text' => "@{#{v}}" }, 'TextView' => { 'text' => "@{#{v}}", 'hint' => 'h' },
      'TextField' => { 'text' => "@{#{v}}", 'hint' => 'h' }, 'Image' => { 'srcName' => 'probe' },
      'CircleImage' => { 'srcName' => 'probe' }, 'NetworkImage' => { 'url' => "@{#{v}}" },
      'SelectBox' => { 'items' => %w[a b], 'selectedIndex' => "@{#{v}}" }, 'CheckBox' => { 'isOn' => "@{#{v}}", 'label' => 'L' },
      'Radio' => { 'text' => 'r', 'group' => "g#{i}", 'selectedValue' => "@{#{v}}", 'value' => 'a' },
      'Segment' => { 'items' => %w[a b], 'selectedIndex' => "@{#{v}}" }, 'Slider' => { 'value' => "@{#{v}}" },
      'Progress' => { 'progress' => "@{#{v}}" }, 'Indicator' => {},
      'View' => { 'child' => [{ 'type' => 'Label', 'id' => "c#{i}", 'text' => 'c' }] },
      'ScrollView' => { 'child' => [{ 'type' => 'Label', 'id' => "c#{i}", 'text' => 'c' }] },
      'Collection' => { 'items' => "@{#{v}}", 'cellClasses' => [{ 'className' => 'ProbeCell' }] },
      'GradientView' => { 'gradient' => ['#FF0000', '#0000FF'] }, 'Blur' => {}, 'Web' => { 'url' => "@{#{v}}" },
      'Switch' => { 'isOn' => "@{#{v}}" }
    }.fetch(target)
  end
  handlers = { 'Switch' => %w[onValueChange], 'CheckBox' => %w[onValueChange], 'Slider' => %w[onValueChange],
               'Radio' => %w[onValueChange], 'Segment' => %w[onValueChange], 'SelectBox' => %w[onValueChange],
               'TextField' => %w[onTextChange], 'TextView' => %w[onTextChange] }

  contexts = {
    'as written' => ->(n, _t, _i) { n },
    'with handlers' => lambda do |n, t, i|
      n.merge('id' => "h#{i}").merge((handlers[t] || []).to_h { |h| [h, "@{h#{h}#{i}}"] }).merge('onClick' => "@{tap#{i}}")
    end,
    "as a SafeAreaView's child" => ->(n, _t, i) { { 'type' => 'SafeAreaView', 'id' => "a#{i}", 'child' => [n.merge('id' => "sa#{i}")] } },
    'with a responsive override' => ->(n, _t, i) { n.merge('id' => "r#{i}", 'responsive' => { 'regular' => { 'visibility' => 'visible' } }) },
    # twice in a View with an id: a parent that counts its children's
    # accessibility elements (the merge-hazard anchor) counts two or none
    'twice in a View with an id' => lambda do |n, _t, i|
      { 'type' => 'View', 'id' => "p#{i}", 'child' => [n.merge('id' => "t#{i}"), n.merge('id' => "u#{i}")] }
    end
  }

  layout_for = lambda do |spelled|
    children = rows.each_with_index.flat_map do |(spelling, target, implied), i|
      node = { 'type' => spelled ? spelling : target, 'id' => "n#{i}" }.merge(needs.call(target, i))
      node = node.merge(implied) unless spelled
      contexts.values.map { |context| context.call(node, target, i) }
    end
    { 'type' => 'View', 'id' => 'root', 'orientation' => 'vertical', 'child' => children }
  end

  build = lambda do |layout|
    dir = Dir.mktmpdir('kjui_spelling')
    FileUtils.ln_s(KJUI_INV_ROOT, File.join(dir, 'kjui_tools'))
    File.write(File.join(dir, 'kjui.config.json'), JSON.pretty_generate(
      'mode' => 'compose', 'project_name' => 'Probe', 'source_directory' => 'app/src/main',
      'layouts_directory' => 'assets/Layouts', 'styles_directory' => 'assets/Styles',
      'data_directory' => 'kotlin/com/example/app/data', 'viewmodel_directory' => 'kotlin/com/example/app/viewmodels',
      'view_directory' => 'kotlin/com/example/app/views', 'package_name' => 'com.example.app',
      'string_files' => ['res/values/strings.xml'], 'use_network' => true
    ))
    FileUtils.mkdir_p(File.join(dir, 'app/src/main/assets/Layouts'))
    FileUtils.mkdir_p(File.join(dir, 'app/src/main/assets/Styles'))
    File.write(File.join(dir, 'app/src/main/assets/Layouts/probe.json'), JSON.pretty_generate(layout))
    log, status = Open3.capture2e({ 'JUI_STAGE_FAILURES' => File.join(dir, 'ledger.json') },
                                  RbConfig.ruby, File.join(dir, 'kjui_tools/bin/kjui'), 'build', chdir: dir)
    files = Dir.glob(File.join(dir, '**/*'), File::FNM_DOTMATCH).reject do |f|
      File.directory?(f) || f.include?('/kjui_tools/') || f.include?('/Layouts/') || f.end_with?('ledger.json') ||
        f.include?('/.jsonui') || f.include?('cache')
    end
    [status.exitstatus, log, files.to_h { |f| [f.sub("#{dir}/", ''), File.read(f)] }, dir]
  ensure
    nil
  end

  before(:all) do
    @canonical = build.call(layout_for.call(false))
    @spelled = build.call(layout_for.call(true))
  end

  # A spelling as a ScrollView's only child: the ScrollView reads its child's
  # type as written to pick its axis (scrollview_component.rb, the `View`
  # child check), so an HStack / Row child scrolls vertically where the View
  # with orientation horizontal it is drawn as scrolls sideways (LazyRow).
  # That component is moved onto TypeSynonyms.drawn by its owner's change;
  # when it lands this example passes and RSpec reports the pending as fixed
  # — then this becomes a plain example.
  it "builds a spelling as a ScrollView's only child as its canonical spelling" do
    pending 'scrollview_component.rb reads its only child as written (moved onto TypeSynonyms.drawn separately)'
    only_child = lambda do |spelled|
      children = rows.each_with_index.map do |(spelling, target, implied), i|
        node = { 'type' => spelled ? spelling : target, 'id' => "w#{i}" }.merge(needs.call(target, i))
        node = node.merge(implied) unless spelled
        { 'type' => 'ScrollView', 'id' => "s#{i}", 'child' => [node] }
      end
      { 'type' => 'View', 'id' => 'root', 'orientation' => 'vertical', 'child' => children }
    end
    a = build.call(only_child.call(false))
    b = build.call(only_child.call(true))
    begin
      expect(a[2].keys.reject { |k| a[2][k] == b[2][k] }).to eq([])
    ensure
      [a, b].each { |r| FileUtils.rm_rf(r[3]) }
    end
  end

  after(:all) { [@canonical, @spelled].each { |r| FileUtils.rm_rf(r[3]) if r } }

  it 'reads every entry of the table and every declared alias (control)' do
    expect(rows.size).to be >= 50
    spelled_types = layout_for.call(true)['child'].map { |n| n['type'] }.uniq
    expect(spelled_types).to include('Textarea', 'AsyncImage', 'HStack', 'EditText', 'Toggle')
  end

  it 'builds both, and what it compares is the build output (control)' do
    expect([@canonical[0], @spelled[0]]).to eq([0, 0])
    expect(@canonical[2].keys).to include(a_string_ending_with('data/ProbeData.kt'),
                                          a_string_ending_with('views/probe/ProbeGeneratedView.kt'))
  end

  it 'writes the same files, byte for byte' do
    expect(@spelled[2].keys.sort).to eq(@canonical[2].keys.sort)
    differ = @canonical[2].keys.reject { |k| @canonical[2][k] == @spelled[2][k] }
    expect(differ).to eq([])
  end

  it 'logs the same, read as the drawn types' do
    norm = ->(log) { log.gsub(/\e\[[0-9;]*m/, '').gsub(%r{/[^ ]*kjui_spelling[^/ ]*}, '<dir>').lines.map(&:rstrip) }
    by_length = rows.sort_by { |spelling, _, _| -spelling.size }
    spelled = norm.call(@spelled[1]).map do |line|
      by_length.reduce(line) { |acc, (spelling, target, _)| acc.gsub(/(?<![A-Za-z])#{Regexp.escape(spelling)}(?![A-Za-z])/, target) }
    end
    expect(spelled).to eq(norm.call(@canonical[1]))
  end
end
