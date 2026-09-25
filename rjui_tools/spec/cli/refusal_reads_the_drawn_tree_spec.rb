# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'

# The shared refusal (a leaf given children, several cellClasses without
# sections, a binding the declaration refuses) reads the tree a layout DRAWS —
# styles merged, includes expanded — and a partial is checked on its own.
# Until 1.8.121 sjui and kjui read a layout before its includes were
# expanded: a leaf given children inside an included layout was drawn with
# its children dropped and nothing refused, on every build; kjui's cached
# build checked a partial that its fresh build skipped. rjui converts each
# partial as a component of its own and refused it (measured 2026-09-26).
# Ticket leaf-refusal-does-not-see-inside-a-partial-include.
#
# One project, each row of the family table a layout of its own (X1-X7), one
# build; then a cached build after a component inside an included partial
# becomes a leaf, the layouts untouched (C1).
RSpec.describe 'the refusal reads the drawn tree, through rjui build' do
  def tool_root
    File.expand_path('../..', __dir__)
  end

  def run(*args)
    out, = Open3.capture2e('ruby', File.join(@dir, 'rjui_tools', 'bin', 'rjui'), *args, chdir: @dir)
    out.gsub(/\e\[[0-9;]*m/, '')
  end

  def gen(name, flag)
    run('g', 'converter', name, '--attributes', 'title:String', flag, '--force')
  end

  # "[error] <file>: <message>" — the file each refusal names.
  def refused(log)
    log.scan(/\[error\] ([\w@.]+): /).flatten.uniq.sort
  end

  before(:all) do
    @dir = Dir.mktmpdir('rjui_drawn_tree')
    tool = File.join(@dir, 'rjui_tools')
    FileUtils.mkdir_p(tool)
    # `-L`: lib/core's files are relative links into shared/core.
    %w[bin lib].each do |d|
      raise "could not copy #{d}" unless system('cp', '-RL', File.join(tool_root, d), tool)
    end
    # No rjui.config.json: rjui writes its defaults (layouts in src/Layouts).
    @layouts = File.join(@dir, 'src', 'Layouts')
    FileUtils.mkdir_p(@layouts)
    @scaffolds = [gen('Leaf', '--no-container'), gen('Box', '--container')]

    kid = ->(id) { { 'type' => 'Label', 'id' => id, 'text' => id, 'width' => 'wrapContent', 'height' => 'wrapContent' } }
    node = ->(type, id, kids) { { 'type' => type, 'id' => id, 'title' => 't', 'width' => 'matchParent', 'height' => 'wrapContent', 'child' => kids } }
    screen = ->(kids) { { 'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent', 'orientation' => 'vertical', 'child' => kids } }
    part = ->(kids, partial: true) { { 'type' => 'View', 'id' => 'part_root', 'width' => 'matchParent', 'height' => 'wrapContent', 'child' => kids }.merge(partial ? { 'partial' => true } : {}) }
    two_cells = { 'type' => 'Collection', 'id' => 'list', 'width' => 'matchParent', 'height' => 'matchParent', 'cellClasses' => %w[RowA RowB], 'items' => '@{rows}' }
    files = {
      'x1_home' => screen.([kid.('h1'), { 'include' => 'x1_part' }]),
      'x1_part' => part.([node.('Leaf', 'leaf1', [kid.('kid1')])], partial: false),
      'x2_home' => screen.([kid.('h2'), { 'include' => 'x2_part' }]),
      'x2_part' => part.([node.('Leaf', 'leaf2', [kid.('kid2')])]),
      'x3_home' => screen.([kid.('h3'), { 'include' => 'x3_outer' }]),
      'x3_outer' => part.([{ 'include' => 'x3_inner' }]),
      'x3_inner' => part.([node.('Leaf', 'leaf3', [kid.('kid3')])]),
      'x4_home' => screen.([kid.('h4')]),
      'x4_home@regular' => screen.([{ 'include' => 'x4_part' }]),
      'x4_part' => part.([node.('Leaf', 'leaf4', [kid.('kid4')])]),
      'x5_home' => screen.([kid.('h5'), { 'include' => 'x5_part' }]),
      'x5_part' => part.([two_cells]),
      'x6_home' => screen.([kid.('h6'), { 'include' => 'x6_part', 'id' => 'hero' }]),
      'x6_part' => part.([node.('Leaf', 'leaf6', [kid.('kid6')])]),
      'x7_home' => screen.([{ 'type' => 'Collection', 'id' => 'rows7', 'width' => 'matchParent', 'height' => 'matchParent', 'cellClasses' => ['x7_cell'], 'items' => '@{rows}' }]),
      'x7_cell' => part.([node.('Leaf', 'leaf7', [kid.('kid7')])]),
      'c1_home' => screen.([kid.('hc'), { 'include' => 'c1_part' }]),
      'c1_part' => part.([node.('Box', 'box_c1', [kid.('kid_c1')])])
    }
    files.each { |name, json| File.write(File.join(@layouts, "#{name}.json"), JSON.generate(json)) }
    @fresh = run('build')

    # C1: Box made a leaf; every layout an hour back, so the build is cached.
    @box_leaf = gen('Box', '--no-container')
    past = Time.at(Time.now.to_i - 3600)
    Dir.glob(File.join(@layouts, '*.json')).each { |f| File.utime(past, past, f) }
    @cached = run('build')
  end

  after(:all) { FileUtils.rm_rf(@dir) }

  it 'scaffolds the leaf and the box' do
    definition = lambda do |name|
      path = Dir.glob(File.join(@dir, '*_tools', '**', 'attribute_definitions', "#{name}.json")).first
      path ? JSON.parse(File.read(path))[name] : {}
    end
    expect(definition.call('Leaf')).to include('_children' => 'none'), @scaffolds.join("\n")
    expect(definition.call('Box')).to include('_children' => 'none') # made a leaf for C1
  end

  # rjui converts each included layout as a component of its own, so it is the
  # included file that is refused — as it was before 1.8.121.
  {
    'X1 an included screen layout' => %w[x1_part.json],
    'X2 an included partial' => %w[x2_part.json],
    'X3 a partial including a partial' => %w[x3_inner.json],
    'X4 a variant including a partial' => %w[x4_part.json],
    'X5 cellClasses without sections, inside a partial' => %w[x5_part.json],
    'X6 an include with an id' => %w[x6_part.json],
    'X7 a Collection cell layout' => %w[x7_cell.json]
  }.each do |row, files|
    it "refuses #{row} where rjui draws it" do
      prefix = row[/X\d/].downcase
      expect(refused(@fresh).select { |f| f.start_with?(prefix) }).to eq(files.sort), @fresh
    end
  end

  it 'answers the same on the next build: a component in an included partial made a leaf (C1)' do
    expect(refused(@cached)).to include('c1_part.json'), @cached
  end
end
