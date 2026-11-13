# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'
require 'rbconfig'
require_relative '../../spec_helper'
require 'core/config_manager'

# A generated file that says it is generated (@generated in its first lines) also says where it ends (the END
# AUTO-GENERATED footer): `jui lint-generated` fails a project (exit 3, generated-artifact health) on one without the
# other. 2.5.34's reorder helper was copied from its template, which had the header and no footer, so every web
# project that wrote a reorderable Collection failed lint-generated (ticket
# rjui-reorder-helper-missing-end-footer-fails-lint-generated). The JavaScript twins lost the footer the same way
# (esbuild drops a trailing comment): js/reorder.jsx and js/use_color_mode.js. Nothing ran a written helper through
# that rule, so nothing saw it.
RSpec.describe 'generated helpers carry both markers' do
  rjui_root = File.expand_path('../../..', __dir__)
  templates = File.join(rjui_root, 'lib/react/templates')
  sentinel = '@generated'
  footer = 'END AUTO-GENERATED — DO NOT APPEND BELOW THIS LINE'

  # The rule jui lint-generated applies (jui_cli/commands/lint_generated_cmd.py _check_file): a header in the
  # first lines asks for the footer in the last ones.
  def marker_problem(path, sentinel, footer)
    lines = File.read(path, encoding: 'UTF-8').lines
    return nil unless lines.first(12).any? { |l| l.include?(sentinel) }
    return nil if lines.last(5).any? { |l| l.include?(footer) }

    'header without the END AUTO-GENERATED footer'
  end

  it 'every template that carries the header ends with the footer, TypeScript and JavaScript twin alike' do
    files = Dir.glob(File.join(templates, '{*,js/*}.{ts,tsx,js,jsx}')).sort
    expect(files.size).to be >= 13
    marked = files.select { |f| File.read(f).lines.first(12).any? { |l| l.include?(sentinel) } }
    expect(marked.map { |f| f.delete_prefix("#{templates}/") }).to include('reorder.tsx', 'js/reorder.jsx',
                                                                            'use_color_mode.ts', 'js/use_color_mode.js')
    problems = marked.filter_map { |f| "#{f.delete_prefix("#{templates}/")}: #{marker_problem(f, sentinel, footer)}" if marker_problem(f, sentinel, footer) }
    expect(problems).to eq([])
  end

  describe 'what rjui build writes' do
    def build(rjui_root, typescript:)
      dir = Dir.mktmpdir('rjui_markers')
      tool = File.join(dir, 'rjui_tools')
      FileUtils.mkdir_p(tool)
      %w[bin lib].each { |d| raise "could not copy #{d}" unless system('cp', '-RL', File.join(rjui_root, d), tool) }
      config = RjuiTools::Core::ConfigManager::DEFAULT_CONFIG.merge('typescript' => typescript)
      File.write(File.join(dir, 'rjui.config.json'), JSON.pretty_generate(config))
      layouts = File.join(dir, 'src', 'Layouts')
      FileUtils.mkdir_p(File.join(layouts, 'Resources'))
      File.write(File.join(layouts, 'Resources', 'colors.json'),
                 JSON.generate({ 'light' => { 'ink' => '#111111' }, 'dark' => { 'ink' => '#EEEEEE' } }))
      cell = { 'type' => 'View', 'width' => 'matchParent', 'height' => 40,
               'data' => [{ 'name' => 'name', 'class' => 'String' }],
               'child' => [{ 'type' => 'Label', 'text' => '@{name}', 'fontColor' => 'ink' }] }
      screen = { 'type' => 'View', 'id' => 'root', 'width' => 'matchParent',
                 'data' => [{ 'name' => 'rows', 'class' => 'CollectionDataSource' },
                            { 'name' => 'move', 'class' => '((Int, Int, Int) -> Void)?' }],
                 'child' => [{ 'type' => 'Collection', 'id' => 'stops', 'width' => 'matchParent', 'items' => '@{rows}',
                               'sections' => [{ 'cell' => 'row_cell' }], 'cellIdProperty' => 'cellId',
                               'reorderable' => true, 'onReorder' => '@{move}', 'autoShrink' => false },
                             { 'type' => 'Label', 'id' => 'title', 'text' => 'x', 'autoShrink' => true, 'fontSize' => 16 }] }
      File.write(File.join(layouts, 'order_screen.json'), JSON.generate(screen))
      File.write(File.join(layouts, 'row_cell.json'), JSON.generate(cell))
      log, status = Open3.capture2e(RbConfig.ruby, File.join(tool, 'bin', 'rjui'), 'build', chdir: dir)
      [dir, log, status]
    end

    [true, false].each do |typescript|
      it "leaves no generated file with a header and no footer (#{typescript ? 'TypeScript' : 'JavaScript'})" do
        dir, log, status = build(rjui_root, typescript: typescript)
        expect(status.success?).to be(true), log
        written = Dir.glob(File.join(dir, 'src', '{generated,hooks}', '**', '*.{ts,tsx,js,jsx}')).sort
        helper = typescript ? 'reorder.tsx' : 'reorder.jsx'
        expect(written.map { |f| File.basename(f) }).to include(helper)
        problems = written.filter_map do |f|
          why = marker_problem(f, sentinel, footer)
          "#{f.delete_prefix("#{dir}/")}: #{why}" if why
        end
        expect(problems).to eq([])
      ensure
        FileUtils.rm_rf(dir) if dir
      end
    end
  end
end
