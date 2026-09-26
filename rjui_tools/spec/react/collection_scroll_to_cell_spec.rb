# frozen_string_literal: true

require 'json'
require 'open3'
require 'tmpdir'
require_relative '../spec_helper'
require 'react/react_generator'
require 'react/converters/collection_converter'
require 'cli/commands/build_command'
require_relative '../support/typescript_compiler'

# What a Collection's `scrollTo` names across sections (4f ruling 2026-09-27;
# the SSoT's Collection.scrollTo description, jsonui-cli 1.9.0):
# - a number is the index of a CELL counted across all the drawn sections in
#   order — a section's header or footer is not counted (the same n as the
#   paging address);
# - a string (with cellIdProperty) is the FIRST cell, in section order, whose
#   key (its cellId, else its cellIdProperty value) it is — two sections may
#   share a key.
# Until jsonui-cli 1.9.0 the web scrolled to the container's child at the
# index — a header, a footer and a section's block each one of them — and a
# string was read as a number, so a key scrolled nowhere.
#
# The arm RENDERS the emitted JSX in headless Chromium (as
# collection_flow_sections_spec.rb does), runs the scroll effect the generator
# emits for the same node against the helper `rjui build` writes, and reads
# which view sits at the top of the list.
RSpec.describe 'rjui Collection: scrollTo names a cell' do
  SCROLL_TO_CELL_NODE = {
    'type' => 'Collection', 'id' => 'target', 'items' => '@{rows}', 'height' => 100,
    'sections' => [{ 'cell' => 'ACell', 'header' => 'HCell', 'footer' => 'FCell' }, { 'cell' => 'BCell', 'header' => 'HCell' }],
    'scrollTo' => '@{target}', 'scrollAnchor' => 'top', 'scrollAnimated' => false
  }.freeze

  # Section A: header H0, cells A0…A4, footer F0; section B: header H1, cells
  # B0…B7. Keys: A's k0…k4; B's k3 (shared with A), x1…x7.
  SCROLL_TO_CELL_DATA = <<~JS
    { rows: { sections: [
      { header: { n: 0 }, cells: { data: [0, 1, 2, 3, 4].map((i) => ({ name: 'A' + i, key: 'k' + i })) }, footer: { n: 0 } },
      { header: { n: 1 }, cells: { data: ['k3', 'x1', 'x2', 'x3', 'x4', 'x5', 'x6', 'x7'].map((key, i) => ({ name: 'B' + i, key })) } }
    ] } }
  JS

  def quiet
    %i[info debug warn success].each { |m| allow(RjuiTools::Core::Logger).to receive(m) }
  end

  def converted(node)
    quiet
    RjuiTools::React::Converters::CollectionConverter.new(JSON.parse(JSON.generate(node)), { 'use_tailwind' => true }).convert
  end

  def generated(node, typescript: false)
    quiet
    RjuiTools::React::ReactGenerator.new({ 'use_tailwind' => true, 'typescript' => typescript,
                                           'layouts_directory' => '/tmp/x', 'generated_directory' => '/tmp/x/out' })
                                    .generate('ScrollScreen', { 'type' => 'View', 'child' => [JSON.parse(JSON.generate(node))] })
  end

  # The scroll call of the effect the generator emits for `node`.
  def scroll_call(node)
    generated(node)[/useEffect\(\(\) => \{ (scrollCollectionToCell\(.*\)); \}, \[data\.target\]\);/, 1] or
      raise "no scrollTo effect in\n#{generated(node)}"
  end

  def helper(typescript: false)
    Dir.mktmpdir('rjui_scroll_helper') do |dir|
      command = RjuiTools::CLI::Commands::BuildCommand.allocate
      command.instance_variable_set(:@config, { 'generated_directory' => dir, 'typescript' => typescript })
      quiet
      command.send(:emit_collection_scroll_helper)
      File.read(File.join(dir, "collectionScroll.#{typescript ? 'ts' : 'js'}"))
    end
  end

  def chromium
    Dir.glob(File.join(Dir.home, 'Library/Caches/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell')).max
  end

  SCROLL_TO_CELL_CSS = {
    'h-[100px]' => 'height:100px', 'shrink-0' => 'flex-shrink:0', 'flex' => 'display:flex',
    'flex-col' => 'flex-direction:column', 'overflow-y-auto' => 'overflow-y:auto'
  }.freeze

  # The name of the view at the list's top after each target in `targets`
  # (each scroll run from the top), e.g. { 6 => "B1" }.
  def top_after(node, targets)
    esbuild = File.expand_path('../support/node_modules/.bin/esbuild', __dir__)
    skip 'esbuild is not installed under spec/support' unless File.executable?(esbuild)
    skip 'no headless Chromium in the Playwright cache' unless chromium

    jsx = converted(node)
    css = jsx.scan(/className="([^"]*)"/).flatten.flat_map(&:split).uniq.map do |c|
      rule = SCROLL_TO_CELL_CSS[c] or raise "no definition for #{c}"
      ".#{c.gsub(/[\[\]]/) { |ch| "\\#{ch}" }} { #{rule} }"
    end.join("\n")
    call = scroll_call(node)
    Dir.mktmpdir('rjui_scroll') do |dir|
      File.write(File.join(dir, 'collectionScroll.js'), helper)
      File.write(File.join(dir, 'app.jsx'), <<~JSX)
        import { scrollCollectionToCell, collectionCellKeys } from './collectionScroll.js';
        function h(tag, props, ...children) {
          if (typeof tag === 'function') return tag({ ...(props || {}), children });
          const el = document.createElement(tag);
          for (const [k, v] of Object.entries(props || {})) {
            if (k === 'className') el.className = v;
            else if (k === 'style') Object.assign(el.style, v);
            else if (k !== 'key' && k !== 'data' && k !== 'ref') el.setAttribute(k, v);
          }
          for (const c of children.flat(Infinity)) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
          return el;
        }
        // A cell: 20 high, addressed by the id the Collection hands it; an
        // edge: 10 high, no address. Each is named by its data.
        const cell = ({ id, data }) => h('div', { id, 'data-name': data.name, style: { height: '20px', flexShrink: '0' } });
        const ACell = cell, BCell = cell;
        const HCell = ({ data }) => h('div', { 'data-name': 'H' + data.n, style: { height: '10px', flexShrink: '0' } });
        const FCell = ({ data }) => h('div', { 'data-name': 'F' + data.n, style: { height: '10px', flexShrink: '0' } });
        const out = {};
        for (const target of #{targets.to_json}) {
          const data = Object.assign(#{SCROLL_TO_CELL_DATA.strip}, { target });
          const targetRef = { current: null };
          const root = (#{jsx.strip});
          root.style.width = '100px';
          document.body.append(root);
          targetRef.current = root;
          #{call};
          const top = root.getBoundingClientRect().top;
          const first = Array.from(root.querySelectorAll('[data-name]'))
            .find((el) => Math.abs(el.getBoundingClientRect().top - top) < 1);
          out[target] = first ? first.getAttribute('data-name') : null;
          root.remove();
        }
        document.body.textContent = 'AT' + JSON.stringify(out);
      JSX
      log, status = Open3.capture2e(esbuild, File.join(dir, 'app.jsx'), '--bundle', '--jsx-factory=h',
                                    '--outfile=' + File.join(dir, 'app.js'))
      raise "esbuild: #{log}" unless status.success?

      File.write(File.join(dir, 'page.html'),
                 "<html><head><style>body{margin:0} #{css}</style></head><body><script src=\"app.js\"></script></body></html>")
      dom, = Open3.capture2e(chromium, '--headless', '--disable-gpu', '--allow-file-access-from-files', '--dump-dom',
                             "file://#{File.join(dir, 'page.html')}")
      JSON.parse(dom[/AT(\{.*?\})</m, 1] || raise("no result in:\n#{dom}"))
    end
  end

  it 'the effect names the Collection and hands keys only with cellIdProperty' do
    expect(scroll_call(SCROLL_TO_CELL_NODE)).to eq("scrollCollectionToCell(targetRef.current, \"target\", data.target, null, 'top', false, false)")
    keyed = scroll_call(SCROLL_TO_CELL_NODE.merge('cellIdProperty' => 'key'))
    expect(keyed).to include('collectionCellKeys([(data.rows?.sections?.[0]?.cells?.data ?? []), (data.rows?.sections?.[1]?.cells?.data ?? [])], "key")')
  end

  it 'renders: a number is a cell counted across the sections, headers and footers not counted' do
    # Children of the list: H0 A0 A1 A2 A3 A4 F0 H1 B0 B1 … — child 6 is F0,
    # child 3 is A2. The cells: A0…A4 are 0…4, B0 5, B1 6.
    expect(top_after(SCROLL_TO_CELL_NODE, [0, 3, 6, '6'])).to eq('0' => 'A0', '3' => 'A3', '6' => 'B1')
  end

  it 'renders: a key two sections share lands on the first section\'s cell; a key of one on its own' do
    at = top_after(SCROLL_TO_CELL_NODE.merge('cellIdProperty' => 'key'), %w[k3 x2 k1 nothing])
    expect(at).to eq('k3' => 'A3', 'x2' => 'B2', 'k1' => 'A1', 'nothing' => 'H0')
  end

  it 'under autoChangeTrackingId the keys are the enriched cellIds' do
    call = scroll_call(SCROLL_TO_CELL_NODE.merge('cellIdProperty' => 'key', 'autoChangeTrackingId' => true))
    expect(call).to include('enrichCellIds((data.rows?.sections?.[0]?.cells?.data ?? []), "key")')
    expect(call).to include('enrichCellIds((data.rows?.sections?.[1]?.cells?.data ?? []), "key")')
  end

  it 'the class-list shape: every data section, or the first on a horizontal Collection' do
    node = { 'type' => 'Collection', 'id' => 'target', 'items' => '@{rows}', 'cellClasses' => ['RowCell'],
             'cellIdProperty' => 'key', 'scrollTo' => '@{target}' }
    expect(scroll_call(node)).to include('collectionCellKeys((data.rows?.sections ?? []).map((section) => section.cells?.data ?? []), "key")')
    expect(scroll_call(node.merge('layout' => 'horizontal'))).to include('collectionCellKeys([data.rows?.sections?.[0]?.cells?.data ?? []], "key")')
  end

  it 'the generated file type-checks with a String scrollTo, keys and autoChangeTrackingId' do
    skip "tsc: #{TypeScriptCompiler.unavailable_reason}" if TypeScriptCompiler.unavailable_reason

    Dir.mktmpdir('rjui_scroll_ts') do |dir|
      File.write(File.join(dir, 'collectionScroll.ts'), helper(typescript: true))
      _, status = Open3.capture2e(TypeScriptCompiler.tsc_path, '--declaration', '--emitDeclarationOnly', '--strict',
                                  '--target', 'ES2020', '--lib', 'ES2020,DOM', '--outDir', dir,
                                  File.join(dir, 'collectionScroll.ts'))
      expect(status).to be_success
      declarations = File.read(File.join(dir, 'collectionScroll.d.ts')).gsub('export declare ', 'export ')
      tsx = generated(SCROLL_TO_CELL_NODE.merge('cellIdProperty' => 'key', 'autoChangeTrackingId' => true), typescript: true)
      ambient = <<~TS
        #{TypeScriptCompiler::AMBIENT.sub('declare const React: any;', '')}
        declare module 'react' { const React: any; export default React; export function useRef<T>(v: T): { current: T }; export const useEffect: any; }
        declare module '@/generated/data/ScrollScreenData' {
          export type ScrollScreenData = { rows?: { sections: { header?: unknown; footer?: unknown; cells?: { data: Record<string, unknown>[] } }[] }; target?: string };
          export const createScrollScreenData: () => ScrollScreenData;
        }
        declare module '@/generated/cellIdGenerator' { export function enrichCellIds(data: Record<string, unknown>[], primaryKey: string): Record<string, unknown>[]; }
        #{%w[ACell BCell HCell FCell].map { |c| "declare module '@/generated/data/#{c}Data' { export type #{c}Data = Record<string, unknown>; }\ndeclare module '@/generated/components/#{c}' { const C: (props: any) => any; export default C; }" }.join("\n")}
        declare module '@/generated/collectionScroll' { #{declarations} }
      TS
      expect(tsx).to compile_as_typescript.with_ambient(ambient)
    end
  end
end
