# frozen_string_literal: true

require 'swiftui/converter_factory'
require 'swiftui/views/view_converter'
require 'swiftui/views/selectbox_converter'
require 'swiftui/view_registry'
require_relative '../../support/emitted_swift'

# What a SelectBox's onValueChange is handed, by the parameters the data
# declares for it (4f's ruling on control-onclick-is-called-differently-on-
# every-path, 1.9.0): one String — the picked item, even with selectedIndex
# bound; a String then an Int — the viewId and the index; two Strings — the
# viewId and the item. The index is the bound selectedIndex, else the item's
# place in `items`; the viewId is the id, else JsonUIShared::LayoutPath.view_id.
#
# Before, `((String) -> Void)?` took the generic reading, whose `(String`
# pattern is the viewId's: it was handed the viewId and the value — two
# arguments to a one-argument closure, which does not compile; and a
# `((String, Int) -> Void)?` without a bound selectedIndex was handed the
# item for its Int.
RSpec.describe 'sjui SelectBox: onValueChange is handed what its declared parameters ask for' do
  include EmittedSwift

  HANDLERS = {
    '(String)' => ['pickItem', '((String) -> Void)?'],
    '(String, Int)' => ['pickIndex', '((String, Int) -> Void)?'],
    '(String, String)' => ['pickNamed', '((String, String) -> Void)?'],
    '(Int)' => ['pickAt', '((Int) -> Void)?']
  }.freeze

  BINDINGS = {
    'item bound' => { 'selectedItem' => '@{sel}' },
    'index bound' => { 'selectedIndex' => '@{idx}' },
    'nothing bound' => {}
  }.freeze

  EXPECTED = {
    ['(String)', 'item bound'] => 'data.pickItem?(newValue)',
    ['(String)', 'index bound'] => 'data.pickItem?(newValue)',
    ['(String)', 'nothing bound'] => 'data.pickItem?(newValue)',
    ['(String, Int)', 'item bound'] => 'data.pickIndex?("box", (["a", "b"].firstIndex(of: newValue) ?? -1))',
    ['(String, Int)', 'index bound'] => 'data.pickIndex?("box", data.idx)',
    ['(String, Int)', 'nothing bound'] => 'data.pickIndex?("box", (["a", "b"].firstIndex(of: newValue) ?? -1))',
    ['(String, String)', 'item bound'] => 'data.pickNamed?("box", newValue)',
    ['(String, String)', 'index bound'] => 'data.pickNamed?("box", newValue)',
    ['(String, String)', 'nothing bound'] => 'data.pickNamed?("box", newValue)'
  }.freeze

  before do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
    SjuiTools::SwiftUI::Views::ColorHelper.data_definitions =
      HANDLERS.values.to_h { |name, klass| [name, { 'name' => name, 'class' => klass }] }
  end

  after do
    SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {}
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  def emit(handler, attrs, id: 'box')
    node = { 'type' => 'SelectBox', 'items' => %w[a b], 'onValueChange' => "@{#{handler}}" }.merge(attrs)
    node['id'] = id if id
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter(node).convert.to_s
  end

  # The closure SelectBoxView calls, one line or several.
  def closure(code)
    code[/onValueChange: \{ newValue in(.*?)\n?\s*\}(?:,|\n\))/m, 1].strip
  end

  EXPECTED.each do |(declared, bound), call|
    it "#{declared}, #{bound}: #{call}" do
      expect(closure(emit(HANDLERS[declared].first, BINDINGS[bound]))).to eq(call)
    end
  end

  it 'an id-less SelectBox hands its position as the viewId' do
    expect(closure(emit('pickIndex', BINDINGS['index bound'], id: nil))).to eq('data.pickIndex?("selectBox_0", data.idx)')
    expect(closure(emit('pickNamed', {}, id: nil))).to eq('data.pickNamed?("selectBox_0", newValue)')
  end

  # A declaration not in the ruling's list (an Event type) keeps the reading
  # it had: the viewId, then the bound index, else the item.
  it 'any other declaration keeps the generic reading' do
    SjuiTools::SwiftUI::Views::ColorHelper.data_definitions['picked'] = { 'name' => 'picked', 'class' => '((SelectEvent) -> Void)?' }
    expect(closure(emit('picked', BINDINGS['index bound']))).to eq('data.picked?("box", data.idx)')
    expect(closure(emit('picked', BINDINGS['item bound']))).to eq('data.picked?("box", newValue)')
    expect(closure(emit('picked', {}))).to eq('data.picked?("box", newValue)')
  end

  it 'a date picker hands its date string: alone, or after the viewId' do
    date = { 'selectItemType' => 'Date', 'selectedDate' => '@{day}' }
    expect(closure(emit('pickItem', date)).lines.map(&:strip)).to eq(['data.day = newValue', 'data.pickItem?(newValue)'])
    expect(closure(emit('pickNamed', date)).lines.map(&:strip)).to eq(['data.day = newValue', 'data.pickNamed?("box", newValue)'])
  end

  # A date has no index: a handler declared to take one is not called, and
  # the comment says why where the call would be (4f's ruling, 1.9.0). It was
  # handed the date string for its Int.
  it 'a date picker does not call a handler that takes an index' do
    date = { 'selectItemType' => 'Date', 'selectedDate' => '@{day}' }
    %w[pickIndex pickAt].each do |handler|
      expect(closure(emit(handler, date)).lines.map(&:strip)).to eq([
        'data.day = newValue',
        "// ERROR: SelectBox.onValueChange #{handler} is not called: a date SelectBox has no index: declare onValueChange as (String) or (String, String)"
      ])
    end
    expect(closure(emit('pickIndex', { 'selectItemType' => 'Date' }))).to start_with('// ERROR: SelectBox.onValueChange pickIndex is not called')
  end

  it 'a list picker hands an index-taking handler its index' do
    expect(closure(emit('pickAt', BINDINGS['index bound']))).to eq('data.pickAt?(data.idx)')
    expect(closure(emit('pickAt', {}))).to eq('data.pickAt?((["a", "b"].firstIndex(of: newValue) ?? -1))')
  end

  # Every closure above, type-checked as SelectBoxView's
  # `onValueChange: ((String) -> Void)?` (SwiftJsonUI SelectBoxView.swift)
  # over the declared handlers — SelectBoxView itself is not on this
  # machine's search path, so the closures are compiled, not the call.
  it 'compiles: every closure over the declared handlers' do
    closures = EXPECTED.keys.map { |declared, bound| closure(emit(HANDLERS[declared].first, BINDINGS[bound])) }
    closures += %w[pickItem pickNamed pickIndex pickAt].map { |h| closure(emit(h, { 'selectItemType' => 'Date', 'selectedDate' => '@{day}' })) }
    closures << closure(emit('pickIndex', { 'selectItemType' => 'Date' }))
    closures += [BINDINGS['index bound'], {}].map { |b| closure(emit('pickAt', b)) }
    lets = closures.each_with_index.map do |body, i|
      "        let c#{i}: (String) -> Void = { newValue in\n#{body.lines.map { |l| "            #{l.strip}\n" }.join}        }\n        _ = c#{i}"
    end
    swift = <<~SWIFT
      #{EmittedSwift::LIBRARY_STUBS}
      struct TestData {
      #{HANDLERS.values.map { |name, klass| "    var #{name}: #{klass} = nil" }.join("\n")}
          var sel: String? = nil
          var idx: Int = 0
          var day: String = ""
      }
      struct EmittedHost {
          @Binding var data: TestData
          func closures() {
      #{lets.join("\n")}
          }
      }
    SWIFT
    expect(swift).to compile_as_swift.with_imports('SwiftUI')
  end
end

# An enum value is its declared spelling, case and all (1.9.0): a spelling
# declared in no case is drawn as no declared value is — the default — on
# every path, as the validator names it. The two values the ruling names:
# View.orientation declares `horizontal`, SelectBox.selectItemType `Date`.
RSpec.describe 'sjui: an enum value is its declared spelling, case and all' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def view(orientation)
    kids = [{ 'type' => 'Label', 'text' => 'a' }, { 'type' => 'Label', 'text' => 'b' }]
    SjuiTools::SwiftUI::Views::ViewConverter.new('type' => 'View', 'orientation' => orientation, 'child' => kids).convert
  end

  def select_box(item_type)
    SjuiTools::SwiftUI::Views::SelectBoxConverter.new('type' => 'SelectBox', 'selectItemType' => item_type).convert
  end

  it "orientation: 'horizontal' lays the children out in a row; 'Horizontal' does not" do
    expect(view('horizontal')).to include('HStack(')
    expect(view('Horizontal')).not_to include('HStack(')
  end

  it "selectItemType: 'Date' is a date picker; 'date' is not" do
    expect(select_box('Date')).to include('selectItemType: .date')
    expect(select_box('date')).not_to include('selectItemType: .date')
  end
end
