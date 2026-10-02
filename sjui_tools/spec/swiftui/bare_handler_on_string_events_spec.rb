# frozen_string_literal: true

require 'swiftui/json_to_swiftui_converter'
require 'swiftui/views/collection_converter'
require 'json'
require 'tmpdir'
require_relative '../support/emitted_swift'

# An event attribute the SSoT declares with a "string" type takes the bare
# name as a declared form (attribute_definitions: TextField / TextView
# onTextChange, Collection onItemAppear and onValueChange — onPageChanged is
# its alias — and TabView onValueChange). Until jsonui-cli 1.9.6 the
# generator read the binding form only and dropped a bare name with no
# report, so "onPageChanged": "onPage" built and never called onPage (ticket
# bare-event-handler-is-dropped-without-a-warning). The bare name now emits
# what the binding emits, byte for byte — so it compiles where the binding
# does; the pager's, the ticket's case, is type-checked below.
RSpec.describe 'a bare handler name on an event the SSoT declares with a string type' do
  include EmittedSwift
  def swift(node)
    Dir.mktmpdir('sjui_bare') do |dir|
      path = File.join(dir, 'probe.json')
      File.write(path, JSON.generate({ 'type' => 'View', 'id' => 'root', 'child' => [
        { 'data' => [{ 'name' => 'h', 'class' => '(Int) -> Void' }, { 'name' => 'rows', 'class' => 'CollectionDataSource' },
                     { 'name' => 't', 'class' => 'String', 'defaultValue' => '' }] }, node
      ] }))
      SjuiTools::SwiftUI::JsonToSwiftUIConverter.new.convert_json_to_view(path).first.to_s
    end
  end

  def self.shapes
    {
    'TextField.onTextChange' => { 'type' => 'TextField', 'id' => 'tf', 'text' => '@{t}' },
    'TextView.onTextChange' => { 'type' => 'TextView', 'id' => 'tv', 'text' => '@{t}' },
    'Collection.onItemAppear' => { 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'sections' => [{ 'cell' => 'ACell' }] },
    'Collection.onPageChanged' => { 'type' => 'Collection', 'id' => 'pager', 'items' => '@{rows}', 'layout' => 'horizontal', 'paging' => true,
                                    'sections' => [{ 'cell' => 'ACell' }] },
    'TabView.onValueChange' => { 'type' => 'TabView', 'id' => 'tabs', 'tabs' => [{ 'title' => 'a', 'view' => 'a_view' }] }
    }
  end

  shapes.each do |name, node|
    attr = name.split('.').last
    it "#{name}: the bare name emits what the binding emits, and calls the handler" do
      bound = swift(node.merge(attr => '@{h}'))
      expect(bound).to match(/data\.h\?\(/)
      expect(swift(node.merge(attr => 'h'))).to eq(bound)
    end
  end

  it 'control: no handler, or a value that is not a name, emits no call' do
    self.class.shapes.each do |name, node|
      attr = name.split('.').last
      [nil, '', 'not a name', 'h()'].each do |value|
        code = swift(value.nil? ? node : node.merge(attr => value))
        expect(code).not_to match(/data\.h\?\(/), "#{name} = #{value.inspect}"
      end
    end
  end

  it 'type-checks the pager with a bare onPageChanged and no currentPage', :swift_compile do
    converter_class = SjuiTools::SwiftUI::Views::CollectionConverter
    converter_class.superclass.validation_enabled = false
    SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = { 'onPage' => { 'class' => '(Int) -> Void' } }
    node = self.class.shapes['Collection.onPageChanged'].merge('onPageChanged' => 'onPage')
    converter = converter_class.new(node, 0, nil, nil, [{ 'name' => 'rows', 'class' => 'CollectionDataSource' }])
    code = converter.convert.to_s
    expect(code).to include('data.onPage?(newValue)')
    # `.page(indexDisplayMode:)` is iOS only and this check type-checks for
    # the host (collection_scroll_routes_spec.rb sets it aside the same way).
    code = code.lines.reject { |l| l.include?('.tabViewStyle(.page(') }.join
    view = <<~SWIFT
      struct BareHostData { var rows: CollectionDataSource? = nil; var onPage: ((Int) -> Void)? = nil }
      struct BareHost: View {
          @State var data = BareHostData()
      #{converter.state_variables.map { |l| "    #{l}" }.join("\n")}
          var body: some View {
      #{code.lines.map { |l| "        #{l}" }.join}
          }
      }
    SWIFT
    stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + cell_view_stub('ACellView')
    expect("#{EmittedSwift::LIBRARY_STUBS}\n#{stubs}\n#{view}").to compile_as_swift
  ensure
    SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {}
    SjuiTools::SwiftUI::Views::CollectionConverter.superclass.validation_enabled = true
  end
end
