# frozen_string_literal: true

require 'cli/commands/build'
require 'fileutils'
require 'tmpdir'

# Every Collection arm passes `modifier = Modifier.testTag(...)` into the cell
# view — that modifier IS the cell's test address. A cell view that takes no
# `modifier` therefore does not compile, and kotlinc reports it at the call
# sites (11 of them on the project that hit this), not at the four files that
# need the parameter.
#
# `jui generate cell` has always emitted the parameter. The screen scaffold
# did not, so a View created as a screen and later used as a cell was missing
# it. That was survivable only while two arms — flow and non-lazy horizontal —
# passed no modifier at all; they were the last place such a view could still
# be used. Giving those arms their cell addresses took that away, which is how
# a consumer found it. The screen scaffold now emits the parameter too; this
# check is for the files that predate that.
RSpec.describe KjuiTools::CLI::Commands::Build do
  let(:build) { described_class.new }

  around do |example|
    Dir.mktmpdir('cellmod') { |dir| @root = dir; example.run }
  end

  def write_cell_view(class_name, signature)
    dir = File.join(@root, 'src/main/kotlin/views', class_name.downcase)
    FileUtils.mkdir_p(dir)
    File.write(File.join(dir, "#{class_name}View.kt"), <<~KOTLIN)
      @Composable
      fun #{class_name}View(
      #{signature}
      ) {
          val data by viewModel.data.collectAsState()
      }
    KOTLIN
  end

  def missing(cells)
    build.instance_variable_set(:@collection_cells, cells)
    build.send(:cell_views_missing_modifier, @root,
               { 'source_directory' => 'src/main', 'view_directory' => 'kotlin/views' })
  end

  it 'names a cell view whose signature has no modifier' do
    write_cell_view('ProbeCell', '    viewModel: ProbeCellViewModel = viewModel()')
    expect(missing(['probe_cell']).size).to eq(1)
  end

  # The first version matched non-greedily to the first `)`, which lands
  # inside `viewModel = viewModel()` — so it reported every compliant cell.
  # A check that fires on correct input is not a check.
  it 'stays silent when the modifier is there, past a defaulted viewModel()' do
    write_cell_view('ProbeCell',
                    "    viewModel: ProbeCellViewModel = viewModel(),\n    modifier: Modifier = Modifier")
    expect(missing(['probe_cell'])).to be_empty
  end

  it 'says nothing about a view no Collection uses as a cell' do
    write_cell_view('Lonely', '    viewModel: LonelyViewModel = viewModel()')
    expect(missing([])).to be_empty
  end

  it 'says nothing when the cell view file does not exist yet' do
    expect(missing(['never_written'])).to be_empty
  end

  it 'reports each offending cell once, however many Collections use it' do
    write_cell_view('ProbeCell', '    viewModel: ProbeCellViewModel = viewModel()')
    expect(missing(%w[probe_cell probe_cell probe_cell]).size).to eq(1)
  end

  describe 'which views are collected' do
    it 'takes the cells a Collection declares' do
      build.instance_variable_set(:@collection_cells, [])
      build.send(:collect_collection_cells,
                 { 'type' => 'View', 'child' => [
                   { 'type' => 'Collection', 'sections' => [{ 'cell' => 'a_cell' }] },
                   { 'type' => 'Collection', 'sections' => [{ 'cell' => 'b_cell' }] }
                 ] })
      expect(build.instance_variable_get(:@collection_cells)).to eq(%w[a_cell b_cell])
    end

    it 'ignores a View that is not a Collection' do
      build.instance_variable_set(:@collection_cells, [])
      build.send(:collect_collection_cells,
                 { 'type' => 'View', 'sections' => [{ 'cell' => 'not_a_cell' }] })
      expect(build.instance_variable_get(:@collection_cells)).to be_empty
    end
  end
end
