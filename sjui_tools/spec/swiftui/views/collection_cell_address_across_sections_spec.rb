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
  def self.sum_of(indices)
    "[#{indices.join(', ')}].reduce(0) { (count: Int, index: Int) -> Int in count + (dataSource.sections[index].cells?.data.count ?? 0) }"
  end
  let(:before_2) { self.class.sum_of([0]) }
  let(:before_3) { self.class.sum_of([0, 2]) }
  let(:runtime_before) do
    'dataSource.sections.prefix(sectionIndex).reduce(0) { (count: Int, section: CollectionDataSection) -> Int in ' \
      'count + (section.cells?.data.count ?? 0) }'
  end

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
      expect(code).to include("let sectionStart: Int = #{before_2}\n")
      expect(code).to include("let sectionStart: Int = #{before_3}\n")
    end
  end

  it 'a pager already counted every page (control: unchanged)' do
    code = convert('sections' => sections, 'orientation' => 'horizontal', 'paging' => true)
    expect(identifiers(code)).to eq(%w[cellIndex cell.index cell.index])
    expect(code).to include("let pageStart: Int = #{before_2}\n", "let pageStart: Int = #{before_3}\n")
    expect(code).not_to include('sectionStart')
  end

  it 'reorderable rows count the sections before theirs' do
    code = convert('sections' => sections, 'reorderable' => true, 'onReorder' => '@{onMove}')
    expect(identifiers(code)).to eq(['index', 'cellsBefore + index', 'cellsBefore + index'])
    expect(code).to include("let cellsBefore: Int = #{before_2}\n", "let cellsBefore: Int = #{before_3}\n")
  end

  it 'the class list adds the data sections before the running one at run time' do
    plain = convert('cellClasses' => ['ACell'])
    expect(identifiers(plain)).to eq(['cellsBefore + cellIndex'])
    expect(plain).to include("let cellsBefore: Int = #{runtime_before}\n")
    reorder = convert('cellClasses' => ['ACell'], 'reorderable' => true, 'onReorder' => '@{onMove}')
    expect(identifiers(reorder)).to eq(['cellsBefore + index'])
    expect(reorder).to include("let cellsBefore: Int = #{runtime_before}\n")
  end

  # The 2.5.39 release-check: on the macos-15 Xcode, an untyped reduce
  # closure inside the identifier's string interpolation (in a ViewBuilder
  # ForEach) failed "unable to type-check this expression in reasonable time"
  # in 13 compile arms, while Xcode 27.2 compiled it. The shape is therefore
  # pinned on the generated text: the interpolation holds names and `+` only,
  # and every count it reads is a `let … : Int` whose closure is typed.
  it 'keeps every count out of the interpolation, in a typed let' do
    shapes = self.class.address_routes.values.map { |extra| { 'sections' => sections }.merge(extra) } +
             [{ 'sections' => sections, 'orientation' => 'horizontal', 'paging' => true },
              { 'sections' => sections, 'reorderable' => true, 'onReorder' => '@{onMove}' },
              { 'cellClasses' => ['ACell'] },
              { 'cellClasses' => ['ACell'], 'reorderable' => true, 'onReorder' => '@{onMove}' },
              { 'cellClasses' => ['ACell'], 'cellIdProperty' => 'key' }]
    shapes.each do |attrs|
      code = convert(attrs)
      ids = identifiers(code)
      expect(ids).not_to be_empty, attrs.inspect
      ids.each { |expr| expect(expr).to match(/\A[A-Za-z.]+( \+ [A-Za-z.]+)?\z/), "#{attrs.inspect}: #{expr}" }
      code.scan(/let (sectionStart|pageStart|cellsBefore)(:? ?[A-Za-z]*) = (.*)$/).each do |name, type, expr|
        expect(type).to eq(': Int'), "#{attrs.inspect}: #{name}"
        expect(expr.scan('??').size).to be <= 1, "#{attrs.inspect}: #{name} = #{expr}"
        expect(expr).not_to match(/\{ *\$0|\{ *[a-z]+ in/), "#{attrs.inspect}: #{name}'s closure is untyped"
      end
    end
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
