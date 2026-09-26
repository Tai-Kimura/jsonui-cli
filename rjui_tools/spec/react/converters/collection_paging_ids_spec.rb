# frozen_string_literal: true

require 'json'
require 'open3'
require 'tmpdir'
require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require 'react/converters/collection_converter'

# A paging Collection's item addresses count across the sections (4f ruling
# 2026-09-26, round 7): `<id>_item_<n>` is the page's place among all the
# pages — sjui's page tag and accessibility identifier, and kjui's pager test
# tag, count the same way. Until jsonui-cli 1.9.0 each section's items were
# `<id>_item_0…` again, so two sections' first pages answered one address.
#
# And a pager's pages are its cells (round 6's ruling, every drawn section in
# order): a section's header and footer are not pages, as sjui's TabView,
# kjui's HorizontalPager and both Dynamic pagers draw. Until jsonui-cli 1.9.0
# rjui put them in the snap container, each a page with no address.
#
# The arm RUNS the emitted JSX (esbuild turns it into calls of a stub `h` that
# builds a plain tree; no DOM) against a data source and reads every id off
# the tree, in order, and what the pager's own children are — its pages.
RSpec.describe 'rjui Collection: paging item ids count across the sections' do
  def convert(extra)
    %i[info debug warn].each { |m| allow(RjuiTools::Core::Logger).to receive(m) }
    RjuiTools::React::Converters::CollectionConverter.new(
      { 'type' => 'Collection', 'id' => 'pager', 'layout' => 'horizontal', 'paging' => true, 'items' => '@{rows}' }.merge(extra),
      { 'use_tailwind' => true }
    ).convert
  end

  # The ids the emitted pager draws for data sections of `counts` cells.
  def ids(jsx, counts)
    run(jsx, counts)['ids']
  end

  # The root's children — a pager's pages — by id, `(no id)` for one without.
  def pages(jsx, counts)
    run(jsx, counts)['pages']
  end

  def run(jsx, counts)
    esbuild = File.expand_path('../../support/node_modules/.bin/esbuild', __dir__)
    skip 'esbuild is not installed under spec/support' unless File.executable?(esbuild)

    Dir.mktmpdir('rjui_ids') do |dir|
      File.write(File.join(dir, 'app.jsx'), <<~JSX)
        function h(tag, props, ...children) {
          if (typeof tag === 'function') return tag({ ...(props || {}), children });
          return { tag, props: props || {}, children: children.flat(Infinity) };
        }
        const cell = () => ({ id }) => ({ tag: 'cell', props: { id }, children: [] });
        const ACell = cell(), BCell = cell(), CCell = cell(), HCell = cell(), FCell = cell();
        const rows = (n) => ({ data: Array.from({ length: n }, (_, i) => ({ i })) });
        const data = { rows: { sections: #{JSON.generate(counts.map { |n| { 'cells' => { 'data' => Array.new(n) { |i| { 'i' => i } } }, 'header' => {}, 'footer' => {} } })} } };
        const out = [];
        const root = (#{jsx.strip});
        (function walk(node) { if (!node || typeof node !== 'object') return;
          if (node.props && typeof node.props.id === 'string' && node.props.id.includes('_item_')) out.push(node.props.id);
          (node.children || []).forEach(walk); })(root);
        const pages = root.children.filter((c) => c && typeof c === 'object').map((c) => c.props.id || '(no id)');
        console.log(JSON.stringify({ ids: out, pages }));
      JSX
      built, status = Open3.capture2e(esbuild, File.join(dir, 'app.jsx'), '--jsx-factory=h', '--outfile=' + File.join(dir, 'app.js'))
      raise "esbuild: #{built}" unless status.success?

      out, status = Open3.capture2e('node', File.join(dir, 'app.js'))
      raise "node: #{out}" unless status.success?

      JSON.parse(out)
    end
  end

  PAGING_IDS_SECTIONS = [{ 'cell' => 'ACell', 'footer' => 'FCell' }, { 'header' => 'HCell' }, { 'cell' => 'BCell', 'header' => 'HCell' },
              { 'cell' => 'CCell' }].freeze

  it 'two sections: 0 … n-1 across them' do
    expect(ids(convert('sections' => PAGING_IDS_SECTIONS.values_at(0, 2)), [2, 3])).to eq((0..4).map { |i| "pager_item_#{i}" })
  end

  it 'a section that draws no cell adds no page and no id' do
    expect(ids(convert('sections' => PAGING_IDS_SECTIONS), [2, 5, 3, 1])).to eq((0..5).map { |i| "pager_item_#{i}" })
  end

  it "a section's header and footer are not pages: every page is a cell with its address" do
    expect(pages(convert('sections' => PAGING_IDS_SECTIONS), [2, 5, 3, 1])).to eq((0..5).map { |i| "pager_item_#{i}" })
  end

  it 'control: a horizontal list draws the headers and footers among its children' do
    list = convert('paging' => false, 'sections' => PAGING_IDS_SECTIONS)
    expect(pages(list, [2, 5, 3, 1])).to eq(%w[pager_item_0 pager_item_1 (no\ id) (no\ id) (no\ id) pager_item_0 pager_item_1
                                                pager_item_2 pager_item_0])
  end

  # A vertical Collection with `paging` is a list on iOS and Android (their
  # pagers are horizontal), so the web draws it as one too, whatever it snaps.
  it 'control: a list keeps each section counting from 0 (only a pager is one run of pages)' do
    [false, true].each do |paging|
      list = convert('layout' => 'vertical', 'paging' => paging, 'sections' => PAGING_IDS_SECTIONS.values_at(0, 2))
      expect(ids(list, [2, 3])).to eq(%w[pager_item_0 pager_item_1 pager_item_0 pager_item_1 pager_item_2]), paging.to_s
      expect(pages(list, [2, 3]).count('(no id)')).to eq(2), paging.to_s # A's footer, B's header
    end
  end

  it 'one section: the emit it always had' do
    expect(convert('sections' => [{ 'cell' => 'ACell' }])).to include('id={`pager_item_${cellIndex}`}')
  end

  it 'the pager type-checks, its sections and their addresses' do
    ambient = <<~TS
      declare const data: { rows?: { sections?: { header?: Record<string, unknown>; footer?: Record<string, unknown>;
        cells?: { data: Record<string, unknown>[] } }[] } };
      #{%w[A B C].map { |l| "type #{l}CellData = Record<string, unknown>;\ndeclare const #{l}Cell: (props: { key?: string | number; id?: string; data: #{l}CellData }) => JSX.Element;" }.join("\n")}
      declare const HCell: (props: { data: unknown }) => JSX.Element;
      declare const FCell: (props: { data: unknown }) => JSX.Element;
    TS
    jsx = RjuiTools::React::Converters::CollectionConverter.new(
      { 'type' => 'Collection', 'id' => 'pager', 'layout' => 'horizontal', 'paging' => true, 'items' => '@{rows}', 'sections' => PAGING_IDS_SECTIONS },
      { 'use_tailwind' => true, 'typescript' => true }
    ).convert
    expect(TypeScriptCompiler.component(jsx)).to compile_as_typescript.with_ambient(ambient)
  end
end
