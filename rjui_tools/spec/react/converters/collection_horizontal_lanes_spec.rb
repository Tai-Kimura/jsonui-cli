# frozen_string_literal: true

require 'json'
require 'open3'
require 'tmpdir'
require_relative '../../spec_helper'
require 'react/converters/collection_converter'
require_relative '../../support/typescript_compiler'

# A horizontal Collection's lanes and spacing on the web (4f ruling,
# 2026-09-26; the rule sjui codegen and SwiftJsonUI Dynamic dde0628 draw):
# - Lanes: a section has more than one lane when its own `columns`, else the
#   Collection's, is above 1; a bound `columns` keeps the grid even at 1 lane,
#   and a section's own count overrides it. Paging is unchanged.
# - Cell order: a column is filled top to bottom, then the next column.
# - Section blocks: each section starts a new column.
# - Spacing on every horizontal Collection: along the scroll axis lineSpacing,
#   else itemSpacing, else 0; between lanes columnSpacing, else itemSpacing.
# Until jsonui-cli 1.9.0 (measured on 142fd2f6) the flex row drew one lane
# whatever `columns` said, and spaced it columnSpacing first.
#
# The layout arm RENDERS the emitted JSX in headless Chromium (esbuild turns it
# into DOM calls; the few Tailwind classes it uses are declared from Tailwind's
# own definitions and every class in the emit must be one of them) and reads
# where each cell landed.
RSpec.describe 'rjui Collection: horizontal lanes' do
  def convert(extra)
    %i[info debug warn].each { |m| allow(RjuiTools::Core::Logger).to receive(m) }
    RjuiTools::React::Converters::CollectionConverter.new(
      { 'type' => 'Collection', 'id' => 'list', 'layout' => 'horizontal', 'items' => '@{rows}' }.merge(extra),
      { 'use_tailwind' => true }
    ).convert
  end

  # [gridTemplateRows, columnGap, rowGap] of each lane grid, in order.
  def lane_grids(jsx)
    jsx.scan(/<div className="grid grid-flow-col[^"]*" style=\{\{ (.*?) \}\}>/).flatten.map do |style|
      [style[/gridTemplateRows: ('[^']*'|`[^`]*`)/, 1], style[/columnGap: '(\w+)'/, 1], style[/rowGap: '(\w+)'/, 1]]
    end
  end

  LANE_SECTIONS = [{ 'cell' => 'ACell' }, { 'cell' => 'BCell', 'columns' => 1 }, { 'cell' => 'CCell', 'columns' => 3 }].freeze

  it "a section's lanes are its own columns, else the Collection's; one lane keeps the flex row" do
    jsx = convert('columns' => 2, 'lineSpacing' => 8, 'columnSpacing' => 4, 'sections' => LANE_SECTIONS)
    expect(lane_grids(jsx)).to eq([["'repeat(2, minmax(0, 1fr))'", '8px', '4px'], ["'repeat(3, minmax(0, 1fr))'", '8px', '4px']]), jsx
    expect(jsx.index('BCell')).to be > jsx.index('</div>') # section 1 sits in the row, after section 0's grid
    expect(lane_grids(convert('columns' => 2, 'lazy' => 'none', 'sections' => LANE_SECTIONS.first(1))).size).to eq(1)
  end

  it 'a bound columns keeps the grid at any count; a section that declares its own overrides it' do
    jsx = convert('columns' => '@{cols}', 'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell', 'columns' => 1 }])
    expect(lane_grids(jsx)).to eq([['`repeat(${data.cols}, minmax(0, 1fr))`', nil, nil]]), jsx
  end

  it 'no lanes for one column, a flow, or paging (the controls)' do
    expect(lane_grids(convert('sections' => LANE_SECTIONS.first(1)))).to eq([])
    expect(lane_grids(convert('layout' => 'flow', 'columns' => 2, 'sections' => LANE_SECTIONS.first(1)))).to eq([])
    expect(lane_grids(convert('paging' => true, 'columns' => 2, 'sections' => LANE_SECTIONS.first(1)))).to eq([])
  end

  it 'the row is spaced along the scroll axis by lineSpacing, else itemSpacing — never columnSpacing' do
    gap = ->(extra) { convert({ 'sections' => LANE_SECTIONS.first(1) }.merge(extra))[/className="[^"]*\bgap-\[(\w+)\]/, 1] }
    expect(gap.call('lineSpacing' => 8, 'itemSpacing' => 5, 'columnSpacing' => 3)).to eq('8px')
    expect(gap.call('itemSpacing' => 5, 'columnSpacing' => 3)).to eq('5px')
    expect(gap.call('columnSpacing' => 3)).to be_nil
    expect(gap.call('paging' => true, 'lineSpacing' => 8, 'itemSpacing' => 5)).to eq('8px')
  end

  # Tailwind's own definitions of the classes the emit uses (tailwindcss.com
  # docs); an emitted class not listed here fails the arm rather than rendering
  # unstyled.
  TAILWIND = {
    'grid' => 'display:grid', 'grid-flow-col' => 'grid-auto-flow:column', 'auto-cols-max' => 'grid-auto-columns:max-content',
    'items-start' => 'align-items:start', 'justify-items-start' => 'justify-items:start', 'shrink-0' => 'flex-shrink:0',
    'flex' => 'display:flex', 'flex-row' => 'flex-direction:row', 'flex-nowrap' => 'flex-wrap:nowrap',
    'overflow-x-auto' => 'overflow-x:auto'
  }.freeze

  def chromium
    Dir.glob(File.join(Dir.home, 'Library/Caches/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell')).max
  end

  # { "A0" => [x, y], … } as Chromium laid the emitted JSX out: the Collection
  # 400 × 100, each cell 40 × 20.
  def render(jsx)
    esbuild = File.expand_path('../../support/node_modules/.bin/esbuild', __dir__)
    skip 'esbuild is not installed under spec/support' unless File.executable?(esbuild)
    skip 'no headless Chromium in the Playwright cache' unless chromium

    classes = jsx.scan(/className="([^"]*)"/).flatten.flat_map(&:split).uniq
    css = classes.map do |c|
      rule = TAILWIND[c] || (c =~ /\Agap-\[(\d+)px\]\z/ && "gap:#{Regexp.last_match(1)}px") or raise "no definition for #{c}"
      ".#{c.gsub(/[\[\]]/) { |ch| "\\#{ch}" }} { #{rule} }"
    end.join("\n")
    Dir.mktmpdir('rjui_lanes') do |dir|
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
        const ACell = cell('A'), BCell = cell('B'), CCell = cell('C');
        const rows = (n) => ({ data: Array.from({ length: n }, (_, i) => ({ i })) });
        const data = { cols: 2, rows: { sections: [{ cells: rows(3) }, { cells: rows(2) }, { cells: rows(4) }] } };
        const root = (#{jsx.strip});
        root.style.width = '400px'; root.style.height = '100px';
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

  it 'renders: a column is filled top to bottom, then the next; each section block starts a new column' do
    at = render(convert('columns' => 2, 'lineSpacing' => 8, 'columnSpacing' => 4, 'sections' => LANE_SECTIONS))
    # Section 0, 2 lanes of (100 - 4) / 2 = 48: A0 A1 down the first column, A2 at the top of the next.
    expect(at.values_at('A0', 'A1', 'A2')).to eq([[0, 0], [0, 52], [48, 0]]), at.inspect
    # Section 1, one lane: after section 0's block (2 columns: 40 + 8 + 40) and the 8 between blocks.
    expect(at.values_at('B0', 'B1')).to eq([[96, 0], [144, 0]]), at.inspect
    # Section 2, 3 lanes of (100 - 2 × 4) / 3 ≈ 30.7: C0 C1 C2 down a new column, C3 at the top of the next.
    c = at.values_at('C0', 'C1', 'C2', 'C3')
    expect(c.map(&:first).uniq.size).to eq(2), at.inspect
    expect([c[0][0], c[1][0], c[2][0]].uniq).to eq([192]), at.inspect
    expect([c[0][1], c[1][1] > c[0][1], c[2][1] > c[1][1], c[3]]).to eq([0, true, true, [240, 0]]), at.inspect
  end

  it 'the lane grids type-check in the whole element' do
    jsx = convert('columns' => '@{cols}', 'lineSpacing' => 8, 'columnSpacing' => 4, 'sections' => LANE_SECTIONS)
    ambient = <<~TS
      #{TypeScriptCompiler::AMBIENT}
      declare const data: { cols: number; rows?: { sections?: { cells?: { data: Record<string, unknown>[] } }[] } };
      declare const ACell: (props: { key?: string | number; id?: string; data: unknown }) => JSX.Element;
      declare const BCell: (props: { key?: string | number; id?: string; data: unknown }) => JSX.Element;
      declare const CCell: (props: { key?: string | number; id?: string; data: unknown }) => JSX.Element;
    TS
    expect(TypeScriptCompiler.component(jsx)).to compile_as_typescript.with_ambient(ambient)
  end
end
