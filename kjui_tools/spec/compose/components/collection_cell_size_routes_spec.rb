# frozen_string_literal: true

require 'set'
require 'compose/components/collection_component'
require_relative '../../support/kotlin_compiler'
require_relative '../../support/compose_bounded_scroll_stubs'
require_relative '../../support/collection_first_frame'

# A Collection's cellWidth / cellHeight size every cell, whatever route draws
# it (the SSoT's Collection.cellWidth / cellHeight: "Fixed width / height for
# every cell … Applied to the cell view AFTER it is built"; ticket
# collection-cellwidth-cellheight-unread-on-some-routes). kjui read them on
# the lazy list, the lazy grid and the lazy horizontal list only; lazy none,
# wrapContent, the non-lazy grid, the non-lazy row and the flow drew every
# cell at its own size, where sjui, rjui and KotlinJsonUI Dynamic size it. Each route now draws the cell in the Box the lazy routes draw
# (cell_size_box_open): the declared size, the cell anchored top-start and
# clipped there. The pager's page draws the same box in its middle (the
# requester's ruling 2026-11-15, as sjui's TabView page centres the cell's
# frame); until then its cell filled the page.
RSpec.describe 'kjui codegen: a Collection cell takes the declared cellWidth / cellHeight on every route' do
  include CollectionFirstFrame

  SIZE_ROUTES = {
    'list' => {}, 'lazyNone' => { 'lazy' => 'none' }, 'wrapContent' => { 'height' => 'wrapContent' },
    'grid' => { 'columns' => 2 }, 'gridLazyNone' => { 'columns' => 2, 'lazy' => 'none' },
    'row' => { 'layout' => 'horizontal' }, 'rowLazyNone' => { 'layout' => 'horizontal', 'lazy' => 'none' },
    'flow' => { 'layout' => 'flow' }, 'flowLazyNone' => { 'layout' => 'flow', 'lazy' => 'none' },
    'classListLazyNone' => { 'sections' => nil, 'cellClasses' => ['ACell'], 'lazy' => 'none' },
    'classListFlow' => { 'sections' => nil, 'cellClasses' => ['ACell'], 'layout' => 'flow' },
    'pager' => { 'layout' => 'horizontal', 'paging' => true },
    'pagerOneSection' => { 'layout' => 'horizontal', 'paging' => true, 'sections' => [{ 'cell' => 'ACell' }] },
    'classListPager' => { 'sections' => nil, 'cellClasses' => ['ACell'], 'layout' => 'horizontal', 'paging' => true }
  }.freeze
  SIZE_PAGER_ROUTES = %w[pager pagerOneSection classListPager].freeze
  SIZE_SECTIONS = [{ 'cell' => 'ACell' }, { 'cell' => 'BCell' }].freeze
  SIZE_BOX = 'Box(modifier = Modifier.width(157.dp).height(63.dp).clipToBounds()) {'

  def emit(extra, size)
    %i[info debug warn].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    node = { 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'sections' => SIZE_SECTIONS }.merge(extra)
    node = node.merge('cellWidth' => 157, 'cellHeight' => 63) if size
    ComposeBoundedScrollStubs.unqualify(KjuiTools::Compose::Components::CollectionComponent.generate(node.compact, 1, Set.new, nil))
  end

  it 'every route draws each cell in the declared size box, the cell view the box\'s only child' do
    SIZE_ROUTES.each do |route, extra|
      code = emit(extra, true)
      views = code.scan(/^\s*[AB]CellView\($/).size
      expect(views).to be > 0, route
      expect(code.scan(SIZE_BOX).size).to eq(views), "#{route}:\n#{code}"
      code.scan(/#{Regexp.escape(SIZE_BOX)}\n\s*([AB]Cell)View\(/).each { |(cell)| expect(%w[ACell BCell]).to include(cell) }
      expect(code.scan(/#{Regexp.escape(SIZE_BOX)}\n\s*[AB]CellView\(/).size).to eq(views), "#{route}:\n#{code}"
    end
  end

  it 'a pager draws the box in the middle of its page, the page padding inside the page' do
    SIZE_PAGER_ROUTES.each do |route|
      code = emit(SIZE_ROUTES[route], true)
      views = code.scan(/^\s*[AB]CellView\($/).size
      page = /Box\(modifier = Modifier\.fillMaxSize\(\), contentAlignment = Alignment\.Center\) \{\n\s*#{Regexp.escape(SIZE_BOX)}\n\s*[AB]CellView\(/
      expect(code.scan(page).size).to eq(views), "#{route}:\n#{code}"
      expect(code).not_to include('.fillMaxSize()) {'), route
      expect(code).not_to match(/_item_\$page"\)\.fillMaxSize\(\)/), route
      padded = emit(SIZE_ROUTES[route].merge('insets' => [4, 8, 4, 8]), true)
      expect(padded).to include('Box(modifier = Modifier.fillMaxSize().padding(pagePadding), contentAlignment = Alignment.Center) {'), route
    end
  end

  it 'a pager with neither declared draws its cell filling the page, as it was' do
    SIZE_PAGER_ROUTES.each do |route|
      code = emit(SIZE_ROUTES[route], false)
      expect(code).to match(/_item_\$page"\)\.fillMaxSize\(\)/), route
      expect(code).not_to include('Alignment.Center'), route
    end
  end

  it 'only cellWidth, or only cellHeight: the box takes the one declared' do
    %w[lazyNone rowLazyNone flow pager].each do |route|
      %w[cellWidth cellHeight].each do |attr|
        node = { 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'sections' => SIZE_SECTIONS }
               .merge(SIZE_ROUTES[route]).merge(attr => 157).compact
        code = KjuiTools::Compose::Components::CollectionComponent.generate(node, 1, Set.new, nil)
        box = attr == 'cellWidth' ? 'Modifier.width(157.dp).clipToBounds()' : 'Modifier.height(157.dp).clipToBounds()'
        expect(code).to include("Box(modifier = #{box}) {"), "#{route} #{attr}"
      end
    end
  end

  it 'with neither declared, every route is as it was: no size box' do
    SIZE_ROUTES.each do |route, extra|
      expect(emit(extra, false)).not_to include('clipToBounds()) {'), route
    end
  end

  it 'records the import the box needs' do
    SIZE_ROUTES.each do |route, extra|
      imports = Set.new
      node = { 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'sections' => SIZE_SECTIONS,
               'cellWidth' => 157, 'cellHeight' => 63 }.merge(extra).compact
      KjuiTools::Compose::Components::CollectionComponent.generate(node, 1, imports, nil)
      expect(imports).to include(:shape), route
    end
  end

  SIZE_STUBS = <<~KOTLIN
    fun Modifier.width(value: Dp): Modifier = this
    fun Modifier.clipToBounds(): Modifier = this
  KOTLIN

  it 'every route compiles with allWarningsAsErrors' do
    expect(SIZE_STUBS + program(SIZE_ROUTES.transform_values { |extra| emit(extra, true) })).to compile_as_kotlin.with_warnings_as_errors
  end
end
