# frozen_string_literal: true

require 'json'
require 'swiftui/converter_factory'

# `items` is declared ["array", "binding"] on Collection (whose alias Table
# is) and on Radio. Each declared shape through the SwiftUI codegen.
#
# Until 1.9.0 (measured on 32785ce8, 2026-09-26) a Collection or Table
# given an array raised NoMethodError (`start_with?` on an Array) on each of
# the 12 routes that read it, and a Radio given a binding raised
# NoMethodError (`any?` on a String): the build went down on a declared
# shape. Ticket kjui-codegen-table-crashes-on-an-items-array.
RSpec.describe 'sjui codegen: each declared shape of `items`' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emit(node)
    %i[info debug warn].each { |m| allow(SjuiTools::Core::Logger).to receive(m) }
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter(JSON.parse(JSON.generate(node)), 0).convert.to_s
  end

  CELL = ['RowCell'].freeze
  ROUTES = [
    {}, { 'cellClasses' => CELL }, { 'cellClasses' => CELL, 'layout' => 'horizontal' },
    { 'cellClasses' => CELL, 'layout' => 'flow' }, { 'cellClasses' => CELL, 'layout' => 'horizontal', 'paging' => true },
    { 'cellClasses' => CELL, 'lazy' => 'none' }, { 'cellClasses' => CELL, 'lazy' => 'none', 'layout' => 'horizontal' },
    { 'cellClasses' => CELL, 'height' => 'wrapContent' }, { 'sections' => [{ 'cell' => 'RowCell' }] },
    { 'sections' => [{ 'cell' => 'RowCell', 'columns' => 2 }] }, { 'sections' => [{ 'cell' => 'RowCell' }], 'layout' => 'horizontal' },
    { 'sections' => [{ 'cell' => 'RowCell' }], 'lazy' => 'none' }, { 'sections' => [{ 'cell' => 'RowCell', 'header' => 'RowHeader' }] }
  ].freeze

  it 'sets an items array aside on every route of a Collection or a Table (a binding is what they draw from)' do
    aggregate_failures do
      %w[Collection Table].product(ROUTES).each do |type, route|
        base = { 'type' => type, 'id' => 'list', 'width' => 'matchParent', 'height' => 200 }.merge(route)
        expect(emit(base.merge('items' => %w[a b]))).to eq(emit(base)), "#{type} #{route}"
      end
    end
  end

  it 'draws a Radio with an items array as its options, and with a binding as the list the data holds; both typecheck' do
    array = emit('type' => 'Radio', 'id' => 'r', 'items' => %w[a b], 'selectedValue' => '@{sel}')
    bound = emit('type' => 'Radio', 'id' => 'r', 'items' => '@{rows}', 'selectedValue' => '@{sel}')
    expect(bound).to include('ForEach(data.rows, id: \.self) { item in').and include('data.sel == item')
    expect(bound.scan('HStack').size).to eq(1) # one option, drawn for each item
    expect(array.scan('HStack').size).to eq(2)
    hosts = [array, bound].each_with_index.map do |code, i|
      "struct RadioHost#{i}: View {\n    @State var data = RadioData()\n    var body: some View {\n#{code}\n    }\n}\n"
    end.join
    expect("struct RadioData { var rows: [String] = []; var sel: String = \"\" }\n#{hosts}").to compile_as_swift
  end
end
