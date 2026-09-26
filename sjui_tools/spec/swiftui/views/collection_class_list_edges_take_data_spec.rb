# frozen_string_literal: true

require 'swiftui/views/collection_converter'
require 'swiftui/generators/collection_generator'

# A class-list Collection's header and footer (headerClasses / footerClasses)
# are cell views — `sjui g collection` writes them, and their one initializer
# is `init(data: Any)`. They are drawn once, with no data of their own, and
# called as every cell and section header is: `View(data: [String: Any]())`
# (4f round 9). Until jsonui-cli 1.9.0 they were called `View()`, which does
# not compile against that initializer: the specs stubbed them with a
# no-argument initializer, the shape the emit assumed.
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  before(:all) { described_class.superclass.validation_enabled = false }
  after(:all) { described_class.superclass.validation_enabled = true }

  # Every route that draws a class-list header or footer.
  def class_list_edge_routes
    {
      'the List' => {},
      'the List, a footer alone' => { 'headerClasses' => nil },
      'the lazy grid' => { 'columns' => 2 },
      'the non-lazy column' => { 'lazy' => 'none' },
      'the non-lazy grid' => { 'lazy' => 'none', 'columns' => 2 }
    }
  end

  def convert(extra)
    described_class.new({
      'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}',
      'cellClasses' => ['ACell'], 'headerClasses' => ['HeadCell'], 'footerClasses' => ['FootCell']
    }.merge(extra).compact).convert.to_s
  end

  it "the stub's initializer is the one `sjui g collection` writes" do
    generator = SjuiTools::SwiftUI::Generators::CollectionGenerator.allocate
    generator.instance_variable_set(:@pascal_name, 'HeadCell')
    generator.instance_variable_set(:@name, 'head_cell')
    view = generator.send(:view_file_content)
    expect(view.scan(/^\s*init\((.*?)\)/).flatten).to eq(['data: Any'])
  end

  it 'on every route the header and footer are called with data' do
    class_list_edge_routes.each do |route, extra|
      code = convert(extra)
      expect(code).to include('FootCellView(data: [String: Any]())'), route
      expect(code).to include('HeadCellView(data: [String: Any]())'), route unless extra.key?('headerClasses')
      expect(code).not_to match(/(Head|Foot)CellView\(\)/), route
    end
  end

  it 'type-checks against views whose one initializer takes data', :swift_compile do
    stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + cell_view_stub('ACellView', 'HeadCellView', 'FootCellView')
    codes = class_list_edge_routes.values.map { |extra| convert(extra) }
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}", data: ['var rows: CollectionDataSource? = nil'], stubs: stubs))
      .to compile_as_swift
  end
end
