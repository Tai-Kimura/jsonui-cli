# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'

# sjui and kjui counted a refused layout as built in their build caches: the
# remedy the leaf refusal names ("regenerate the component with --container")
# was followed by a build that skipped the layout as cached and generated
# nothing for it, exit 0 (measured 2026-09-26 on 6ab928bf). rjui was not
# affected — it keeps no build cache and converts every layout on every build
# (measured the same night: its second build generated the layout). This holds
# it to that, with the same three builds as the other two faces, so a cache
# added here later meets the refused layout on its first day. Ticket
# build-caches-a-refused-layout-as-built.

RSpec.describe 'a refused layout, through rjui build (no build cache)' do
  def tool_root
    File.expand_path('../..', __dir__)
  end

  # A method, not a constant: a constant in a describe block is top-level.
  def name
    'CacheProbe'
  end

  def rjui(*args)
    Open3.capture2e('ruby', File.join(@dir, 'rjui_tools', 'bin', 'rjui'), *args, chdir: @dir)
  end

  def build
    log, status = rjui('build')
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
    Dir.glob(File.join(@dir, 'src', 'generated', '**', "#{layout}.{tsx,jsx}")).map { |f| File.read(f) }.join
  end

  before(:all) do
    @dir = Dir.mktmpdir('rjui_refused_cache')
    tool = File.join(@dir, 'rjui_tools')
    FileUtils.mkdir_p(tool)
    # `-L`: lib/core's files are relative links into shared/core.
    %w[bin lib].each do |d|
      raise "could not copy #{d}" unless system('cp', '-RL', File.join(tool_root, d), tool)
    end
    # No rjui.config.json: rjui writes its defaults (layouts in src/Layouts).
    @layouts = File.join(@dir, 'src', 'Layouts')
    FileUtils.mkdir_p(@layouts)
    @leaf = rjui('g', 'converter', 'Leaf', '--attributes', 'title:String', '--no-container', '--force')

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
    File.write(File.join(@layouts, 'plain.json'), JSON.generate(root.call([kid.call('plain_kid')])))

    # Each build's log and the views on disk right after it.
    views = -> { %w[LeafScreen TwoCells Plain].to_h { |v| [v, generated(v)] } }
    @log1, = build
    @views1 = views.call
    age_layouts
    @log2, = build
    @views2 = views.call
    @remedy = rjui('g', 'converter', 'Leaf', '--attributes', 'title:String', '--container', '--force')
    age_layouts
    @log3, = build
    @views3 = views.call
  end

  after(:all) { FileUtils.rm_rf(@dir) }

  it 'refuses both layouts on the first build and builds the plain one' do
    expect(@leaf.last.success?).to be(true), @leaf.first
    expect(@log1).to include("'Leaf' (id=leaf) takes no children")
    expect(@log1).to include('2 cellClasses declared without sections')
    expect(@views1['LeafScreen']).to be_empty
    expect(@views1['TwoCells']).to be_empty
    expect(@views1['Plain']).to include('"plain_kid"')
  end

  it 'converts every layout again on the next build — there is no cache to skip one' do
    expect(@log2.scan(%r{Processing: src/Layouts/\w+\.json}).uniq.size).to eq(3), @log2
    expect(@views2['LeafScreen']).to be_empty
  end

  it "generates the leaf's layout once the component takes children, the layout untouched" do
    expect(@remedy.last.success?).to be(true), @remedy.first
    expect(@log3).not_to include("'Leaf' (id=leaf) takes no children")
    expect(@views3['LeafScreen']).to include('"leaf_kid"'), @log3
  end

  it 'keeps refusing the layout that is still refused' do
    expect(@log3).to include('2 cellClasses declared without sections')
    expect(@views3['TwoCells']).to be_empty
  end
end
