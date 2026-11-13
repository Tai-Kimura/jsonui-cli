# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'
require 'rbconfig'
require_relative '../spec_helper'
require 'react/converters/collection_converter'
require 'react/reorder'
require 'core/config_manager'

# A reorderable Collection on the web (ticket jui-collection-drag-to-reorder, ruling B 2026-11-13): the converter
# wraps each section's rows in the generated helper's JsonuiReorderSection, each row in a JsonuiReorderItem (which
# takes the row's key, its identity when the Collection names one), and marks the Collection's element as the
# container a release is judged in; `rjui build` writes the helper (lib/react/templates/reorder.tsx, or its .jsx
# twin) as @/generated/reorder when a layout has one, and the screen imports what it uses. v1 is one vertical
# column: a grid, a horizontal, a flow or a paging Collection is drawn as before. How the rows move is
# conformance/hosts/web/scripts/collection_reorder_probe.mjs (a real browser) and
# spec/react/reorder_helper_follows_the_shared_rule_spec.rb (the rule's vectors).
RSpec.describe 'a reorderable Collection (rjui)' do
  def convert(extra, typescript: true)
    base = { 'type' => 'Collection', 'id' => 'stops', 'cellIdProperty' => 'cellId', 'reorderable' => true,
             'onReorder' => '@{onMoveStop}' }
    RjuiTools::React::Converters::CollectionConverter.new(base.merge(extra), { 'use_tailwind' => true,
                                                                           'typescript' => typescript }).convert
  end

  SECTIONS = { 'items' => '@{rows}', 'sections' => [{ 'cell' => 'RowCell', 'header' => 'Head', 'footer' => 'Foot' }] }.freeze
  CLASS_LIST = { 'items' => '@{rows}', 'cellClasses' => ['RowCell'], 'lazy' => 'none' }.freeze

  describe 'the drawn rows' do
    it 'wraps a section and its rows, marks the container, and keys a row by its identity (sections path)' do
      out = convert(SECTIONS)
      expect(out).to include('data-jsonui-reorder=""')
      expect(out).to include('<JsonuiReorderSection section={0} count={((data.rows?.sections?.[0]?.cells?.data ?? [])).length} ' \
                             'enabled={true} onReorder={data.onMoveStop}>')
      expect(out).to include('<JsonuiReorderItem key={String((cellData as Record<string, unknown>)["cellId"]')
      expect(out).to include('index={cellIndex}>')
      expect(out).to include('<RowCell id={`stops_item_${cellIndex}`} data={cellData as unknown as RowCellData} />')
      expect(out.index('<JsonuiReorderSection')).to be > out.index('<Head')   # the header is outside the rows
      expect(out.index('</JsonuiReorderSection>')).to be < out.index('<Foot')
    end

    it 'wraps every data section on the class-list path' do
      out = convert(CLASS_LIST)
      expect(out).to include('<JsonuiReorderSection key={sectionIndex} section={sectionIndex}')
      expect(out).to include('{(section.cells?.data ?? []).map((cellData, cellIndex) => (')
      expect(out).to include('<JsonuiReorderItem key=')
    end

    it 'passes a bound reorderable, the handle and the locked rows' do
      out = convert(SECTIONS.merge('reorderable' => '@{editing}', 'reorderHandle' => 'grip',
                                   'reorderLockedProperty' => 'isDivider'))
      expect(out).to include('enabled={(data.editing === true)}')
      expect(out).to include('handleId="grip"')
      expect(out).to include('locked={jsonuiReorderLocked((data.rows?.sections?.[0]?.cells?.data ?? []), "isDivider")}')
    end

    it 'keys a row by its index when the Collection names no identity (the validator warns it)' do
      out = convert(SECTIONS.merge('cellIdProperty' => nil))
      expect(out).to include('<JsonuiReorderItem key={cellIndex} index={cellIndex}>')
    end

    it 'writes no TypeScript cast in a JavaScript project' do
      out = convert(SECTIONS, typescript: false)
      expect(out).to include('<JsonuiReorderItem key={String(cellData["cellId"] ?? cellData["cellId"] ?? cellIndex)}')
      expect(out).not_to include(' as ')
    end

    {
      'reorderable false' => { 'reorderable' => false },
      'no reorderable' => { 'reorderable' => nil },
      'a grid' => { 'columns' => 2 },
      'a horizontal Collection' => { 'layout' => 'horizontal' },
      'a flow' => { 'layout' => 'flow' }
    }.each do |what, extra|
      it "draws #{what} as before" do
        out = convert(SECTIONS.merge(extra))
        expect(out).not_to include('JsonuiReorder')
        expect(out).not_to include('data-jsonui-reorder')
      end
    end
  end

  describe 'whether a layout uses the helper' do
    it 'is true for a reorderable Collection anywhere in the tree, true or bound' do
      tree = { 'type' => 'View', 'child' => [{ 'type' => 'View', 'child' => [{ 'type' => 'Collection', 'reorderable' => true }] }] }
      expect(RjuiTools::React::Reorder.used?(tree)).to be(true)
      expect(RjuiTools::React::Reorder.used?({ 'type' => 'Collection', 'reorderable' => '@{editing}' })).to be(true)
    end

    it 'is false otherwise' do
      expect(RjuiTools::React::Reorder.used?({ 'type' => 'Collection', 'reorderable' => false })).to be(false)
      expect(RjuiTools::React::Reorder.used?({ 'type' => 'View', 'reorderable' => true })).to be(false)
    end
  end

  describe 'rjui build' do
    rjui_root = File.expand_path('../..', __dir__)

    def build(rjui_root, layouts, typescript:)
      dir = Dir.mktmpdir('rjui_reorder')
      tool = File.join(dir, 'rjui_tools')
      FileUtils.mkdir_p(tool)
      %w[bin lib].each { |d| raise "could not copy #{d}" unless system('cp', '-RL', File.join(rjui_root, d), tool) }
      config = RjuiTools::Core::ConfigManager::DEFAULT_CONFIG.merge('typescript' => typescript)
      File.write(File.join(dir, 'rjui.config.json'), JSON.pretty_generate(config))
      FileUtils.mkdir_p(File.join(dir, 'src', 'Layouts'))
      layouts.each { |name, body| File.write(File.join(dir, 'src', 'Layouts', "#{name}.json"), JSON.generate(body)) }
      log, status = Open3.capture2e(RbConfig.ruby, File.join(tool, 'bin', 'rjui'), 'build', chdir: dir)
      [dir, log, status]
    end

    let(:cell) { { 'type' => 'View', 'width' => 'matchParent', 'height' => 40, 'data' => [{ 'name' => 'name', 'class' => 'String' }] } }
    let(:screen) do
      { 'type' => 'View', 'id' => 'root', 'width' => 'matchParent',
        'data' => [{ 'name' => 'rows', 'class' => 'CollectionDataSource' }, { 'name' => 'move', 'class' => '((Int, Int, Int) -> Void)?' }],
        'child' => [{ 'type' => 'Collection', 'id' => 'stops', 'width' => 'matchParent', 'items' => '@{rows}',
                      'sections' => [{ 'cell' => 'row_cell' }], 'cellIdProperty' => 'cellId', 'reorderable' => true,
                      'onReorder' => '@{move}' }] }
    end

    { true => %w[reorder.tsx OrderScreen.tsx], false => %w[reorder.jsx OrderScreen.jsx] }.each do |ts, (helper, component)|
      it "writes the helper and imports it (#{ts ? 'TypeScript' : 'JavaScript'})" do
        dir, log, status = build(rjui_root, { 'order_screen' => screen, 'row_cell' => cell }, typescript: ts)
        expect(status.success?).to be(true), log
        written = File.join(dir, 'src', 'generated', helper)
        expect(File.exist?(written)).to be(true), "no #{helper}: #{log}"
        template = ts ? 'reorder.tsx' : File.join('js', 'reorder.jsx')
        expect(File.read(written)).to eq(File.read(File.join(rjui_root, 'lib/react/templates', template)))
        source = File.read(Dir.glob(File.join(dir, 'src', '**', component)).first)
        expect(source).to include("import { JsonuiReorderSection, JsonuiReorderItem } from '@/generated/reorder';")
      ensure
        FileUtils.rm_rf(dir) if dir
      end
    end

    it 'writes no helper when no layout reorders' do
      plain = screen.merge('child' => [screen['child'][0].merge('reorderable' => false)])
      dir, log, status = build(rjui_root, { 'order_screen' => plain, 'row_cell' => cell }, typescript: true)
      expect(status.success?).to be(true), log
      expect(Dir.glob(File.join(dir, 'src', 'generated', 'reorder.*'))).to be_empty
      source = File.read(Dir.glob(File.join(dir, 'src', '**', 'OrderScreen.tsx')).first)
      expect(source).not_to include('@/generated/reorder')
    ensure
      FileUtils.rm_rf(dir) if dir
    end
  end
end
