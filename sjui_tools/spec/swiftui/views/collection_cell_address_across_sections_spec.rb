# frozen_string_literal: true

require 'swiftui/views/collection_converter'

# A cell's `<id>_item_<n>` counts across the drawn sections (ticket
# jui-collection-item-identifier-repeats-per-section, ruling a2;
# attribute_semantics idBox.collectionCellRoot): n is the cells of the
# sections before its own, then its index in its section — the n of
# scrollTo's Int and of a pager's page. Until 2.5.39 every route but the
# pager restarted n at 0 per section, so a Collection of two sections had
# two `_item_0` and a test could not reach the second section's rows.
#
# The first section's cells and a Collection of one section keep their ids.
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  before(:all) { described_class.superclass.validation_enabled = false }
  after(:all) { described_class.superclass.validation_enabled = true }

  def self.address_routes
    {
      'list' => {}, 'lazy:none' => { 'lazy' => 'none' }, 'grid' => { 'columns' => 2 },
      'grid, lazy:none' => { 'columns' => 2, 'lazy' => 'none' }, 'flow' => { 'layout' => 'flow' },
      'horizontal' => { 'orientation' => 'horizontal' },
      'horizontal, lazy:none' => { 'orientation' => 'horizontal', 'lazy' => 'none' },
      'cellIdProperty' => { 'cellIdProperty' => 'key' }, 'scrollTo' => { 'scrollTo' => '@{target}' }
    }
  end

  let(:sections) { [{ 'cell' => 'ACell' }, { 'header' => 'HCell' }, { 'cell' => 'BCell' }, { 'cell' => 'CCell' }] }
  let(:before_2) { '(dataSource.sections[0].cells?.data.count ?? 0)' }
  let(:before_3) { '(dataSource.sections[0].cells?.data.count ?? 0) + (dataSource.sections[2].cells?.data.count ?? 0)' }

  def convert(attrs)
    described_class.new({ 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}' }.merge(attrs)).convert.to_s
  end

  def identifiers(code)
    code.scan(/\.accessibilityIdentifier\("list_item_\\\((.*)\)"\)/).flatten
  end

  address_routes.each do |route, extra|
    it "#{route}: a later section's n adds the drawn sections' cells before it" do
      code = convert({ 'sections' => sections }.merge(extra))
      ids = identifiers(code)
      expect(ids.length).to eq(3)
      expect(ids[0]).to match(/\A(cellIndex|cell\.index)\z/)
      expect(ids[1]).to eq('sectionStart + cell.index')
      expect(ids[2]).to eq('sectionStart + cell.index')
      expect(code).to include("let sectionStart = #{before_2}\n")
      expect(code).to include("let sectionStart = #{before_3}\n")
    end
  end

  it 'a pager already counted every page (control: unchanged)' do
    code = convert('sections' => sections, 'orientation' => 'horizontal', 'paging' => true)
    expect(identifiers(code)).to eq(%w[cellIndex cell.index cell.index])
    expect(code).to include("let pageStart = #{before_2}\n", "let pageStart = #{before_3}\n")
    expect(code).not_to include('sectionStart')
  end

  it 'reorderable rows count the sections before theirs' do
    code = convert('sections' => sections, 'reorderable' => true, 'onReorder' => '@{onMove}')
    expect(identifiers(code)).to eq(['index', "(#{before_2}) + index", "(#{before_3}) + index"])
  end

  it 'the class list adds the data sections before the running one at run time' do
    before = 'dataSource.sections.prefix(sectionIndex).reduce(0) { $0 + ($1.cells?.data.count ?? 0) }'
    expect(identifiers(convert('cellClasses' => ['ACell']))).to eq(["#{before} + cellIndex"])
    reorder = convert('cellClasses' => ['ACell'], 'reorderable' => true, 'onReorder' => '@{onMove}')
    expect(identifiers(reorder)).to eq(["(#{before}) + index"])
  end

  it 'a Collection of one section keeps its ids (control)' do
    code = convert('sections' => [{ 'cell' => 'ACell' }])
    expect(identifiers(code)).to eq(['cellIndex'])
    expect(code).not_to include('sectionStart')
  end

  it 'with no id nothing is counted (no sectionStart is emitted for an address)' do
    code = described_class.new({ 'type' => 'Collection', 'items' => '@{rows}', 'sections' => sections }).convert.to_s
    expect(code).not_to include('accessibilityIdentifier')
    expect(code).not_to include('sectionStart')
  end

  # The emitted Swift compiles: the address reads the data the section
  # routes bind (`dataSource`), inside a string interpolation. The flow
  # route's FlowLayout has no stub here; its address is the same line.
  it 'compiles on every section route but the flow, and the class list' do
    stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + EmittedSwift::COLLECTION_STACK_VIEW_STUB + cell_view_stub('ACellView', 'BCellView', 'CCellView', 'HCellView')
    codes = self.class.address_routes.except('scrollTo', 'flow').values.map { |extra| convert({ 'sections' => sections }.merge(extra)) }
    codes << convert('cellClasses' => ['ACell'])
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}", data: ['var rows: CollectionDataSource? = nil'], stubs: stubs))
      .to compile_as_swift
  end
end
