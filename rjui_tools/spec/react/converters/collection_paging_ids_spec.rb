# frozen_string_literal: true

require 'json'
require 'open3'
require 'tmpdir'
require_relative '../../spec_helper'
require 'react/converters/collection_converter'

# A paging Collection's item addresses count across the sections (4f ruling
# 2026-09-26, round 7): `<id>_item_<n>` is the page's place among all the
# pages — sjui's page tag and accessibility identifier, and kjui's pager test
# tag, count the same way. Until jsonui-cli 1.9.0 each section's items were
# `<id>_item_0…` again, so two sections' first pages answered one address.
#
# The arm RUNS the emitted JSX (esbuild turns it into calls of a stub `h` that
# builds a plain tree; no DOM) against a data source and reads every id off
# the tree, in order.
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
    esbuild = File.expand_path('../../support/node_modules/.bin/esbuild', __dir__)
    skip 'esbuild is not installed under spec/support' unless File.executable?(esbuild)

    Dir.mktmpdir('rjui_ids') do |dir|
      File.write(File.join(dir, 'app.jsx'), <<~JSX)
        function h(tag, props, ...children) {
          if (typeof tag === 'function') return tag({ ...(props || {}), children });
          return { tag, props: props || {}, children: children.flat(Infinity) };
        }
        const cell = () => ({ id }) => ({ tag: 'cell', props: { id }, children: [] });
        const ACell = cell(), BCell = cell(), CCell = cell(), HCell = cell();
        const rows = (n) => ({ data: Array.from({ length: n }, (_, i) => ({ i })) });
        const data = { rows: { sections: #{JSON.generate(counts.map { |n| { 'cells' => { 'data' => Array.new(n) { |i| { 'i' => i } } } } })} } };
        const out = [];
        (function walk(node) { if (!node || typeof node !== 'object') return;
          if (node.props && typeof node.props.id === 'string' && node.props.id.includes('_item_')) out.push(node.props.id);
          (node.children || []).forEach(walk); })(#{jsx.strip});
        console.log(JSON.stringify(out));
      JSX
      built, status = Open3.capture2e(esbuild, File.join(dir, 'app.jsx'), '--jsx-factory=h', '--outfile=' + File.join(dir, 'app.js'))
      raise "esbuild: #{built}" unless status.success?

      out, status = Open3.capture2e('node', File.join(dir, 'app.js'))
      raise "node: #{out}" unless status.success?

      JSON.parse(out)
    end
  end

  SECTIONS = [{ 'cell' => 'ACell' }, { 'header' => 'HCell' }, { 'cell' => 'BCell' }, { 'cell' => 'CCell' }].freeze

  it 'two sections: 0 … n-1 across them' do
    expect(ids(convert('sections' => SECTIONS.values_at(0, 2)), [2, 3])).to eq((0..4).map { |i| "pager_item_#{i}" })
  end

  it 'a section that draws no cell adds no page and no id' do
    expect(ids(convert('sections' => SECTIONS), [2, 5, 3, 1])).to eq((0..5).map { |i| "pager_item_#{i}" })
  end

  it 'control: a list keeps each section counting from 0 (only a pager is one run of pages)' do
    list = convert('layout' => 'vertical', 'paging' => false, 'sections' => SECTIONS.values_at(0, 2))
    expect(ids(list, [2, 3])).to eq(%w[pager_item_0 pager_item_1 pager_item_0 pager_item_1 pager_item_2])
  end

  it 'one section: the emit it always had' do
    expect(convert('sections' => SECTIONS.first(1))).to include('id={`pager_item_${cellIndex}`}')
  end
end
