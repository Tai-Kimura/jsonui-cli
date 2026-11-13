# frozen_string_literal: true

require 'set'
require 'tmpdir'
require 'json'
require_relative '../../../lib/compose/components/collection_component'
require_relative '../../../lib/compose/reorder_handle_index'
require_relative '../../../lib/compose/helpers/modifier_builder'
require_relative '../../support/collection_first_frame'

# A reorderable Collection in kjui's codegen (ticket jui-collection-drag-to-reorder, ruling B 2026-11-13): the vertical
# single-column routes draw KotlinJsonUI's CollectionReorder — the Collection is the container, each row a
# CollectionReorderRow, each cell's root takes the accessibility moves — and the reorderHandle is marked in the cell's
# own file (ReorderHandleIndex). The emitted code compiles and draws its cells as before: the reorder routes of
# collection_cell_first_frame_spec.rb.
RSpec.describe 'kjui codegen: a reorderable Collection' do
  before { %i[info debug warn].each { |m| allow(KjuiTools::Core::Logger).to receive(m) } }

  def emit(extra)
    node = { 'type' => 'Collection', 'id' => 'stop_list', 'width' => 'matchParent', 'items' => '@{rows}',
             'sections' => [{ 'cell' => 'stop_cell' }] }.merge(extra).compact
    imports = Set.new
    [KjuiTools::Compose::Components::CollectionComponent.generate(node, 1, imports, nil), imports]
  end

  KJUI_REORDER_DECL = { 'reorderable' => '@{editing}', 'onReorder' => '@{onStopMove}' }.freeze
  KJUI_REORDER_ROUTES = { 'lazy none' => { 'lazy' => 'none' }, 'list' => {}, 'wrapContent' => { 'height' => 'wrapContent' } }.freeze

  it 'without the declaration the emitted code is the route as it was (no reorder, false, or no handler)' do
    KJUI_REORDER_ROUTES.each do |route, extra|
      plain, = emit(extra)
      expect(plain).not_to include('Reorder'), route
      [{ 'reorderable' => false, 'onReorder' => '@{onStopMove}' }, { 'reorderable' => true }].each do |half|
        code, imports = emit(extra.merge(half))
        expect(code).to eq(plain), "#{route} #{half}"
        expect(imports).not_to include(:collection_reorder)
      end
    end
  end

  it 'each vertical single-column route opens the reorder: the state, the scope, the container, a row per cell' do
    KJUI_REORDER_ROUTES.each do |route, extra|
      code, imports = emit(extra.merge(KJUI_REORDER_DECL))
      expect(imports).to include(:collection_reorder), route
      expect(code).to include('val stopListReorder = rememberCollectionReorder('), route
      expect(code).to include('if (data.editing == true) CollectionReorder(true, false) { s, f, t -> data.onStopMove?.invoke(s, f, t) } else null,'), route
      expect(code).to include('CollectionReorderScope(stopListReorder) {'), route
      expect(code).to include('.collectionReorderContainer(stopListReorder)'), route
      expect(code).to match(/CollectionReorderRow\(stopListReorder, 0, cellIndex, [\w.]+\.size, reorderLocked0\) \{/), route
      expect(code).to include('.testTag("stop_list_item_$cellIndex").collectionReorderActions()'), route
      expect(code.scan('{').size).to eq(code.scan('}').size), route
    end
  end

  it 'the container scrolls itself unless an outer scroll carries it (lazy none)' do
    expect(emit({ 'lazy' => 'none' }.merge(KJUI_REORDER_DECL)).first).to include('scrollsItself = false,')
    expect(emit({ 'height' => 'wrapContent' }.merge(KJUI_REORDER_DECL)).first).to include('scrollsItself = true,')
    expect(emit(KJUI_REORDER_DECL).first).to match(/scrollsItself = .*CollectionStackMode\.\w+ != CollectionStackMode\.NONE,/)
  end

  it 'a literal reorderable is on, a handle declared is used, the locked rows are read from the cell data' do
    code, = emit({ 'lazy' => 'none', 'reorderable' => true, 'onReorder' => '@{onStopMove}', 'reorderHandle' => 'grip',
                   'reorderLockedProperty' => 'fixed', 'cellIdProperty' => 'id' })
    expect(code).to include('if (true) CollectionReorder(true, true) {')
    expect(code).to include('[it]["fixed"] == true }.toSet() }')
    expect(code).to include('key(sectionKeys[cellIndex]) { CollectionReorderRow(')
  end

  it 'a fixed row is read from the cell data and passed to its row; without the declaration the route is as it was' do
    base = { 'lazy' => 'none', 'reorderable' => true, 'onReorder' => '@{onStopMove}', 'cellIdProperty' => 'id' }
    KJUI_REORDER_ROUTES.each do |route, extra|
      plain, = emit(extra.merge(KJUI_REORDER_DECL))
      expect(plain).not_to include('Fixed'), route
      code, = emit(extra.merge(KJUI_REORDER_DECL).merge('reorderFixedProperty' => 'skipped'))
      expect(code).to include('[it]["skipped"] == true }.toSet() }'), route
      expect(code).to match(/CollectionReorderRow\(stopListReorder, 0, cellIndex, [\w.]+\.size, reorderLocked0, reorderLocked0Fixed\) \{/), route
      expect(code.sub(/\n[^\n]*reorderLocked0Fixed = remember[^\n]*/, '').gsub(', reorderLocked0Fixed', '')).to eq(plain), route
    end
    both, = emit(base.merge('reorderLockedProperty' => 'pinned', 'reorderFixedProperty' => 'skipped'))
    expect(both).to include('[it]["pinned"] == true }.toSet() }')
    expect(both).to include('[it]["skipped"] == true }.toSet() }')
  end

  it 'a horizontal or grid Collection does not reorder (v1)' do
    [{ 'layout' => 'horizontal' }, { 'columns' => 2 }].each do |extra|
      code, = emit(extra.merge(KJUI_REORDER_DECL))
      expect(code).not_to include('Reorder'), extra.to_s
    end
  end

  it 'the class-list shape (no sections) reorders too, each data section its own: the lazy-none Column and the grid' do
    legacy = { 'sections' => nil, 'cellClasses' => ['stop_cell'] }
    none, = emit(legacy.merge('lazy' => 'none').merge(KJUI_REORDER_DECL))
    lazy, = emit(legacy.merge('height' => 400).merge(KJUI_REORDER_DECL))
    [none, lazy].each do |code|
      expect(code).to include('CollectionReorderScope(stopListReorder) {')
      expect(code).to include('.collectionReorderContainer(stopListReorder)')
      expect(code).to match(/CollectionReorderRow\(stopListReorder, sectionIndex, cellIndex, [\w.]+\.size, reorderLocked\) \{/)
      expect(code).to include('.collectionReorderActions()')
      expect(code.scan('{').size).to eq(code.scan('}').size)
    end
    expect(none).to include('scrollsItself = false,')
    expect(lazy).to include('LazyVerticalGrid(')
  end

  describe 'compiled and run (the stub universe of spec/support/collection_first_frame.rb)' do
    include CollectionFirstFrame

    def frame_emit(extra)
      node = { 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}',
               'sections' => [{ 'cell' => 'ACell', 'header' => 'HCell', 'footer' => 'FCell' }, { 'cell' => 'BCell', 'header' => 'HCell' }] }
      ComposeBoundedScrollStubs.unqualify(KjuiTools::Compose::Components::CollectionComponent.generate(node.merge(extra).compact, 1, Set.new, nil))
    end

    it 'every reorderable route compiles and draws its cells with their data, as the route does without it' do
      routes = {
        'none' => { 'lazy' => 'none', 'cellIdProperty' => 'id' }, 'list' => {}, 'wrap' => { 'height' => 'wrapContent' },
        'classList' => { 'sections' => nil, 'cellClasses' => ['ACell'] }
      }
      functions = routes.flat_map do |name, extra|
        [["plain#{name.capitalize}", frame_emit(extra)],
         ["reorder#{name.capitalize}", frame_emit(extra.merge('reorderable' => '@{editing}', 'onReorder' => '@{onMove}', 'reorderLockedProperty' => 'fixed', 'reorderFixedProperty' => 'skipped'))]]
      end.to_h
      expect(program(functions)).to compile_as_kotlin
      frames = run(functions)
      routes.each_key do |name|
        expect(frames["reorder#{name.capitalize}"]).to eq(frames["plain#{name.capitalize}"]), name
        expect(frames["reorder#{name.capitalize}"]).to include('Aa0'), name
      end
    end
  end

  describe 'the handle, marked in the cell layout' do
    after { KjuiTools::Compose::Helpers::ModifierBuilder.reorder_handle_ids = Set.new }

    it 'ReorderHandleIndex maps each cell layout of a reorderable Collection to its handle id' do
      Dir.mktmpdir do |dir|
        File.write(File.join(dir, 'visit.json'), JSON.generate(
          { 'type' => 'View', 'child' => [
            { 'type' => 'Collection', 'id' => 'stops', 'reorderable' => true, 'onReorder' => '@{onMove}', 'reorderHandle' => 'grip',
              'sections' => [{ 'cell' => 'visit/stop_cell' }] },
            { 'type' => 'Collection', 'id' => 'plain', 'reorderHandle' => 'grip', 'sections' => [{ 'cell' => 'other_cell' }] }
          ] }
        ))
        index = KjuiTools::Compose::ReorderHandleIndex.build(dir)
        expect(index).to eq({ 'stop_cell' => Set['grip'] })
      end
    end

    it "the handle's element takes collectionReorderHandle, other elements nothing" do
      mb = KjuiTools::Compose::Helpers::ModifierBuilder
      mb.reorder_handle_ids = Set['grip']
      imports = Set.new
      expect(mb.build_test_tag({ 'id' => 'grip' }, imports)).to include('.collectionReorderHandle()')
      expect(imports).to include(:collection_reorder_handle)
      expect(mb.build_test_tag({ 'id' => 'title' }, Set.new)).not_to include('.collectionReorderHandle()')
      mb.reorder_handle_ids = Set.new
      expect(mb.build_test_tag({ 'id' => 'grip' }, Set.new)).not_to include('.collectionReorderHandle()')
    end
  end
end
