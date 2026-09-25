# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'

# A layout the build refused is not built, so the build cache must not count
# it as built. It did: every layout the build looked at was recorded with its
# mtime, and one not modified since is skipped, so a refused layout was
# skipped from then on — and the remedy the leaf refusal names
# ("regenerate the component with --container") was followed by a build that
# printed "No files need updating (all cached)", generated nothing for the
# layout, and exited 0 (measured 2026-09-26 on 6ab928bf, sjui and kjui; rjui
# converts every layout on every build). Here the cache keeps each layout's
# mtime, and a refused one was recorded like a built one. Ticket
# build-caches-a-refused-layout-as-built.
#
# Three builds, the layouts' mtimes set an hour back before the second and the
# third — so no layout reads as modified since it was recorded, whichever
# second each build started in:
#   1  the leaf given a child and a Collection with two cellClasses and no
#      sections are refused; `plain` is built
#   2  nothing changed: plain is cached, the two refused layouts are converted
#      again (and refused again)
#   3  after `g converter Leaf --container --force` — the leaf refusal's own
#      remedy — the leaf's layout is generated, with its child
# and the other way in: `plain` holds a Box, a container, with a child —
#   4  Box made a leaf: plain and the variant are refused — every layout is
#      converted, a component having changed (before that ticket the cached
#      pass refused them; that path is not reached here any more)
#   5  nothing changed: plain is converted again, as a refused layout
# and a cached screen's variant (`variant@regular`, a Box with a child) is
# checked with it: at 4 it is refused on the cached run too. Until 1.8.121 the
# cached pass read the base alone, and sjui printed "all cached" with nothing
# named (kjui re-converts every screen with variants, so it named it).
#
# VARIANTS: a screen with a variant file is converted on every build here —
# the cache records the bases and never the variant files, so the variant
# reads as unrecorded (dirty). Measured, not changed: a cache miss, not a
# silence. Hence one more layout in each count than on sjui.
RSpec.describe 'a refused layout, through kjui build and the build cache' do
  def tool_root
    File.expand_path('../..', __dir__)
  end

  # A method, not a constant: a constant in a describe block is top-level.
  def name
    'CacheProbe'
  end

  def kjui(*args)
    Open3.capture2e('ruby', File.join(@dir, 'kjui_tools', 'bin', 'kjui'), *args, chdir: @dir)
  end

  def build
    log, status = kjui('build')
    [log.gsub(/\e\[[0-9;]*m/, ''), status]
  end

  # Every layout back to ONE fixed moment an hour before the first build —
  # older than any build, and the same moment each time: "now - 1h" taken
  # afresh moves forward between calls, and a cache that records each
  # layout's mtime reads that as a modification (it did, one run in two).
  def age_layouts
    @past ||= Time.at(Time.now.to_i - 3600)
    Dir.glob(File.join(@layouts, '*.json')).each { |f| File.utime(@past, @past, f) }
  end

  def generated(layout)
    Dir.glob(File.join(@dir, '**', "#{layout}GeneratedView.kt")).map { |f| File.read(f) }.join
  end

  before(:all) do
    @dir = Dir.mktmpdir('kjui_refused_cache')
    tool = File.join(@dir, 'kjui_tools')
    FileUtils.mkdir_p(tool)
    # `-L`: lib/core's files are relative links into shared/core.
    %w[bin lib].each do |d|
      raise "could not copy #{d}" unless system('cp', '-RL', File.join(tool_root, d), tool)
    end
    File.write(File.join(@dir, 'kjui.config.json'), JSON.pretty_generate(
      'mode' => 'compose', 'project_name' => name,
      'source_directory' => 'app/src/main', 'layouts_directory' => 'assets/Layouts',
      'styles_directory' => 'assets/Styles',
      'data_directory' => 'kotlin/com/example/app/data',
      'viewmodel_directory' => 'kotlin/com/example/app/viewmodels',
      'view_directory' => 'kotlin/com/example/app/views',
      'extension_directory' => 'kotlin/com/example/app/extensions',
      'adapter_directory' => 'kotlin/com/example/app/adapters',
      'resource_manager_directory' => 'app/src/main/kotlin/com/kotlinjsonui/generated',
      'package_name' => 'com.example.app',
      'string_files' => ['res/values/strings.xml'], 'use_network' => true
    ))
    @layouts = File.join(@dir, 'app', 'src', 'main', 'assets', 'Layouts')
    FileUtils.mkdir_p(@layouts)
    FileUtils.mkdir_p(File.join(@dir, 'app', 'src', 'main', 'assets', 'Styles'))
    @leaf = kjui('g', 'converter', 'Leaf', '--attr', 'title:String', '--no-container', '--force')
    @box = kjui('g', 'converter', 'Box', '--attr', 'title:String', '--container', '--force')

    kid = ->(id) { { 'type' => 'Label', 'id' => id, 'text' => id, 'width' => 'wrapContent', 'height' => 'wrapContent' } }
    root = ->(kids) { { 'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent', 'orientation' => 'vertical', 'child' => kids } }
    File.write(File.join(@layouts, 'leaf_screen.json'), JSON.generate(root.call([
      { 'type' => 'Leaf', 'id' => 'leaf', 'title' => 't', 'width' => 'matchParent', 'height' => 'wrapContent',
        'child' => [kid.call('leaf_kid')] }
    ])))
    File.write(File.join(@layouts, 'two_cells.json'), JSON.generate(root.call([
      { 'type' => 'Collection', 'id' => 'list', 'width' => 'matchParent', 'height' => 'matchParent',
        'cellClasses' => %w[RowA RowB], 'items' => '@{rows}' }
    ])))
    File.write(File.join(@layouts, 'variant.json'), JSON.generate(root.call([kid.call('variant_kid')])))
    File.write(File.join(@layouts, 'variant@regular.json'), JSON.generate(root.call([
      { 'type' => 'Box', 'id' => 'wide_box', 'title' => 'w', 'width' => 'matchParent', 'height' => 'wrapContent',
        'child' => [kid.call('wide_kid')] }
    ])))
    File.write(File.join(@layouts, 'plain.json'), JSON.generate(root.call([
      kid.call('plain_kid'),
      { 'type' => 'Box', 'id' => 'box', 'title' => 'b', 'width' => 'matchParent', 'height' => 'wrapContent',
        'child' => [kid.call('box_kid')] }
    ])))

    # Each build's log and the views on disk right after it.
    views = -> { %w[LeafScreen TwoCells Plain].to_h { |v| [v, generated(v)] } }
    @log1, = build
    @views1 = views.call
    age_layouts
    @log2, = build
    @views2 = views.call
    @remedy = kjui('g', 'converter', 'Leaf', '--attr', 'title:String', '--container', '--force')
    age_layouts
    @log3, = build
    @views3 = views.call
    @box_leaf = kjui('g', 'converter', 'Box', '--attr', 'title:String', '--no-container', '--force')
    age_layouts
    @log4, = build
    age_layouts
    @log5, = build
  end

  after(:all) { FileUtils.rm_rf(@dir) }

  it 'refuses both layouts on the first build and builds the plain one' do
    expect(@leaf.last.success?).to be(true), @leaf.first
    expect(@log1).to include("'Leaf' (id=leaf) takes no children")
    expect(@log1).to include('2 cellClasses declared without sections')
    expect(@views1['LeafScreen']).to be_empty
    expect(@views1['TwoCells']).to be_empty
    expect(@views1['Plain']).to include('"plain_kid"').and include('"box_kid"')
  end

  it 'converts the two refused layouts again on the next build, and only them' do
    expect(@log2).to include('Updating 3 of 4 files'), @log2 # and variant: see VARIANTS below
    expect(@log2).not_to include('all cached')
    expect(@views2['LeafScreen']).to be_empty
  end

  it "generates the leaf's layout once the component takes children, the layout untouched" do
    expect(@remedy.last.success?).to be(true), @remedy.first
    expect(@log3).not_to include("'Leaf' (id=leaf) takes no children")
    expect(@views3['LeafScreen']).to include('"leaf_kid"'), @log3
  end

  it 'keeps refusing the layout that is still refused, and caches the plain one' do
    expect(@log3).to include('2 cellClasses declared without sections')
    expect(@views3['TwoCells']).to be_empty
    # A component changed (`g converter`): every layout is converted since
    # build-cache-ignores-a-changed-component-definition-or-converter.
    expect(@log3).to include('every layout is converted').and(include('Updating 4 of 4 files')), @log3
  end

  it 'refuses a cached layout once a component in it becomes a leaf, and converts it again next time' do
    expect(@box_leaf.last.success?).to be(true), @box_leaf.first
    expect(@log4).to include("'Box' (id=box) takes no children")
    expect(@log4).to include("'Box' (id=wide_box) takes no children"), @log4
    expect(@log4).to include('variant@regular.json was not generated'), @log4
    expect(@log4).to include('every layout is converted').and(include('Updating 4 of 4 files')), @log4
    expect(@log5).to include('Updating 3 of 4 files'), @log5 # two_cells, plain and variant
  end
end
