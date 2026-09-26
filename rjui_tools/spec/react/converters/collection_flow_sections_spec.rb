# frozen_string_literal: true

require 'json'
require 'open3'
require 'tmpdir'
require_relative '../../spec_helper'
require 'react/converters/collection_converter'
require_relative '../../support/typescript_compiler'

# A flow Collection's sections, and a grid's and a flow's gaps, on the web
# (4f ruling 2026-09-26, round 5; attribute_semantics.json ->
# collectionSpacing):
# - Flow sections: with two or more sections that draw cells, each section is
#   a wrap of its own, one under the other, the blocks spaced as the lines —
#   sjui's FlowLayout per section in a VStack, kjui's FlowRow per section in a
#   Column. Until jsonui-cli 1.9.0 every section went into the one wrap, so
#   section 2 continued section 1's last line.
# - Gaps (grid and flow): between rows lineSpacing, else itemSpacing; between
#   columns columnSpacing, else itemSpacing. Until jsonui-cli 1.9.0 a
#   columnSpacing with no lineSpacing wrote `gap-[x]`, spacing the rows by it
#   too — and with an itemSpacing beside it, the rows took the columnSpacing
#   instead of the itemSpacing.
#
# The layout arm RENDERS the emitted JSX in headless Chromium, as
# collection_horizontal_lanes_spec.rb does, and reads where each cell landed.
RSpec.describe 'rjui Collection: flow sections, and the rows and columns of a grid or a flow' do
  def convert(extra)
    %i[info debug warn].each { |m| allow(RjuiTools::Core::Logger).to receive(m) }
    RjuiTools::React::Converters::CollectionConverter.new(
      { 'type' => 'Collection', 'id' => 'chips', 'items' => '@{rows}' }.merge(extra),
      { 'use_tailwind' => true }
    ).convert
  end

  FLOW_TWO_SECTIONS = { 'layout' => 'flow', 'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell' }] }.freeze

  def root_classes(jsx)
    jsx[/\A\s*<div id="chips"[^>]* className="([^"]*)"/, 1].split
  end

  def wraps(jsx)
    jsx.scan(/<div className="(flex flex-row flex-wrap content-start[^"]*)">/).flatten
  end

  describe 'flow sections' do
    it 'two sections: a column of two wraps, the blocks spaced as the lines' do
      jsx = convert(FLOW_TWO_SECTIONS.merge('lineSpacing' => 4, 'columnSpacing' => 10))
      expect(root_classes(jsx)).to include('flex', 'flex-col', 'gap-y-[4px]')
      expect(root_classes(jsx)).not_to include('flex-wrap')
      expect(wraps(jsx)).to eq(['flex flex-row flex-wrap content-start gap-x-[10px] gap-y-[4px]'] * 2), jsx
      expect(jsx.index('BCell')).to be > jsx.index('</div>') # section 1 in the second wrap
    end

    it 'one section, the legacy shape, or no items: the one wrap as before (the controls)' do
      [FLOW_TWO_SECTIONS.merge('sections' => [{ 'cell' => 'ACell' }]),
       { 'layout' => 'flow', 'cellClasses' => ['ACell'] },
       FLOW_TWO_SECTIONS.merge('sections' => [{ 'cell' => 'ACell' }, { 'header' => 'HCell' }])].each do |extra|
        jsx = convert(extra.merge('lineSpacing' => 4))
        expect(root_classes(jsx)).to include('flex-row', 'flex-wrap', 'gap-y-[4px]')
        expect(wraps(jsx)).to eq([]), jsx
      end
    end
  end

  # Every declaration that decides a gap, on the grid and on the one-wrap flow.
  GAP_CASES = {
    {} => [],
    { 'itemSpacing' => 6 } => ['gap-[6px]'],
    { 'lineSpacing' => 4 } => ['gap-y-[4px]'],
    { 'columnSpacing' => 10 } => ['gap-x-[10px]'],
    { 'columnSpacing' => 10, 'itemSpacing' => 6 } => ['gap-x-[10px]', 'gap-y-[6px]'],
    { 'lineSpacing' => 4, 'itemSpacing' => 6 } => ['gap-x-[6px]', 'gap-y-[4px]'],
    { 'lineSpacing' => 4, 'columnSpacing' => 10 } => ['gap-x-[10px]', 'gap-y-[4px]']
  }.freeze

  { 'grid' => { 'columns' => 2, 'sections' => [{ 'cell' => 'ACell' }] },
    'flow' => { 'layout' => 'flow', 'sections' => [{ 'cell' => 'ACell' }] } }.each do |route, shape|
    it "#{route}: rows lineSpacing, else itemSpacing; columns columnSpacing, else itemSpacing" do
      GAP_CASES.each do |declared, gaps|
        expect(root_classes(convert(shape.merge(declared))).grep(/\Agap/)).to eq(gaps), "#{route} #{declared}"
      end
    end
  end

  # Tailwind's own definitions of the classes the emit uses (tailwindcss.com
  # docs); an emitted class not listed here fails the arm rather than rendering
  # unstyled.
  TAILWIND_FLOW = {
    'flex' => 'display:flex', 'flex-row' => 'flex-direction:row', 'flex-col' => 'flex-direction:column',
    'flex-wrap' => 'flex-wrap:wrap', 'content-start' => 'align-content:flex-start', 'overflow-y-auto' => 'overflow-y:auto',
    'grid' => 'display:grid', 'grid-cols-2' => 'grid-template-columns:repeat(2, minmax(0, 1fr))'
  }.freeze

  def chromium
    Dir.glob(File.join(Dir.home, 'Library/Caches/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell')).max
  end

  # { "A0" => [x, y], … } as Chromium laid the emitted JSX out: the Collection
  # 200 wide, each cell 40 × 20; section A six cells, section B two.
  def render(jsx)
    esbuild = File.expand_path('../../support/node_modules/.bin/esbuild', __dir__)
    skip 'esbuild is not installed under spec/support' unless File.executable?(esbuild)
    skip 'no headless Chromium in the Playwright cache' unless chromium

    classes = jsx.scan(/className="([^"]*)"/).flatten.flat_map(&:split).uniq
    css = classes.map do |c|
      rule = TAILWIND_FLOW[c] ||
             (c =~ /\Agap-\[(\d+)px\]\z/ && "gap:#{Regexp.last_match(1)}px") ||
             (c =~ /\Agap-x-\[(\d+)px\]\z/ && "column-gap:#{Regexp.last_match(1)}px") ||
             (c =~ /\Agap-y-\[(\d+)px\]\z/ && "row-gap:#{Regexp.last_match(1)}px") or raise "no definition for #{c}"
      ".#{c.gsub(/[\[\]]/) { |ch| "\\#{ch}" }} { #{rule} }"
    end.join("\n")
    Dir.mktmpdir('rjui_flow') do |dir|
      File.write(File.join(dir, 'app.jsx'), <<~JSX)
        function h(tag, props, ...children) {
          if (typeof tag === 'function') return tag({ ...(props || {}), children });
          const el = document.createElement(tag);
          for (const [k, v] of Object.entries(props || {})) {
            if (k === 'className') el.className = v;
            else if (k === 'style') Object.assign(el.style, v);
            else if (k !== 'key' && k !== 'data') el.setAttribute(k, v);
          }
          for (const c of children.flat(Infinity)) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
          return el;
        }
        const cell = (letter) => ({ id }) => h('div', { id: letter + id.split('_').pop(), style: { width: '40px', height: '20px' } });
        const ACell = cell('A'), BCell = cell('B');
        const rows = (n) => ({ data: Array.from({ length: n }, (_, i) => ({ i })) });
        const data = { rows: { sections: [{ cells: rows(6) }, { cells: rows(2) }] } };
        const root = (#{jsx.strip});
        root.style.width = '200px';
        document.body.append(root);
        const origin = root.getBoundingClientRect();
        const at = {};
        for (const el of root.querySelectorAll('[id]')) {
          if (el === root) continue;
          const b = el.getBoundingClientRect();
          at[el.id] = [Math.round(b.left - origin.left), Math.round(b.top - origin.top)];
        }
        document.body.textContent = 'AT' + JSON.stringify(at);
      JSX
      out, status = Open3.capture2e(esbuild, File.join(dir, 'app.jsx'), '--jsx-factory=h', '--outfile=' + File.join(dir, 'app.js'))
      raise "esbuild: #{out}" unless status.success?

      File.write(File.join(dir, 'page.html'),
                 "<html><head><style>body{margin:0} #{css}</style></head><body><script src=\"app.js\"></script></body></html>")
      dom, = Open3.capture2e(chromium, '--headless', '--disable-gpu', '--allow-file-access-from-files', '--dump-dom',
                             "file://#{File.join(dir, 'page.html')}")
      JSON.parse(dom[/AT(\{.*?\})</m, 1] || raise("no layout in:\n#{dom}"))
    end
  end

  it 'renders: section B starts a line under section A, the blocks and the lines spaced by lineSpacing' do
    at = render(convert(FLOW_TWO_SECTIONS.merge('lineSpacing' => 4, 'columnSpacing' => 10)))
    # Section A: 40 + 10 per cell, 4 on a 200 line (190), A4 on the next line 20 + 4 down.
    expect(at.values_at('A0', 'A1', 'A3', 'A4')).to eq([[0, 0], [50, 0], [150, 0], [0, 24]]), at.inspect
    # Section B: its own line, under A's two lines and the 4 between the blocks.
    expect(at.values_at('B0', 'B1')).to eq([[0, 48], [50, 48]]), at.inspect
  end

  it 'renders: a lone columnSpacing spaces the columns and not the rows, on the flow and on the grid' do
    flow = render(convert(FLOW_TWO_SECTIONS.merge('columnSpacing' => 10)))
    expect(flow.values_at('A0', 'A1', 'A4', 'B0')).to eq([[0, 0], [50, 0], [0, 20], [0, 40]]), flow.inspect
    grid = render(convert('columns' => 2, 'columnSpacing' => 10, 'sections' => [{ 'cell' => 'ACell' }]))
    # Two columns of (200 - 10) / 2 = 95: A1 at 105, A2 on the next row, 20 down.
    expect(grid.values_at('A0', 'A1', 'A2')).to eq([[0, 0], [105, 0], [0, 20]]), grid.inspect
  end

  it 'the two wraps type-check in the whole element' do
    jsx = convert(FLOW_TWO_SECTIONS.merge('lineSpacing' => 4, 'columnSpacing' => 10))
    ambient = <<~TS
      #{TypeScriptCompiler::AMBIENT}
      declare const data: { rows?: { sections?: { cells?: { data: Record<string, unknown>[] } }[] } };
      declare const ACell: (props: { key?: string | number; id?: string; data: unknown }) => JSX.Element;
      declare const BCell: (props: { key?: string | number; id?: string; data: unknown }) => JSX.Element;
    TS
    expect(TypeScriptCompiler.component(jsx)).to compile_as_typescript.with_ambient(ambient)
  end
end
