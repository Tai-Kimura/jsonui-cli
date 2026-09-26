# frozen_string_literal: true

require 'json'
require 'open3'
require 'tmpdir'
require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require 'react/converters/collection_converter'

# A section's declared header or footer is drawn only when the section has
# that data (4f ruling 2026-09-26, round 8) — as sjui (`if let headerData =
# section.header?.data`), kjui (`section.header?.let`) and both Dynamic
# renderers draw it. Until jsonui-cli 1.9.0 the web drew it with `{}` for its
# data when the section had none, on every route.
#
# The arm RUNS the emitted JSX (esbuild turns it into calls of a stub `h` that
# builds a plain tree; no DOM) against a data source whose first section has a
# header and a footer and whose second has neither, both declaring them, and
# lists the header / footer views the tree holds, with the data each got.
RSpec.describe 'rjui Collection: a section header or footer is drawn only with its data' do
  NEED_DATA_SECTIONS = [{ 'cell' => 'ACell', 'header' => 'HCell', 'footer' => 'FCell' },
              { 'cell' => 'BCell', 'header' => 'HCell', 'footer' => 'FCell' }].freeze

  NEED_DATA_ROUTES = {
    'list' => {},
    'list, lazy none' => { 'lazy' => 'none' },
    'grid' => { 'columns' => 2 },
    'horizontal' => { 'layout' => 'horizontal' },
    'flow' => { 'layout' => 'flow' },
    'flow, lazy none' => { 'layout' => 'flow', 'lazy' => 'none' }
  }.freeze

  def convert(extra)
    %i[info debug warn].each { |m| allow(RjuiTools::Core::Logger).to receive(m) }
    RjuiTools::React::Converters::CollectionConverter.new(
      { 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'sections' => NEED_DATA_SECTIONS }.merge(extra),
      { 'use_tailwind' => true, 'typescript' => true }
    ).convert
  end

  # The header / footer views in the emitted tree, as "H:<data.n>" / "F:<data.n>".
  def edges(jsx, sections_js)
    esbuild = File.expand_path('../../support/node_modules/.bin/esbuild', __dir__)
    skip 'esbuild is not installed under spec/support' unless File.executable?(esbuild)

    Dir.mktmpdir('rjui_edges') do |dir|
      File.write(File.join(dir, 'app.tsx'), <<~JSX)
        function h(tag: any, props: any, ...children: any[]): any {
          if (typeof tag === 'function') return tag({ ...(props || {}), children });
          return { tag, props: props || {}, children: children.flat(Infinity) };
        }
        const cell = () => ({ id }: any) => ({ tag: 'cell', props: { id }, children: [] });
        const edge = (letter: string) => ({ data }: any) => ({ tag: 'edge', props: { name: letter + ':' + (data && data.n) }, children: [] });
        const ACell = cell(), BCell = cell(), HCell = edge('H'), FCell = edge('F');
        const rows = (n: number) => ({ data: Array.from({ length: n }, (_, i) => ({ i })) });
        const data: any = { rows: { sections: #{sections_js} } };
        const out: string[] = [];
        (function walk(node: any) { if (!node || typeof node !== 'object') return;
          if (node.tag === 'edge') out.push(node.props.name);
          (node.children || []).forEach(walk); })(#{jsx.strip.gsub(/ as unknown as \w+Data/, '')});
        console.log(JSON.stringify(out));
      JSX
      built, status = Open3.capture2e(esbuild, File.join(dir, 'app.tsx'), '--jsx-factory=h', '--outfile=' + File.join(dir, 'app.js'))
      raise "esbuild: #{built}" unless status.success?

      out, status = Open3.capture2e('node', File.join(dir, 'app.js'))
      raise "node: #{out}" unless status.success?

      JSON.parse(out)
    end
  end

  NEED_DATA_ONE_SECTION = '[{ header: { n: 0 }, cells: rows(2), footer: { n: 0 } }, { cells: rows(2) }]'

  NEED_DATA_ROUTES.each do |route, extra|
    it "#{route}: the first section's header and footer, none for the second" do
      expect(edges(convert(extra), NEED_DATA_ONE_SECTION)).to eq(%w[H:0 F:0])
    end
  end

  it 'control: a section whose header data is empty draws it (the data is there)' do
    expect(edges(convert({}), '[{ header: {}, cells: rows(1) }, { header: { n: 1 }, footer: { n: 1 }, cells: rows(1) }]'))
      .to eq(%w[H:undefined H:1 F:1])
  end

  it 'type-checks against views that take their data as a record (no `{}` to fall back on)' do
    ambient = <<~TS
      declare const data: { rows?: { sections?: { header?: Record<string, unknown>; footer?: Record<string, unknown>;
        cells?: { data: Record<string, unknown>[] } }[] } };
      type ACellData = Record<string, unknown>; type BCellData = Record<string, unknown>;
      declare const ACell: (props: { key?: string | number; id?: string; data: ACellData }) => JSX.Element;
      declare const BCell: (props: { key?: string | number; id?: string; data: BCellData }) => JSX.Element;
      declare const HCell: (props: { data: Record<string, unknown> }) => JSX.Element;
      declare const FCell: (props: { data: Record<string, unknown> }) => JSX.Element;
    TS
    expect(TypeScriptCompiler.component(*NEED_DATA_ROUTES.values.map { |extra| convert(extra) })).to compile_as_typescript.with_ambient(ambient)
  end
end
