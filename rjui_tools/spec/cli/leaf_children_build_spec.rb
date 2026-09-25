# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'

# A component scaffolded as a leaf (`rjui g converter <Name> --no-container`)
# that a layout gives children: the build refuses the layout by name.
#
# Before 1.8.121 (measured on e1a85ca2) the leaf's converter emitted
# `<Leaf … />` whatever the layout held, so the children were dropped at
# generation and the build went on. Ticket
# sjui-leaf-custom-component-cannot-reject-children.
#
# The tool is COPIED (links dereferenced), not linked: `g converter` writes
# its converter into the tool's own converters/extensions and the build
# loads it from there, so a linked checkout would be written into.
RSpec.describe 'a leaf given children, through rjui build' do
  def tool_root
    File.expand_path('../..', __dir__)
  end

  before(:all) do
    @dir = Dir.mktmpdir('rjui_leaf')
    tool = File.join(@dir, 'rjui_tools')
    FileUtils.mkdir_p(tool)
    # `-L`: lib/core's files are relative links into shared/core.
    %w[bin lib].each do |d|
      raise "could not copy #{d}" unless system('cp', '-RL', File.join(tool_root, d), tool)
    end
    # No rjui.config.json: rjui writes its defaults (layouts in src/Layouts,
    # output under src/generated). A partial one leaves the rest nil.
    @layouts = File.join(@dir, 'src', 'Layouts')
    FileUtils.mkdir_p(@layouts)

    @scaffold = {
      'Shelf' => ['--container'], 'Auto' => [], 'Leaf' => ['--no-container']
    }.map do |component, mode|
      Open3.capture2e('ruby', File.join(tool, 'bin', 'rjui'), 'g', 'converter', component,
                      '--attributes', 'title:String', '--force', *mode, chdir: @dir)
    end

    node = ->(type, id, kids = nil) {
      n = { 'type' => type, 'id' => id, 'title' => id, 'width' => 'matchParent', 'height' => 'wrapContent' }
      n['child'] = kids if kids
      n
    }
    kid = ->(id) { { 'type' => 'Label', 'id' => id, 'text' => id, 'width' => 'wrapContent', 'height' => 'wrapContent' } }
    root = ->(kids) { { 'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent', 'orientation' => 'vertical', 'child' => kids } }
    File.write(File.join(@layouts, 'refused.json'), JSON.generate(root.call([
      node.call('Leaf', 'leaf', [kid.call('leaf_kid')])
    ])))
    File.write(File.join(@layouts, 'healthy.json'), JSON.generate(root.call([
      node.call('Leaf', 'leaf_alone'),
      node.call('Shelf', 'shelf', [kid.call('shelf_kid')]),
      node.call('Auto', 'auto', [kid.call('auto_kid')])
    ])))

    @ledger = File.join(@dir, 'stage-failures.json')
    @log, @status = Open3.capture2e({ 'JUI_STAGE_FAILURES' => @ledger },
                                    'ruby', File.join(tool, 'bin', 'rjui'), 'build', chdir: @dir)
    @log = @log.gsub(/\e\[[0-9;]*m/, '')
  end

  after(:all) { FileUtils.rm_rf(@dir) }

  def ledger
    File.exist?(@ledger) ? JSON.parse(File.read(@ledger)) : []
  end

  def generated(layout)
    Dir.glob(File.join(@dir, 'src', 'generated', '**', "#{layout}.{tsx,jsx}")).map { |f| File.read(f) }.join
  end

  it 'scaffolds the three modes' do
    expect(@scaffold.map { |_, s| s.success? }).to all(be(true)), @scaffold.map(&:first).join("\n")
    defs = File.join(@dir, 'rjui_tools', 'lib', 'react', 'converters', 'extensions', 'attribute_definitions')
    expect(JSON.parse(File.read(File.join(defs, 'Leaf.json')))['Leaf']).to include('_children' => 'none')
    expect(JSON.parse(File.read(File.join(defs, 'Auto.json')))['Auto'].keys).to include('child', 'children')
  end

  it 'records the leaf with children as the one incomplete stage, naming the node and the child' do
    entries = ledger.select { |e| e['stage'] == 'layout' }
    expect(entries.size).to eq(1), "#{ledger.inspect}\n#{@log}"
    expect(entries.first['message']).to include('refused.json').and include('was not generated')
      .and include("'Leaf' (id=leaf) takes no children").and include('child[0] (id=leaf_kid)')
  end

  it 'writes no component for the refused layout' do
    expect(generated('Refused')).to be_empty
  end

  it 'says nothing about a leaf without children, and draws the containers\' children' do
    expect(@log).not_to include("'Leaf' (id=leaf_alone)")
    view = generated('Healthy')
    expect(view).to include('"leaf_alone"')
    expect(view).to include('"shelf_kid"').and include('"auto_kid"')
  end

  it "no longer says \"Unknown attribute 'child'\" for the default mode or the leaf" do
    expect(@log).not_to match(/Unknown attribute 'child' for component type '(Auto|Shelf|Leaf)'/)
  end
end
