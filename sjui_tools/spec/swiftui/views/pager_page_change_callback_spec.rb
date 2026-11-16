# frozen_string_literal: true

require 'swiftui/views/collection_converter'
require_relative '../../support/emitted_swift'

# A paging Collection's page-change callback (onValueChange, aliases
# onValueChanged / onPageChanged) is called with the page the TabView's
# selection turns to — the bound currentPage, else the pager's own page
# state — as KotlinJsonUI calls it from the pager whether or not a
# currentPage is bound, and SwiftJsonUI Dynamic from its internal page.
# Until jsonui-cli 1.9.6 sjui emitted it only with a currentPage binding:
# without one the TabView had no selection and the callback was dropped,
# with no warning (ticket
# sjui-pager-page-change-callback-requires-currentpage-binding).
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  include EmittedSwift

  before(:all) { described_class.superclass.validation_enabled = false }
  after(:all) { described_class.superclass.validation_enabled = true }

  before do
    SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = { 'onPage' => { 'class' => '(Int) -> Void' } }
  end
  after { SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {} }

  def emit(node)
    props = [{ 'name' => 'rows', 'class' => 'CollectionDataSource' }, { 'name' => 'target', 'class' => 'Int', 'defaultValue' => 0 }]
    paging = { 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'layout' => 'horizontal', 'paging' => true,
               'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell' }] }
    converter = described_class.new(paging.merge(node), 0, nil, nil, props)
    [converter.convert.to_s, converter.state_variables]
  end

  %w[onValueChange onValueChanged onPageChanged].each do |key|
    it "with no currentPage, #{key} is called from a page state of the pager's own" do
      code, state = emit(key => '@{onPage}')
      expect(state).to eq(['@State private var listScrollPage: Int = 0'])
      expect(code).to include('TabView(selection: $listScrollPage) {')
      expect(code).to include(".onChange(of: listScrollPage) { oldValue, newValue in\n")
      expect(code).to include('data.onPage?(newValue)')
    end
  end

  it 'with a bound currentPage it is called from the binding, with no state of its own' do
    code, state = emit('onPageChanged' => '@{onPage}', 'currentPage' => '@{page}')
    expect(state).to eq([])
    expect(code).to include('TabView(selection: $data.page) {')
    expect(code).to include('.onChange(of: data.page) { oldValue, newValue in')
    expect(code).to include('data.onPage?(newValue)')
  end

  # A bound currentPage outside the pages is clamped and written back; the
  # handler hears the clamped page (only when the shown page changes), never
  # the out-of-range value, and the write-back's own change is not a page
  # change (ticket sjui-dynamic-pager-does-not-write-back-a-clamped-page).
  it 'clamps a bound currentPage outside the pages, and tells the handler the clamped page' do
    code, = emit('onPageChanged' => '@{onPage}', 'currentPage' => '@{page}')
    expect(code).to include('let clamped = min(max(newValue, 0), lastPage)',
                            "if clamped != newValue {\n",
                            'data.page = clamped',
                            'if (0...lastPage).contains(oldValue) && oldValue != clamped { data.onPage?(clamped) }',
                            'guard (0...lastPage).contains(oldValue) else { return }')
    # No handler: the clamp still writes back; no currentPage: nothing to clamp.
    bare, = emit('currentPage' => '@{page}')
    expect(bare).to include('data.page = clamped')
    expect(bare).not_to include('onPage')
    own, = emit('onPageChanged' => '@{onPage}')
    expect(own).not_to include('clamped')
  end

  it 'a scrollTo and the callback share the one page state' do
    code, state = emit('onValueChange' => '@{onPage}', 'scrollTo' => '@{target}')
    expect(state).to eq(['@State private var listScrollPage: Int = 0'])
    expect(code).to include('withAnimation { listScrollPage = found }')
    expect(code).to include('.onChange(of: listScrollPage) { oldValue, newValue in')
  end

  it 'control: with neither a callback nor a scrollTo the TabView has no selection and calls nothing' do
    code, state = emit({})
    expect(state).to eq([])
    expect(code).to include('TabView {')
    expect(code).not_to include('onPage')
  end

  # The callback is declared ["string", "binding"]: a bare name is a declared
  # form, and from jsonui-cli 1.9.6 it is called as the binding is (ticket
  # bare-event-handler-is-dropped-without-a-warning; until then a bare name
  # was dropped, and this file's control said so).
  it 'a bare callback name emits what the binding emits' do
    expect(emit('onPageChanged' => 'onPage')).to eq(emit('onPageChanged' => '@{onPage}'))
  end

  it 'type-checks with and without a currentPage, and with a scrollTo', :swift_compile do
    stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + cell_view_stub('ACellView', 'BCellView')
    nodes = [{ 'onPageChanged' => '@{onPage}' }, { 'onPageChanged' => '@{onPage}', 'currentPage' => '@{page}' },
             { 'onValueChange' => '@{onPage}', 'scrollTo' => '@{target}' }]
    views = nodes.each_with_index.map do |node, i|
      code, state = emit(node.merge('id' => "list#{i}"))
      # `.page(indexDisplayMode:)` is iOS only and this check type-checks for
      # the host (collection_scroll_routes_spec.rb sets it aside the same way).
      code = code.lines.reject { |l| l.include?('.tabViewStyle(.page(') }.join
      <<~SWIFT
        struct PageHost#{i}Data {
            var rows: CollectionDataSource? = nil; var target: Int = 0; var page: Int = 0
            var onPage: ((Int) -> Void)? = nil
        }
        struct PageHost#{i}: View {
            @State var data = PageHost#{i}Data()
        #{state.map { |l| "    #{l}" }.join("\n")}
            var body: some View {
        #{code.lines.map { |l| "        #{l}" }.join}
            }
        }
      SWIFT
    end
    expect("#{EmittedSwift::LIBRARY_STUBS}\n#{stubs}\n#{views.join("\n")}").to compile_as_swift
  end
end
