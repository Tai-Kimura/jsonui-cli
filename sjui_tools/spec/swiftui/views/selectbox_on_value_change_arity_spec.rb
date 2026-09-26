# frozen_string_literal: true

require 'swiftui/converter_factory'
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
    '(String, String)' => ['pickNamed', '((String, String) -> Void)?']
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

  # Every closure above, type-checked as SelectBoxView's
  # `onValueChange: ((String) -> Void)?` (SwiftJsonUI SelectBoxView.swift)
  # over the declared handlers — SelectBoxView itself is not on this
  # machine's search path, so the closures are compiled, not the call.
  it 'compiles: every closure over the declared handlers' do
    closures = EXPECTED.keys.map { |declared, bound| closure(emit(HANDLERS[declared].first, BINDINGS[bound])) }
    closures += %w[pickItem pickNamed].map { |h| closure(emit(h, { 'selectItemType' => 'Date', 'selectedDate' => '@{day}' })) }
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
