# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'
require 'rbconfig'
require_relative '../spec_helper'
require 'core/config_manager'

# An include draws the including layout's data (ruling 2026-10-02;
# JsonUI-Agents-for-claude/.claude/jsonui-rules/design-philosophy.md — an
# include is a static inline expansion and the parent owns the VM), with the
# include node's maps over it: shared_data, then data. sjui / kjui expand the
# include into the screen, so the partial's `@{title}` reads the screen's
# `title` — or, under an id, the screen's `<id>Title`. rjui draws the include
# as a component call; until jsonui-cli 1.9.6 a bare include rendered
# `<Panel />` and the partial drew its own createPanelData() defaults (ticket
# rjui-include-does-not-read-the-screens-data).
#
# Each project is built by a copied rjui and its generated components are
# rendered by node (esbuild's JSX transform, a tree-keeping factory, as
# include_view_id_build_spec.rb does); the text each Label draws is read from
# the rendered tree. The screen declares its names with "from screen"
# defaults and the partial declares `title` with "from partial", so which
# side a Label drew is in its text.
RSpec.describe 'an include draws the including layout data, through rjui build' do
  IRD_RJUI_ROOT = File.expand_path('../..', __dir__)
  IRD_ESBUILD = File.expand_path('../support/node_modules/esbuild', __dir__)

  IRD_NODE_PROGRAM = <<~JS
    const fs = require('fs');
    const esbuild = require(process.argv[2]);
    const files = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
    const strip = (src) => src.split('\\n').filter((l) => !l.startsWith('import ')).join('\\n')
      .replace(/^export default [^;]+;$/gm, '').replace(/^export /gm, '').replace(/^"use client";$/m, '');
    const code = files.map((f) => esbuild.transformSync(strip(fs.readFileSync(f, 'utf8')),
      { loader: 'tsx', jsx: 'transform', jsxFactory: 'h', jsxFragment: 'Frag' }).code).join('\\n');
    const h = (type, props, ...children) => (typeof type === 'function'
      ? type({ ...(props || {}), children: children.length === 1 ? children[0] : children })
      : { type, props: props || {}, children: children.flat(Infinity) });
    const stubs = { Frag: 'frag', React: {}, useState: (v) => [v, () => {}], useRef: (v) => ({ current: v }),
      useEffect: () => {}, useMemo: (f) => f(), useCallback: (f) => f,
      useStringManager: () => new Proxy({}, { get: (_, k) => String(k) }), screenMarker: () => ({}) };
    const names = Object.keys(stubs);
    const tree = new Function('h', ...names, `${code}\\nreturn h(Screen, {});`)(h, ...names.map((n) => stubs[n]));
    const texts = {};
    const walk = (n, id) => {
      if (typeof n === 'string' || typeof n === 'number') { if (id) texts[id] = (texts[id] || '') + String(n); return; }
      if (n && typeof n === 'object' && n.props) { const own = n.props.id || id; (n.children || []).forEach((c) => walk(c, own)); }
    };
    walk(tree, null);
    process.stdout.write(JSON.stringify(texts));
  JS

  def self.label(id, text = '@{title}')
    { 'type' => 'Label', 'id' => id, 'text' => text, 'width' => 'wrapContent', 'height' => 'wrapContent' }
  end

  def self.string(name, default)
    { 'name' => name, 'class' => 'String', 'defaultValue' => default }
  end

  IRD_PANEL = { 'type' => 'View', 'id' => 'panel_root', 'width' => 'matchParent', 'height' => 'wrapContent',
            'data' => [string('title', 'from partial')], 'child' => [label('panel_title')] }.freeze

  # The generated Screen and Panel, their data files with them, as one
  # TypeScript source (imports dropped — they are each other's).
  def self.typescript(files)
    files.select { |f| f =~ %r{/(Screen|Panel)(Data)?\.tsx?\z} }.map do |f|
      File.read(f).lines.reject { |l| l.start_with?('import ') || l.start_with?('export default') || l.strip == '"use client";' }.join
    end.join("\n")
  end

  IRD_AMBIENT = "declare function useStringManager(): any;\ndeclare function screenMarker(name: string): any;\n"

  # [the texts the screen draws ({ label id => text }), Screen.tsx, the
  # TypeScript of Screen and Panel].
  def self.draw(screen_data, include_node, panel: IRD_PANEL)
    dir = Dir.mktmpdir('rjui_include_data')
    tool = File.join(dir, 'rjui_tools')
    FileUtils.mkdir_p(tool)
    %w[bin lib].each { |d| raise "could not copy #{d}" unless system('cp', '-RL', File.join(IRD_RJUI_ROOT, d), tool) }
    File.write(File.join(dir, 'rjui.config.json'),
               JSON.generate(RjuiTools::Core::ConfigManager::DEFAULT_CONFIG.merge('typescript' => true)))
    layouts = File.join(dir, 'src', 'Layouts')
    FileUtils.mkdir_p(File.join(layouts, 'parts'))
    File.write(File.join(layouts, 'parts', 'panel.json'), JSON.generate(panel))
    File.write(File.join(layouts, 'screen.json'), JSON.generate(
      'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
      'data' => screen_data, 'child' => [include_node]
    ))
    log, status = Open3.capture2e(RbConfig.ruby, File.join(tool, 'bin', 'rjui'), 'build', chdir: dir)
    raise "rjui build failed:\n#{log}" unless status.success?

    generated = File.join(dir, 'src', 'generated')
    files = Dir.glob(File.join(generated, 'data', '*.ts')) + Dir.glob(File.join(generated, 'components', '**', '*.tsx'))
    raise "no Screen.tsx:\n#{log}" unless files.any? { |f| f.end_with?('/Screen.tsx') }

    File.write(File.join(dir, 'main.js'), IRD_NODE_PROGRAM)
    File.write(File.join(dir, 'files.json'), JSON.generate(files))
    out, err, node = Open3.capture3('node', File.join(dir, 'main.js'), IRD_ESBUILD, File.join(dir, 'files.json'))
    raise "node failed: #{err}" unless node.success?

    [JSON.parse(out), File.read(File.join(generated, 'components', 'Screen.tsx')), typescript(files)]
  ensure
    FileUtils.rm_rf(dir) if dir
  end

  # A partial holding a TabView: the screen's VM drives its tab and hears its
  # taps. The screen's data hands `selectedTabIndex: 1` and a setter that
  # records what it is called with; the rendered tree shows which tab's
  # content is drawn, and tab 0's button is pressed.
  IRD_TABS_PROGRAM = <<~JS
    const fs = require('fs'); const esbuild = require(process.argv[2]);
    const files = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
    const strip = (src) => src.split('\\n').filter((l) => !l.startsWith('import ')).join('\\n')
      .replace(/^export default [^;]+;$/gm, '').replace(/^export /gm, '').replace(/^"use client";$/m, '');
    const code = files.map((f) => esbuild.transformSync(strip(fs.readFileSync(f, 'utf8')),
      { loader: 'tsx', jsx: 'transform', jsxFactory: 'h', jsxFragment: 'Frag' }).code).join('\\n');
    const h = (type, props, ...children) => (typeof type === 'function'
      ? type({ ...(props || {}), children: children.length === 1 ? children[0] : children })
      : { type, props: props || {}, children: children.flat(Infinity) });
    const calls = [];
    const stubs = { Frag: 'frag', React: {}, useState: (v) => [v, () => {}], useRef: (v) => ({ current: v }),
      useEffect: () => {}, useMemo: (f) => f(), useCallback: (f) => f, Circle: () => null,
      useStringManager: () => new Proxy({}, { get: (_, k) => String(k) }), screenMarker: () => ({}) };
    const names = Object.keys(stubs);
    const screenData = { selectedTabIndex: 1, setSelectedTabIndex: (i) => calls.push(i) };
    const tree = new Function('h', 'screenData', ...names, `${code}\\nreturn h(Screen, { data: screenData });`)(h, screenData, ...names.map((n) => stubs[n]));
    const ids = []; let tab0 = null;
    const walk = (n) => { if (n && typeof n === 'object' && n.props) {
      if (n.props.id) ids.push(n.props.id);
      if (n.props.id === 'tv_tab_0') tab0 = n;
      (n.children || []).forEach(walk); } };
    walk(tree);
    tab0.props.onClick();
    process.stdout.write(JSON.stringify({ ids, calls }));
  JS

  def self.draw_tabs
    dir = Dir.mktmpdir('rjui_include_tabs')
    tool = File.join(dir, 'rjui_tools')
    FileUtils.mkdir_p(tool)
    %w[bin lib].each { |d| raise "could not copy #{d}" unless system('cp', '-RL', File.join(IRD_RJUI_ROOT, d), tool) }
    File.write(File.join(dir, 'rjui.config.json'),
               JSON.generate(RjuiTools::Core::ConfigManager::DEFAULT_CONFIG.merge('typescript' => true)))
    layouts = File.join(dir, 'src', 'Layouts')
    FileUtils.mkdir_p(File.join(layouts, 'parts'))
    box = ->(id) { { 'type' => 'View', 'id' => id, 'width' => 'matchParent', 'height' => 'matchParent', 'child' => [] } }
    File.write(File.join(layouts, 'tab_a.json'), JSON.generate(box.call('content_a')))
    File.write(File.join(layouts, 'tab_b.json'), JSON.generate(box.call('content_b')))
    File.write(File.join(layouts, 'parts', 'tabs.json'), JSON.generate(
      'type' => 'View', 'id' => 'tabs_root', 'width' => 'matchParent', 'height' => 'wrapContent',
      'child' => [{ 'type' => 'TabView', 'id' => 'tv', 'width' => 'matchParent', 'height' => 200,
                    'tabs' => [{ 'title' => 'A', 'view' => 'tab_a' }, { 'title' => 'B', 'view' => 'tab_b' }] }]
    ))
    File.write(File.join(layouts, 'screen.json'), JSON.generate(
      'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
      'child' => [{ 'include' => 'parts/tabs' }]
    ))
    log, status = Open3.capture2e(RbConfig.ruby, File.join(tool, 'bin', 'rjui'), 'build', chdir: dir)
    raise "rjui build failed:\n#{log}" unless status.success?

    generated = File.join(dir, 'src', 'generated')
    files = Dir.glob(File.join(generated, 'data', '*.ts')) + Dir.glob(File.join(generated, 'components', '**', '*.tsx'))
    File.write(File.join(dir, 'main.js'), IRD_TABS_PROGRAM)
    File.write(File.join(dir, 'files.json'), JSON.generate(files))
    out, err, node = Open3.capture3('node', File.join(dir, 'main.js'), IRD_ESBUILD, File.join(dir, 'files.json'))
    raise "node failed: #{err}" unless node.success?

    [JSON.parse(out), File.read(File.join(generated, 'components', 'Screen.tsx'))[/<Tabs[^>]*\/>/]]
  ensure
    FileUtils.rm_rf(dir) if dir
  end

  before do
    skip 'node is not on PATH' unless system('node', '--version', out: File::NULL, err: File::NULL)
    skip "esbuild is not installed (npm ci --prefix #{File.dirname(IRD_ESBUILD, 2)})" unless File.directory?(IRD_ESBUILD)
  end

  it "draws the screen's value for a name both declare, without an id, and compiles" do
    texts, _, ts = self.class.draw([self.class.string('title', 'from screen')], { 'include' => 'parts/panel' })

    expect(texts['panel_title']).to eq('from screen')
    expect(ts).to compile_as_typescript.with_ambient(IRD_AMBIENT)
  end

  # A partial that binds a name it does not declare reads the including
  # layout's declaration — valid on sjui / kjui, where the include is
  # expanded into the screen. Until 1.9.6 its Data type had no such member
  # and tsc rejected `data.title` (TS2339; ticket
  # rjui-partial-binding-an-undeclared-name-does-not-compile).
  IRD_UNDECLARED = { 'type' => 'View', 'id' => 'panel_root', 'width' => 'matchParent', 'height' => 'wrapContent',
                 'child' => [label('panel_title')] }.freeze

  it 'draws and compiles a name the partial binds without declaring' do
    texts, site, ts = self.class.draw([self.class.string('title', 'from screen')], { 'include' => 'parts/panel' },
                                      panel: IRD_UNDECLARED)

    expect(texts['panel_title']).to eq('from screen')
    expect(site).to include('<Panel data={{ title: data.title }} />')
    expect(ts).to compile_as_typescript.with_ambient(IRD_AMBIENT)
  end

  it 'reads it prefixed under an id, and compiles' do
    texts, _, ts = self.class.draw([self.class.string('sideTitle', 'from screen')],
                                   { 'include' => 'parts/panel', 'id' => 'side' }, panel: IRD_UNDECLARED)

    expect(texts['panel_title']).to eq('from screen')
    expect(ts).to compile_as_typescript.with_ambient(IRD_AMBIENT)
  end

  # A handler the partial binds is a member too: the call site hands it the
  # screen's. Until 1.9.6 the partial's Data type lacked it (TS2339) and the
  # site handed nothing, so the tap reached no handler.
  it 'hands a handler the partial binds, and compiles' do
    button = { 'type' => 'Button', 'id' => 'b', 'text' => 'go', 'onClick' => '@{onTap}',
               'width' => 'wrapContent', 'height' => 'wrapContent' }
    _, site, ts = self.class.draw([{ 'name' => 'onTap', 'class' => '(() -> Void)?' }], { 'include' => 'parts/panel' },
                                  panel: IRD_UNDECLARED.merge('child' => [button]))

    expect(site).to include('<Panel data={{ onTap: data.onTap }} />')
    expect(ts).to compile_as_typescript.with_ambient(IRD_AMBIENT)
  end

  it "draws the screen's prefixed name under an id" do
    texts, = self.class.draw([self.class.string('panelTitle', 'from screen')], { 'include' => 'parts/panel', 'id' => 'panel' })

    expect(texts['panel_title']).to eq('from screen')
  end

  # The control of the two above: under an id the screen's unprefixed `title`
  # is another name. The partial's declaration is in the screen's Data type
  # as `panelTitle`, with the partial's default, and that is what it draws.
  it "draws its own declaration's default when the screen has no such name" do
    texts, site = self.class.draw([self.class.string('title', 'from screen')], { 'include' => 'parts/panel', 'id' => 'panel' })

    expect(texts['panel_title']).to eq('from partial')
    expect(site).to include('title: data.panelTitle')
  end

  it "draws a map's binding over the screen's data" do
    texts, = self.class.draw([self.class.string('title', 'from screen'), self.class.string('other', 'from map')], { 'include' => 'parts/panel', 'data' => { 'title' => '@{other}' } })

    expect(texts['panel_title']).to eq('from map')
  end

  it "draws a map's literal" do
    texts, = self.class.draw([self.class.string('title', 'from screen')], { 'include' => 'parts/panel', 'data' => { 'title' => 'literal' } })

    expect(texts['panel_title']).to eq('literal')
  end

  it 'reads shared_data first and data over it' do
    texts, = self.class.draw([self.class.string('a', 'from shared_data'), self.class.string('b', 'from data')], { 'include' => 'parts/panel', 'shared_data' => { 'title' => '@{a}' }, 'data' => { 'title' => '@{b}' } })

    expect(texts['panel_title']).to eq('from data')
  end

  # Until 1.9.6 the call site was `<Tabs />`: the partial drew its own seeded
  # tab 0 whatever the screen's VM held, and a tap moved only that seeded
  # state — setSelectedTabIndex was never called (ticket
  # rjui-include-does-not-hand-a-partials-tabview-state).
  it "hands a partial's TabView the screen's tab state and setter" do
    drawn, site = self.class.draw_tabs

    expect(site).to include('selectedTabIndex: data.selectedTabIndex', 'setSelectedTabIndex: data.setSelectedTabIndex')
    expect(drawn['ids']).to include('content_b')
    expect(drawn['ids']).not_to include('content_a')
    expect(drawn['calls']).to eq([0])
  end
end
