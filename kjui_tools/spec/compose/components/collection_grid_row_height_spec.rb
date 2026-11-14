# frozen_string_literal: true

require 'set'
require 'compose/components/collection_component'
require 'compose/helpers/resource_resolver'
require_relative '../../support/kotlin_compiler'
require_relative '../../support/collection_first_frame'

# kjui-collection-grid-row-matchparent-cell-height-unbounded: a non-lazy grid
# Collection (lazy none, columns >= 2) lays its cells out as Rows of weighted
# boxes. A cell whose root is height matchParent drew `fillMaxHeight()` into a
# Row that set no height of its own, so it reached for the parent's remaining
# height: a row of two cards took the screen (a consumer's chat, 360dp wide),
# where iOS draws the row as tall as its taller cell. The row now takes the
# tallest cell's height (IntrinsicSize.Min) and each box fills it — only when
# the cell's root is matchParent, and not when the cell holds a
# SubcomposeLayout (IntrinsicSize.Min throws there), as
# ModifierBuilder.adjust_for_intrinsic_size! decides for a plain Row.
RSpec.describe KjuiTools::Compose::Components::CollectionComponent do
  RESOLVER = KjuiTools::Compose::Helpers::ResourceResolver unless defined?(RESOLVER)

  def with_cell(root)
    RESOLVER.cell_layouts = { 'card_cell' => root }
    yield
  ensure
    RESOLVER.cell_layouts = nil
  end

  def sections_grid
    described_class.generate({ 'type' => 'Collection', 'id' => 'grid', 'lazy' => 'none', 'columns' => 2,
                               'columnSpacing' => 12, 'items' => '@{items}',
                               'sections' => [{ 'cell' => 'card_cell' }] }, 0, Set.new)
  end

  def class_list_grid
    described_class.generate({ 'type' => 'Collection', 'id' => 'grid', 'lazy' => 'none', 'columns' => 2,
                               'items' => '@{items}', 'cellClasses' => ['card_cell'] }, 0, Set.new)
  end

  FILLS_ROW = 'Row(modifier = Modifier.fillMaxWidth().height(IntrinsicSize.Min)'
  FILLS_BOX = 'Box(modifier = Modifier.weight(1f).fillMaxHeight())'

  MATCH_PARENT = { 'type' => 'View', 'width' => 'matchParent', 'height' => 'matchParent', 'minHeight' => 56,
                   'child' => [{ 'type' => 'Label', 'text' => '@{title}' }] }.freeze

  it 'a cell whose root is height matchParent: the row takes its tallest cell, each box fills it (sections and class-list)' do
    with_cell(MATCH_PARENT) do
      [sections_grid, class_list_grid].each do |code|
        expect(code).to include(FILLS_ROW), code
        expect(code).to include(FILLS_BOX), code
        expect(code).not_to include('Box(modifier = Modifier.weight(1f)) {'), code
      end
    end
  end

  it 'records the import the row needs' do
    with_cell(MATCH_PARENT) do
      imports = Set.new
      described_class.generate({ 'type' => 'Collection', 'id' => 'grid', 'lazy' => 'none', 'columns' => 2,
                                 'items' => '@{items}', 'sections' => [{ 'cell' => 'card_cell' }] }, 0, imports)
      expect(imports).to include(:intrinsic_size)
    end
  end

  it 'a cell whose root wraps its content: the rows are as they were' do
    with_cell(MATCH_PARENT.merge('height' => 'wrapContent')) do
      [sections_grid, class_list_grid].each do |code|
        expect(code).not_to include('IntrinsicSize'), code
        expect(code).to include('Box(modifier = Modifier.weight(1f)) {'), code
      end
    end
  end

  it 'a cell holding a lazy list (a SubcomposeLayout): the rows are as they were, IntrinsicSize.Min would throw' do
    lazy = MATCH_PARENT.merge('child' => [{ 'type' => 'Collection', 'items' => '@{rows}', 'sections' => [{ 'cell' => 'x_cell' }] }])
    with_cell(lazy) do
      [sections_grid, class_list_grid].each do |code|
        expect(code).not_to include('IntrinsicSize'), code
      end
    end
  end

  # The rows compile, with warnings as errors, on the sections grid and the
  # class-list grid (the stub universe of spec/support/collection_first_frame.rb,
  # plus the IntrinsicSize the row asks for).
  describe 'compiled' do
    include CollectionFirstFrame

    INTRINSIC_STUBS = <<~KOTLIN
      enum class IntrinsicSize { Min, Max }
      fun Modifier.height(intrinsicSize: IntrinsicSize): Modifier = this
    KOTLIN

    it 'the grids compile with allWarningsAsErrors' do
      RESOLVER.cell_layouts = { 'ACell' => MATCH_PARENT }
      functions = {
        'sectionsGrid' => described_class.generate({ 'type' => 'Collection', 'id' => 'grid', 'lazy' => 'none', 'columns' => 2,
                                                     'columnSpacing' => 12, 'items' => '@{rows}',
                                                     'sections' => [{ 'cell' => 'ACell' }] }, 0, Set.new),
        'classListGrid' => described_class.generate({ 'type' => 'Collection', 'id' => 'grid', 'lazy' => 'none', 'columns' => 2,
                                                      'items' => '@{rows}', 'cellClasses' => ['ACell'] }, 0, Set.new)
      }
      functions.each_value { |code| expect(code).to include(FILLS_ROW), code }
      expect(INTRINSIC_STUBS + program(functions)).to compile_as_kotlin.with_warnings_as_errors
    ensure
      RESOLVER.cell_layouts = nil
    end
  end

  it 'a cell with no layout to read: the rows are as they were' do
    with_cell(nil) do
      expect(sections_grid).not_to include('IntrinsicSize')
    end
  end
end
