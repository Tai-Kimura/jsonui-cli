# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'
require 'rbconfig'
require_relative '../spec_helper'
require 'core/config_manager'
require 'core/layout_path'

# The viewId of an id-less node inside an include is its position in the
# include-EXPANDED tree (JsonUIShared::LayoutPath), which is what sjui and kjui
# stamp. rjui does not expand an include — it calls the included layout's own
# component — so the part of the path above the include comes in at run time:
# a layout that takes it (React::IncludePaths) receives `jsonuiPath`, and the
# include site hands it the include node's path. 4f's ruling (1.9.0): the web
# value must equal what sjui and kjui stamp.
#
# Each project below is built by a copied rjui (the tool is COPIED, links
# dereferenced, as the other build specs do); its generated components are
# rendered by node (esbuild's JSX transform, a tree-keeping factory) and every
# <select> is operated, so the viewId read is the one the running page hands
# its handler — evaluated from the emitted template, not recomputed here.
# The sjui and kjui values are their own code's: each tool's IncludeExpander
# and LayoutPath, run in a process of its own on the same layouts.
RSpec.describe 'the viewId of a node inside an include, through rjui build' do
  IVI_RJUI_ROOT = File.expand_path('../..', __dir__)
  IVI_REPO = File.expand_path('../../..', __dir__)
  IVI_ESBUILD = File.expand_path('../support/node_modules/esbuild', __dir__)

  def self.select_box(extra = {})
    { 'type' => 'SelectBox', 'width' => 'matchParent', 'height' => 44, 'items' => '@{opts}',
      'selectedIndex' => '@{idx}', 'onValueChange' => '@{pick}' }.merge(extra)
  end

  def self.data
    [{ 'name' => 'opts', 'class' => '[String]' }, { 'name' => 'idx', 'class' => 'Int' },
     { 'name' => 'pick', 'class' => '((String, Int) -> Void)?' }]
  end

  def self.view(id, children, data: nil)
    node = { 'type' => 'View', 'id' => id, 'width' => 'matchParent', 'height' => 'wrapContent',
             'orientation' => 'vertical', 'child' => children }
    node['data'] = data if data
    node
  end

  def self.label(id)
    { 'type' => 'Label', 'id' => id, 'text' => id, 'width' => 'wrapContent', 'height' => 'wrapContent' }
  end

  # A screen with a SelectBox of its own, an include that includes (nested),
  # the same include direct, a SelectBox with an id, and an include that hands
  # no viewId.
  IVI_NESTED = {
    'home' => view('root', [label('t'), { 'include' => 'outer_part' }, select_box,
                            { 'include' => 'inner_part' }, { 'include' => 'plain_part' }], data: data),
    'outer_part' => view('outer_root', [label('o'), { 'include' => 'inner_part' }]),
    'inner_part' => view('inner_root', [label('i'), select_box, select_box('id' => 'named_box')], data: data),
    'plain_part' => view('plain_root', [label('p')])
  }.freeze

  # The shared vectors' include row (shared/core/layout_path_vectors.json),
  # with the two nodes it names inside and after the include made id-less
  # SelectBoxes: their viewIds are `selectBox_` and the paths the row expects.
  def self.vector_row
    vectors = JSON.parse(File.read(File.join(IVI_REPO, 'shared/core/layout_path_vectors.json'), encoding: 'UTF-8'))
    row = vectors['cases'].find { |c| c['includes'] }
    to_box = lambda do |node|
      case node
      when Hash
        node = node.transform_values { |v| to_box.call(v) }
        if %w[p0 after].include?(node['id'])
          label = node['id']
          node = select_box('_label' => label)
        end
        node
      when Array then node.map { |v| to_box.call(v) }
      else node
      end
    end
    layouts = { 'screen' => to_box.call(row['layout']).merge('data' => data) }
    row['includes'].each { |name, body| layouts[name] = to_box.call(body).merge('data' => data) }
    [layouts, %w[p0 after].map { |label| "selectBox_#{row['expect'][label]}" }]
  end

  def self.build(layouts)
    dir = Dir.mktmpdir('rjui_include_view_id')
    tool = File.join(dir, 'rjui_tools')
    FileUtils.mkdir_p(tool)
    %w[bin lib].each { |d| raise "could not copy #{d}" unless system('cp', '-RL', File.join(IVI_RJUI_ROOT, d), tool) }
    config = RjuiTools::Core::ConfigManager::DEFAULT_CONFIG.merge('typescript' => true)
    File.write(File.join(dir, 'rjui.config.json'), JSON.pretty_generate(config))
    FileUtils.mkdir_p(File.join(dir, 'src', 'Layouts'))
    layouts.each { |name, body| File.write(File.join(dir, 'src', 'Layouts', "#{name}.json"), JSON.generate(body)) }
    # The ruby running this suite, not PATH's: rbenv resolves `ruby` by
    # RBENV_VERSION and the cwd's .ruby-version, and a 2.6 leg ran its child
    # tool on 3.2 (or the other way round).
    log, status = Open3.capture2e(RbConfig.ruby, File.join(tool, 'bin', 'rjui'), 'build', chdir: dir)
    [dir, log, status]
  end

  # Renders the screen and operates every <select>: the first argument each
  # hands `pick`, in document order.
  IVI_NODE_PROGRAM = <<~JS
    const fs = require('fs');
    const esbuild = require(process.argv[2]);
    const files = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
    const screen = process.argv[4];
    const strip = (src) => src.split('\\n').filter((l) => !l.startsWith('import ')).join('\\n')
      .replace(/^export default [^;]+;$/gm, '').replace(/^export /gm, '').replace(/^"use client";$/m, '');
    const code = files.map((f) => esbuild.transformSync(strip(fs.readFileSync(f, 'utf8')),
      { loader: 'tsx', jsx: 'transform', jsxFactory: 'h', jsxFragment: 'Frag' }).code).join('\\n');
    const recorded = [];
    const h = (type, props, ...children) => (typeof type === 'function'
      ? type({ ...(props || {}), children: children.length === 1 ? children[0] : children })
      : { type, props: props || {}, children: children.flat(Infinity) });
    const stubs = {
      Frag: 'frag', React: {}, useState: (v) => [v, () => {}], useRef: (v) => ({ current: v }),
      useEffect: () => {}, useMemo: (f) => f(), useCallback: (f) => f,
      useStringManager: () => new Proxy({}, { get: (_, k) => String(k) }), screenMarker: () => ({}),
      __record: (viewId) => recorded.push(viewId),
    };
    const names = Object.keys(stubs);
    const body = `${code}\\nreturn h(${screen}, {});`;
    const tree = new Function('h', ...names, body)(h, ...names.map((n) => stubs[n]));
    const selects = [];
    const walk = (n) => { if (n && typeof n === 'object' && n.props) { if (n.type === 'select') selects.push(n); (n.children || []).forEach(walk); } };
    walk(tree);
    selects.forEach((s) => s.props.onChange({ target: { selectedIndex: 1, value: 'x', selectedOptions: [] } }));
    process.stdout.write(JSON.stringify(recorded));
  JS

  def self.rjui_view_ids(dir, screen)
    generated = File.join(dir, 'src', 'generated')
    files = Dir.glob(File.join(generated, 'data', '*.ts')) + Dir.glob(File.join(generated, 'components', '*.tsx'))
    Dir.mktmpdir('rjui_include_eval') do |tmp|
      # The handler's call is the one thing replaced: the viewId expression
      # handed to it is evaluated as emitted.
      sources = files.map do |f|
        copy = File.join(tmp, File.basename(f))
        File.write(copy, File.read(f).gsub('data.pick?.(', '__record('))
        copy
      end
      File.write(File.join(tmp, 'main.js'), IVI_NODE_PROGRAM)
      File.write(File.join(tmp, 'files.json'), JSON.generate(sources))
      out, err, status = Open3.capture3('node', File.join(tmp, 'main.js'), IVI_ESBUILD, File.join(tmp, 'files.json'), screen)
      raise "node failed: #{err}" unless status.success?

      JSON.parse(out)
    end
  end

  # sjui's and kjui's own expansion and stamp, each in a process of its own:
  # the viewId LayoutPath gives every SelectBox, in document order.
  def self.native_view_ids(tool, dir, screen)
    layouts = File.join(dir, 'src', 'Layouts')
    expand = {
      'sjui' => ['swiftui/include_expander', 'SjuiTools::SwiftUI::IncludeExpander.process_includes(tree, dir, nil)'],
      'kjui' => ['compose/include_expander', 'KjuiTools::Compose::IncludeExpander.process_includes(tree, dir, nil, dir)']
    }.fetch(tool)
    script = <<~RUBY
      require 'json'
      require '#{expand[0]}'
      require 'core/layout_path'
      dir = ARGV[0]
      tree = JSON.parse(File.read(File.join(dir, ARGV[1] + '.json')))
      tree = #{expand[1]}
      JsonUIShared::LayoutPath.stamp!(tree)
      ids = []
      walk = lambda do |node|
        next unless node.is_a?(Hash)
        ids << JsonUIShared::LayoutPath.view_id(node) if node['type'] == 'SelectBox'
        JsonUIShared::LayoutPath.children(node).each { |child| walk.call(child) }
      end
      walk.call(tree)
      puts JSON.generate(ids)
    RUBY
    out, err, status = Open3.capture3(RbConfig.ruby, '-I', File.join(IVI_REPO, "#{tool}_tools", 'lib'), '-e', script, layouts, screen)
    raise "#{tool} failed: #{err}" unless status.success?

    JSON.parse(out.lines.last)
  end

  before(:context) do
    skip 'node is not on PATH: UNMEASURED here' unless system('which node > /dev/null 2>&1') || ENV['CI']
    skip 'esbuild is not installed (npm ci --prefix rjui_tools/spec/support): UNMEASURED here' unless File.directory?(IVI_ESBUILD) || ENV['CI']

    @nested_dir, @nested_log, @nested_status = self.class.build(IVI_NESTED)
    layouts, @vector_expected = self.class.vector_row
    @vector_dir, @vector_log, @vector_status = self.class.build(layouts)
  end

  after(:context) do
    FileUtils.rm_rf(@nested_dir) if @nested_dir
    FileUtils.rm_rf(@vector_dir) if @vector_dir
  end

  it 'builds' do
    expect(@nested_status).to be_success, @nested_log[-3000..]
    expect(@vector_status).to be_success, @vector_log[-3000..]
  end

  it 'hands the viewIds of the expanded tree, nested include and all' do
    got = self.class.rjui_view_ids(@nested_dir, 'Home')
    expect(got).to eq(%w[selectBox_0_1_1_1 named_box selectBox_0_2 selectBox_0_3_1 named_box])
  end

  it 'hands the values sjui and kjui stamp on the same layouts' do
    got = self.class.rjui_view_ids(@nested_dir, 'Home')
    expect(self.class.native_view_ids('sjui', @nested_dir, 'home')).to eq(got)
    expect(self.class.native_view_ids('kjui', @nested_dir, 'home')).to eq(got)
  end

  it 'hands the paths the shared vectors expect for the include row' do
    expect(self.class.rjui_view_ids(@vector_dir, 'Screen')).to eq(@vector_expected)
  end

  # Only a layout that needs the path takes it: an include that hands no
  # viewId, and a screen no one includes, come out as they did. (From
  # jsonui-cli 1.9.6 each call site also hands the partial the including
  # layout's data — `data={{ ... }}` after the path; the path is what this
  # reads.)
  it 'plumbs the path through the layouts that need it, and no other' do
    components = File.join(@nested_dir, 'src', 'generated', 'components')
    read = ->(name) { File.read(File.join(components, "#{name}.tsx")) }
    expect(read.('Home')).to include('<OuterPart jsonuiPath="0_1" ').and include('<InnerPart jsonuiPath="0_3" ')
    expect(read.('Home')).to match(/<PlainPart(?: data=\{\{[^}]*\}\})? \/>/)
    expect(read.('Home')).not_to include('jsonuiPath?: string')
    expect(read.('OuterPart')).to include('jsonuiPath?: string').and include('<InnerPart jsonuiPath={`${jsonuiPath}_1`} ')
    expect(read.('InnerPart')).to include('`selectBox_${jsonuiPath}_1`').and include('"named_box"')
    expect(read.('PlainPart')).not_to include('jsonuiPath')
  end
end
