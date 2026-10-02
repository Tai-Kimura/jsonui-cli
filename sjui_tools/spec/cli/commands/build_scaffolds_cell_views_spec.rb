# frozen_string_literal: true

require 'open3'
require 'rbconfig'
require 'tmpdir'
require 'json'
require 'fileutils'

# A cell layout written by hand gets its `<Cell>View` and ViewModel from the
# build (CellViewScaffold), as kjui's build scaffolds a hand-added layout.
# Until jsonui-cli 1.9.6 the build wrote the cell's Data and GeneratedView
# only: the screen's generated code named `<Cell>View(data:)`, nothing
# defined it, and the build said warning 0 while the app did not compile
# (ticket sjui-build-does-not-scaffold-cell-views-for-hand-written-cell-layouts;
# measured 2026-10-02 with xcodebuild against SwiftJsonUI 10.29.1 — BUILD
# FAILED "cannot find 'BookCoverCellView' in scope" without the scaffold,
# BUILD SUCCEEDED with it). A cell view it cannot scaffold is a warning.
RSpec.describe 'sjui build and the cell views a Collection draws' do
  def tool_root
    File.expand_path('../../..', __dir__)
  end

  def sjui(dir, *args)
    log, status = Open3.capture2e(RbConfig.ruby, File.join(dir, 'sjui_tools', 'bin', 'sjui'), *args, chdir: dir)
    [log.gsub(/\e\[[0-9;]*m/, ''), status]
  end

  def project(layouts)
    dir = Dir.mktmpdir('sjui_cell_scaffold')
    @dirs << dir
    tool = File.join(dir, 'sjui_tools')
    FileUtils.mkdir_p(tool)
    # `-L`: lib/core's files are relative links into shared/core.
    %w[bin lib].each { |d| raise "could not copy #{d}" unless system('cp', '-RL', File.join(tool_root, d), tool) }
    File.write(File.join(dir, 'sjui.config.json'), JSON.pretty_generate(
      'mode' => 'swiftui', 'project_name' => 'Cells', 'project_file_name' => 'Cells',
      'source_directory' => 'Cells', 'layouts_directory' => 'Layouts', 'view_directory' => 'View',
      'data_directory' => 'Data', 'viewmodel_directory' => 'ViewModel', 'string_files' => []
    ))
    FileUtils.mkdir_p(File.join(dir, 'Cells.xcodeproj'))
    layouts.each do |rel, json|
      path = File.join(dir, 'Cells', 'Layouts', rel)
      FileUtils.mkdir_p(File.dirname(path))
      File.write(path, JSON.generate(json))
    end
    dir
  end

  def screen(*cells)
    { 'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent', 'child' => [
      { 'data' => [{ 'name' => 'rows', 'class' => 'CollectionDataSource' }] },
      { 'type' => 'Collection', 'id' => 'list', 'width' => 'matchParent', 'height' => 'matchParent',
        'items' => '@{rows}', 'cellIdProperty' => 'id', 'sections' => cells.map { |c| { 'cell' => c } } }
    ] }
  end

  def cell(id)
    { 'type' => 'View', 'id' => id, 'width' => 'matchParent', 'height' => 'wrapContent', 'child' => [
      { 'data' => [{ 'name' => 'title', 'class' => 'String', 'defaultValue' => '' }] },
      { 'type' => 'Label', 'id' => "#{id}_title", 'text' => '@{title}', 'width' => 'wrapContent', 'height' => 'wrapContent' }
    ] }
  end

  def file(dir, rel)
    File.join(dir, 'Cells', rel)
  end

  def warnings(log)
    log.lines.grep(/WARNING/)
  end

  before { @dirs = [] }
  after { @dirs.each { |d| FileUtils.rm_rf(d) } }

  it "scaffolds a hand-written cell's View and ViewModel, whichever way the section names it, with no warning" do
    dir = project('home.json' => screen('BookCoverCell', 'book_spine_cell'),
                  'home/book_cover_cell.json' => cell('cover'), 'home/book_spine_cell.json' => cell('spine'))
    log, status = sjui(dir, 'build')
    expect(status.success?).to be(true), log
    expect(warnings(log)).to eq([])
    %w[BookCoverCell BookSpineCell].each do |name|
      view = file(dir, "View/Home/#{name}/#{name}View.swift")
      expect(File.read(view)).to include("struct #{name}View: View, Equatable {", "#{name}GeneratedView(data: $viewModel.data)")
      expect(File.read(file(dir, "ViewModel/#{name}ViewModel.swift"))).to include("@Published var data = #{name}Data()")
      expect(File.exist?(file(dir, "View/Home/#{name}/#{name}GeneratedView.swift"))).to be(true)
      expect(log).to include("Scaffolded cell #{name}View: ")
    end
    expect(File.read(file(dir, 'View/Home/HomeGeneratedView.swift'))).to include('BookCoverCellView(data:', 'BookSpineCellView(data:')
  end

  it 'never writes over a file, and scaffolds nothing for a cell view or ViewModel some source already defines' do
    dir = project('home.json' => screen('own_cell', 'half_cell'),
                  'home/own_cell.json' => cell('own'), 'home/half_cell.json' => cell('half'))
    FileUtils.mkdir_p(file(dir, 'Elsewhere'))
    File.write(file(dir, 'Elsewhere/Own.swift'), "struct OwnCellView: View { init(data: Any) {} }\n")
    File.write(file(dir, 'Elsewhere/HalfVM.swift'), "final class HalfCellViewModel {}\n")
    sjui(dir, 'build')
    expect(File.exist?(file(dir, 'View/Home/OwnCell/OwnCellView.swift'))).to be(false)
    expect(File.exist?(file(dir, 'ViewModel/OwnCellViewModel.swift'))).to be(false)
    expect(File.exist?(file(dir, 'View/Home/HalfCell/HalfCellView.swift'))).to be(true)
    expect(File.exist?(file(dir, 'ViewModel/HalfCellViewModel.swift'))).to be(false)

    edited = file(dir, 'View/Home/HalfCell/HalfCellView.swift')
    File.write(edited, "// the app's\n#{File.read(edited)}")
    log, = sjui(dir, 'build', '--clean')
    expect(File.read(edited)).to start_with("// the app's\n")
    expect(log).not_to include('Scaffolded cell')
  end

  it 'warns — and --strict fails — when a drawn cell view has no layout to scaffold it from' do
    dir = project('home.json' => screen('ghost_cell'))
    log, status = sjui(dir, 'build')
    expect(status.success?).to be(true)
    expect(warnings(log).join).to include('Collection cell ghost_cell is drawn as GhostCellView, which no Swift source defines',
                                          'no layout the build converts gives this name')
    _, strict = sjui(dir, 'build', '--strict')
    expect(strict.success?).to be(false)
  end

  it 'control: a partial cell layout is not one the build converts, so it is named, not scaffolded' do
    dir = project('home.json' => screen('part_cell'), 'home/part_cell.json' => cell('part').merge('partial' => true))
    log, = sjui(dir, 'build')
    expect(warnings(log).join).to include('Collection cell part_cell is drawn as PartCellView')
    expect(Dir.glob(file(dir, '**/PartCellView.swift'))).to eq([])
  end
end
