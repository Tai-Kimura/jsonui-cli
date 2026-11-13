# frozen_string_literal: true

require 'set'
require 'tmpdir'
require 'json'
require 'swiftui/views/collection_converter'
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'
require_relative '../../../lib/swiftui/reorder_handle_index'

# A reorderable Collection in sjui's codegen (ticket jui-collection-drag-to-reorder, ruling B 2026-11-13): the vertical
# single-column routes with sections draw SwiftJsonUI's CollectionReorder — CollectionReorderRows in place of each
# section's ForEach (.list in a List, .stack elsewhere), the stack as the container (CollectionStackView's `reorder:`,
# .collectionReorderContainer on the lazy-none VStack) — and the reorderHandle is marked in the cell's own file
# (ReorderHandleIndex). No #available in the emitted code: the OS version's fork is the library's.
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  include EmittedSwift

  before(:all) { described_class.superclass.validation_enabled = false }
  after(:all) { described_class.superclass.validation_enabled = true }
  after do
    base = SjuiTools::SwiftUI::Views::BaseViewConverter
    base.reorder_handle_ids = Set.new if base.respond_to?(:reorder_handle_ids=)
  end

  def emit(extra)
    described_class.new({ 'type' => 'Collection', 'id' => 'stop_list', 'width' => 'matchParent', 'items' => '@{rows}',
                          'sections' => [{ 'cell' => 'ACell' }] }.merge(extra).compact).convert.to_s
  end

  SJUI_REORDER_DECL = { 'reorderable' => '@{editing}', 'onReorder' => '@{onStopMove}' }.freeze
  SJUI_REORDER_ROUTES = {
    'lazy none' => [{ 'lazy' => 'none' }, :stack], 'stack' => [{ 'height' => 400 }, :stack],
    'List' => [{ 'height' => 400, 'listStyle' => 'plain' }, :list]
  }.freeze

  it 'without the declaration the emitted code is the route as it was (no reorder, false, or no handler)' do
    SJUI_REORDER_ROUTES.each do |route, (extra, _)|
      plain = emit(extra)
      expect(plain).not_to include('Reorder'), route
      [{ 'reorderable' => false, 'onReorder' => '@{onStopMove}' }, { 'reorderable' => true }].each do |half|
        expect(emit(extra.merge(half))).to eq(plain), "#{route} #{half}"
      end
    end
  end

  it "each route draws the section's rows through CollectionReorderRows, in its style" do
    SJUI_REORDER_ROUTES.each do |route, (extra, style)|
      code = emit(extra.merge(SJUI_REORDER_DECL))
      expect(code).to include('CollectionReorderRows(section: 0, ids: cellsData.enumerated().map { index, data in'), route
      expect(code).to include("style: .#{style}) { index in"), route
      expect(code).to include('reorder: CollectionReorder(isEnabled: data.editing == true, usesHandle: false, hasLockedRows: false, ' \
                              'onReorder: { section, from, to in data.onStopMove?(section, from, to) })'), route
      expect(code).to include('.accessibilityIdentifier("stop_list_item_\\(index)")'), route
      expect(code).not_to include('#available'), route
      expect(code).not_to include('ForEach('), route
    end
  end

  it 'the container: CollectionReorder on the CollectionStackView, on the lazy-none VStack; none on a List' do
    expect(emit({ 'height' => 400 }.merge(SJUI_REORDER_DECL))).to match(/CollectionStackView\(\n(.*\n)*?\s*reorder: CollectionReorder\(/)
    expect(emit({ 'lazy' => 'none' }.merge(SJUI_REORDER_DECL))).to include('.collectionReorderContainer(CollectionReorder(')
    list = emit({ 'height' => 400, 'listStyle' => 'plain' }.merge(SJUI_REORDER_DECL))
    expect(list).not_to include('collectionReorderContainer')
    expect(list).not_to include('CollectionStackView(')
  end

  it 'a literal reorderable, a handle and the locked rows' do
    code = emit({ 'lazy' => 'none', 'reorderable' => true, 'onReorder' => '@{onStopMove}', 'reorderHandle' => 'grip',
                  'reorderLockedProperty' => 'fixed', 'cellIdProperty' => 'id' })
    expect(code).to include('CollectionReorder(isEnabled: true, usesHandle: true, hasLockedRows: true,')
    expect(code).to include('locked: Set(cellsData.indices.filter { (cellsData[$0]["fixed"] as? Bool) == true })')
  end

  it 'a Collection with locked rows says so to CollectionReorder (the library keeps its own drag on iOS 27 for it)' do
    SJUI_REORDER_ROUTES.each do |route, (extra, _style)|
      locked = emit(extra.merge(SJUI_REORDER_DECL).merge('reorderLockedProperty' => 'fixed'))
      expect(locked).to include('hasLockedRows: true, onReorder:'), route
      expect(emit(extra.merge(SJUI_REORDER_DECL))).to include('hasLockedRows: false, onReorder:'), route
      expect(emit(extra.merge(SJUI_REORDER_DECL).merge('reorderLockedProperty' => ''))).to include('hasLockedRows: false,'), route
    end
  end

  it 'a horizontal or grid Collection does not reorder (v1)' do
    [{ 'layout' => 'horizontal', 'height' => 40 }, { 'columns' => 2 }].each do |extra|
      expect(emit(extra.merge(SJUI_REORDER_DECL))).not_to include('CollectionReorderRows'), extra.to_s
    end
  end

  # The class-list shape (no sections): each data section a reorderable section of its own, as SwiftJsonUI's Dynamic
  # draws it — the lazy-none VStack (.stack, the container on it) and the List (.list, none).
  SJUI_REORDER_LEGACY = { 'sections' => nil, 'cellClasses' => ['ACell'] }.freeze

  it 'the class-list shape reorders too: the lazy-none VStack and the List' do
    none = emit(SJUI_REORDER_LEGACY.merge('lazy' => 'none').merge(SJUI_REORDER_DECL))
    expect(none).to include('CollectionReorderRows(section: sectionIndex,')
    expect(none).to include('style: .stack) { index in')
    expect(none).to include('.collectionReorderContainer(CollectionReorder(')
    list = emit(SJUI_REORDER_LEGACY.merge('height' => 400).merge(SJUI_REORDER_DECL))
    expect(list).to include('CollectionReorderRows(section: sectionIndex,')
    expect(list).to include('style: .list) { index in')
    expect(list).not_to include('collectionReorderContainer')
    [none, list].each { |code| expect(code).not_to include('ForEach(Array(cellsData') }
  end

  it 'ReorderHandleIndex maps each cell layout of a reorderable Collection to its handle id' do
    Dir.mktmpdir do |dir|
      File.write(File.join(dir, 'visit.json'), JSON.generate(
        { 'type' => 'View', 'child' => [
          { 'type' => 'Collection', 'reorderable' => true, 'onReorder' => '@{onMove}', 'reorderHandle' => 'grip',
            'sections' => [{ 'cell' => 'visit/stop_cell' }] },
          { 'type' => 'Collection', 'reorderHandle' => 'grip', 'sections' => [{ 'cell' => 'other_cell' }] }
        ] }
      ))
      expect(SjuiTools::SwiftUI::ReorderHandleIndex.build(dir)).to eq({ 'stop_cell' => Set['grip'] })
    end
  end

  it "the handle's element takes .collectionReorderHandle() after its identifier; other elements nothing" do
    SjuiTools::SwiftUI::Views::BaseViewConverter.reorder_handle_ids = Set['grip']
    factory = SjuiTools::SwiftUI::ConverterFactory.new
    grip = factory.create_converter({ 'type' => 'View', 'id' => 'grip', 'width' => 40, 'height' => 40 }, 0).convert.to_s
    other = factory.create_converter({ 'type' => 'View', 'id' => 'title', 'width' => 40, 'height' => 40 }, 0).convert.to_s
    expect(grip).to include('.collectionReorderHandle()')
    expect(grip.index('.collectionReorderHandle()')).to be > grip.index('.accessibilityIdentifier("grip")')
    expect(other).not_to include('.collectionReorderHandle()')
  end

  it 'type-checks on every route against the library declarations', :swift_compile do
    stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + EmittedSwift::COLLECTION_STACK_VIEW_STUB + cell_view_stub('ACellView') + <<~SWIFT
      // SwiftJsonUI CollectionReorder.swift (feature/collection-reorder), the public declarations.
      enum CollectionReorderStyle { case stack, list }
      struct CollectionReorderRows<Content: View>: View {
          let content: (Int) -> Content
          init(section: Int, ids: [String], locked: Set<Int> = [], reorder: CollectionReorder?,
               style: CollectionReorderStyle = .stack, @ViewBuilder content: @escaping (Int) -> Content) { self.content = content }
          var body: some View { content(0) }
      }
      extension View {
          func collectionReorderContainer(_ reorder: CollectionReorder?) -> some View { self }
          func collectionReorderHandle() -> some View { self }
      }
    SWIFT
    codes = SJUI_REORDER_ROUTES.values.map { |extra, _| emit(extra.merge(SJUI_REORDER_DECL)) } +
            [emit(SJUI_REORDER_LEGACY.merge('lazy' => 'none').merge(SJUI_REORDER_DECL)), emit(SJUI_REORDER_LEGACY.merge('height' => 400).merge(SJUI_REORDER_DECL))] +
            [emit({ 'lazy' => 'none', 'reorderable' => true, 'onReorder' => '@{onStopMove}', 'reorderHandle' => 'grip',
                    'reorderLockedProperty' => 'fixed', 'cellIdProperty' => 'id' })]
    data = ['var rows: CollectionDataSource? = nil', 'var editing: Bool = false', 'var onStopMove: ((Int, Int, Int) -> Void)? = nil']
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}", data: data, stubs: stubs)).to compile_as_swift
  end
end
