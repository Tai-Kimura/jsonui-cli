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
# Measured before this spec (2026-09-26, jsonui-cli e1713527): Probe.jsx,
# ProbeData.js, useProbeViewModel.ts and ProbeViewModelBase.ts differed — a
# Textarea's focus ref was emitted and never declared, an AsyncImage lost its
# NetworkImage import, a Toggle's binding was typed as a CheckBox's.
#
# The spellings are every entry of type_synonyms.json and every `_alias_of`
# section of attribute_definitions.json, each placed as written, with the
# handlers the pre-passes read, as a ScrollView's only child, as a
# SafeAreaView's child, with a responsive override and twice in a View
# with an id.
RSpec.describe 'rjui build: a synonym or alias spelling builds what its canonical spelling builds' do
  RJUI_INV_ROOT = File.expand_path('../..', __dir__)
  RJUI_INV_SHARED = File.join(RJUI_INV_ROOT, 'lib', 'core')

  synonyms = JSON.parse(File.read(File.join(RJUI_INV_SHARED, 'type_synonyms.json')))['synonyms']
  definitions = JSON.parse(File.read(File.join(RJUI_INV_SHARED, 'attribute_definitions.json')))
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
    "as a ScrollView's only child" => ->(n, _t, i) { { 'type' => 'ScrollView', 'id' => "s#{i}", 'child' => [n.merge('id' => "w#{i}")] } },
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
    dir = Dir.mktmpdir('rjui_spelling')
    FileUtils.ln_s(RJUI_INV_ROOT, File.join(dir, 'rjui_tools'))
    FileUtils.mkdir_p(File.join(dir, 'src/Layouts'))
    FileUtils.mkdir_p(File.join(dir, 'src/Styles'))
    FileUtils.mkdir_p(File.join(dir, 'src/viewmodels'))
    File.write(File.join(dir, 'src/Layouts/probe.json'), JSON.pretty_generate(layout))
    # a hand-written ViewModel, so the hook and the ViewModel base are built
    File.write(File.join(dir, 'src/viewmodels/ProbeViewModel.ts'), "export class ProbeViewModel {}\n")
    log, status = Open3.capture2e({ 'JUI_STAGE_FAILURES' => File.join(dir, 'ledger.json') },
                                  RbConfig.ruby, File.join(dir, 'rjui_tools/bin/rjui'), 'build', chdir: dir)
    files = Dir.glob(File.join(dir, '**/*'), File::FNM_DOTMATCH).reject do |f|
      File.directory?(f) || f.include?('/rjui_tools/') || f.include?('/Layouts/') || f.end_with?('ledger.json') ||
        f == File.join(dir, 'src/viewmodels/ProbeViewModel.ts') ||
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

  after(:all) { [@canonical, @spelled].each { |r| FileUtils.rm_rf(r[3]) if r } }

  it 'reads every entry of the table and every declared alias (control)' do
    expect(rows.size).to be >= 50
    spelled_types = layout_for.call(true)['child'].map { |n| n['type'] }.uniq
    expect(spelled_types).to include('Textarea', 'AsyncImage', 'HStack', 'EditText', 'Toggle')
  end

  it 'builds both, and what it compares is the build output (control)' do
    expect([@canonical[0], @spelled[0]]).to eq([0, 0])
    expect(@canonical[2].keys).to include(a_string_ending_with('generated/components/Probe.jsx'),
                                          a_string_ending_with('data/ProbeData.js'),
                                          a_string_ending_with('hooks/useProbeViewModel.ts'),
                                          a_string_ending_with('viewmodels/ProbeViewModelBase.ts'))
  end

  it 'writes the same files, byte for byte' do
    expect(@spelled[2].keys.sort).to eq(@canonical[2].keys.sort)
    differ = @canonical[2].keys.reject { |k| @canonical[2][k] == @spelled[2][k] }
    expect(differ).to eq([])
  end

  it 'logs the same, read as the drawn types' do
    norm = ->(log) { log.gsub(/\e\[[0-9;]*m/, '').gsub(%r{/[^ ]*rjui_spelling[^/ ]*}, '<dir>').lines.map(&:rstrip) }
    by_length = rows.sort_by { |spelling, _, _| -spelling.size }
    spelled = norm.call(@spelled[1]).map do |line|
      by_length.reduce(line) { |acc, (spelling, target, _)| acc.gsub(/(?<![A-Za-z])#{Regexp.escape(spelling)}(?![A-Za-z])/, target) }
    end
    expect(spelled).to eq(norm.call(@canonical[1]))
  end
end
