# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'

# A component scaffolded as a leaf (`sjui g converter <Name> --no-container`)
# that a layout gives children: the build refuses the layout by name.
#
# Before 1.8.121 (measured on e1a85ca2) the build exited 0, the children were
# not in the generated view, and the only line about it was "Unknown
# attribute 'child' for component type 'Leaf'" — the same line a component
# in the DEFAULT mode got while its children WERE drawn. Ticket
# sjui-leaf-custom-component-cannot-reject-children.
#
# End to end on purpose: the scaffold, the definition file it writes and the
# build that reads it are three steps, and each cheaper arm passes with any
# one of them broken. The tool is COPIED (links dereferenced), not linked:
# `g converter` writes its converter into the tool's own views/extensions and
# the build loads it from there, so a linked checkout would be written into.
RSpec.describe 'a leaf given children, through sjui build' do
  def tool_root
    File.expand_path('../../..', __dir__)
  end

  before(:all) do
    @dir = Dir.mktmpdir('sjui_leaf')
    name = 'LeafProbe'
    tool = File.join(@dir, 'sjui_tools')
    FileUtils.mkdir_p(tool)
    # `-L`: lib/core's files are relative links into shared/core, which a
    # plain copy leaves dangling — the validator then loads no definitions
    # and every rule is silent.
    %w[bin lib].each do |d|
      raise "could not copy #{d}" unless system('cp', '-RL', File.join(tool_root, d), tool)
    end
    File.write(File.join(@dir, 'sjui.config.json'), JSON.pretty_generate(
      'mode' => 'swiftui', 'project_name' => name, 'project_file_name' => name,
      'source_directory' => name, 'layouts_directory' => 'Layouts',
      'resources_directory' => 'Resources', 'styles_directory' => 'Styles',
      'view_directory' => 'View', 'data_directory' => 'Data',
      'viewmodel_directory' => 'ViewModel',
      'resource_manager_directory' => 'ResourceManager',
      'string_files' => ["#{name}/Localizable.strings"], 'use_network' => true
    ))
    FileUtils.mkdir_p(File.join(@dir, "#{name}.xcodeproj"))
    @layouts = File.join(@dir, name, 'Layouts')
    FileUtils.mkdir_p(@layouts)

    # Leaf is scaffolded twice: with --no-container, then with neither flag
    # and JUI_SKIP_EXISTING=1 — what `jui g converter --all --skip-existing`
    # runs for a component spec without slots. Until 1.8.121 the second run
    # wrote the default back over the leaf's declaration, and the build
    # stopped refusing its children while its scaffold went on dropping them
    # (measured 2026-09-26). Grown is the control: made a leaf, then run with
    # --container, it takes children — the declaration changes when a flag
    # asks, and only then.
    @scaffold = [
      ['Shelf', ['--container', '--force']], ['Auto', ['--force']], ['Leaf', ['--no-container', '--force']],
      ['Leaf', [], { 'JUI_SKIP_EXISTING' => '1' }],
      ['Grown', ['--no-container', '--force']], ['Grown', ['--container', '--force']]
    ].map do |component, args, env = {}|
      Open3.capture2e(env, 'ruby', File.join(tool, 'bin', 'sjui'), 'g', 'converter', component,
                      '--attributes', 'title:String', *args, chdir: @dir)
    end

    node = ->(type, id, kids = nil) {
      n = { 'type' => type, 'id' => id, 'title' => id, 'width' => 'matchParent', 'height' => 'wrapContent' }
      n['child'] = kids if kids
      n
    }
    kid = ->(id) { { 'type' => 'Label', 'id' => id, 'text' => id, 'width' => 'wrapContent', 'height' => 'wrapContent' } }
    root = ->(kids) { { 'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent', 'orientation' => 'vertical', 'child' => kids } }
    File.write(File.join(@layouts, 'refused.json'), JSON.generate(root.call([
      node.call('Leaf', 'leaf', [kid.call('leaf_kid')]),
      { 'type' => 'Leaf', 'title' => 'nameless', 'width' => 'matchParent', 'height' => 'wrapContent',
        'child' => [kid.call('nameless_kid'), { 'type' => 'Label', 'text' => 'no id' }] }
    ])))
    File.write(File.join(@layouts, 'healthy.json'), JSON.generate(root.call([
      node.call('Leaf', 'leaf_alone'),
      node.call('Shelf', 'shelf', [kid.call('shelf_kid')]),
      node.call('Auto', 'auto', [kid.call('auto_kid')]),
      node.call('Grown', 'grown', [kid.call('grown_kid')])
    ])))

    @ledger = File.join(@dir, 'stage-failures.json')
    @log, @status = Open3.capture2e({ 'JUI_STAGE_FAILURES' => @ledger },
                                    'ruby', File.join(tool, 'bin', 'sjui'), 'build', chdir: @dir)
    @log = @log.gsub(/\e\[[0-9;]*m/, '')
  end

  after(:all) { FileUtils.rm_rf(@dir) }

  def ledger
    File.exist?(@ledger) ? JSON.parse(File.read(@ledger)) : []
  end

  def generated(layout)
    Dir.glob(File.join(@dir, '**', "#{layout}GeneratedView.swift")).map { |f| File.read(f) }.join
  end

  it 'scaffolds the three modes, and a leaf run again without a flag stays a leaf' do
    expect(@scaffold.map { |_, s| s.success? }).to all(be(true)), @scaffold.map(&:first).join("\n")
    defs = File.join(@dir, 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'attribute_definitions')
    expect(JSON.parse(File.read(File.join(defs, 'Leaf.json')))['Leaf']).to include('_children' => 'none')
    expect(@scaffold[3].first).to include('Leaf is declared a leaf in attribute_definitions/Leaf.json — kept')
    expect(JSON.parse(File.read(File.join(defs, 'Auto.json')))['Auto'].keys).to include('child', 'children')
    grown = JSON.parse(File.read(File.join(defs, 'Grown.json')))['Grown']
    expect(grown.keys).to include('child', 'children')
    expect(grown).not_to include('_children')
  end

  it 'records the leaf with children as the one incomplete stage, naming the node and the children' do
    entries = ledger.select { |e| e['stage'] == 'layout' }
    expect(entries.size).to eq(1), "#{ledger.inspect}\n#{@log}"
    message = entries.first['message']
    expect(message).to include('refused.json').and include('was not generated')
    expect(message).to include("'Leaf' (id=leaf) takes no children").and include('child[0] (id=leaf_kid)')
    # An id-less leaf is named by where it sits; so is an id-less child.
    expect(message).to include("'Leaf' (child[1]) takes no children")
      .and include('child[0] (id=nameless_kid), child[1] would be dropped')
  end

  it 'writes no view for the refused layout' do
    expect(generated('Refused')).to be_empty
  end

  it 'says nothing about a leaf without children, and draws the containers\' children' do
    expect(@log).not_to include("'Leaf' (id=leaf_alone)")
    view = generated('Healthy')
    expect(view).to include('"leaf_alone"')
    expect(view).to include('"shelf_kid"').and include('"auto_kid"').and include('"grown_kid"')
  end

  it "no longer says \"Unknown attribute 'child'\" — not for the default mode, whose children are drawn, nor for the leaf, which is refused instead" do
    expect(@log).not_to match(/Unknown attribute 'child' for component type '(Auto|Shelf|Leaf|Grown)'/)
  end
end
