# frozen_string_literal: true

require 'swiftui/json_to_swiftui_converter'
require 'core/stage_failures'
require_relative '../support/emitted_swift'

# The viewId a handler is handed is the node's id, else its drawn type and its
# position — JsonUIShared::LayoutPath.view_id (`switch_0_1`, `selectBox_0_3`),
# the name every path gives it (4f's ruling on
# sjui-codegen-state-declarations-collide-by-name, 1.9.0). An id-less node's
# viewId was a per-kind word — `toggle`, `checkbox`, `segment`, `slider`,
# `selectBox`, `textField`, `textEditor`, `button`, `image`, or `""` for a
# View's tap — the same for every node of the kind, and not the word the
# Android paths use. Driven through the build's entry, the layout declaring
# handlers that take the viewId.
RSpec.describe 'sjui: an id-less node hands its handlers its position as the viewId' do
  include EmittedSwift

  let(:converter) { SjuiTools::SwiftUI::JsonToSwiftUIConverter.new }
  let(:dir) { Dir.mktmpdir('view_ids') }

  before { JsonUI::StageFailures.clear! }
  after { FileUtils.rm_rf(dir) }

  def convert(children)
    convert_all(children).first.to_s
  end

  def convert_all(children)
    data = [
      { 'name' => 'tap', 'class' => '((String) -> Void)?' },
      { 'name' => 'flip', 'class' => '((String, Bool) -> Void)?' },
      { 'name' => 'pick', 'class' => '((String, Int) -> Void)?' },
      { 'name' => 'move', 'class' => '((String, Double) -> Void)?' },
      { 'name' => 'typed', 'class' => '((String, String) -> Void)?' },
      { 'name' => 'on', 'class' => 'Bool' }, { 'name' => 'idx', 'class' => 'Int' }, { 'name' => 'text', 'class' => 'String' }
    ]
    path = File.join(dir, 'probe.json')
    File.write(path, JSON.generate('type' => 'View', 'data' => data, 'child' => children))
    converter.convert_json_to_view(path)
  end

  {
    'Switch' => [{ 'type' => 'Switch', 'isOn' => '@{on}', 'onValueChange' => '@{flip}' }, 'data.flip?("switch_0_1", newValue)'],
    'Toggle (an alias of Switch)' => [{ 'type' => 'Toggle', 'isOn' => '@{on}', 'onValueChange' => '@{flip}' }, 'data.flip?("switch_0_1", newValue)'],
    'CheckBox' => [{ 'type' => 'CheckBox', 'label' => 'x', 'onValueChange' => '@{flip}' }, 'data.flip?("checkBox_0_1", newValue)'],
    'Segment' => [{ 'type' => 'Segment', 'items' => %w[a b], 'selectedIndex' => '@{idx}', 'onValueChange' => '@{pick}' }, 'data.pick?("segment_0_1", newValue)'],
    'Slider' => [{ 'type' => 'Slider', 'onValueChange' => '@{move}' }, 'data.move?("slider_0_1", newValue)'],
    'SelectBox' => [{ 'type' => 'SelectBox', 'items' => %w[a b], 'selectedIndex' => '@{idx}', 'onValueChange' => '@{pick}' }, 'data.pick?("selectBox_0_1", data.idx)'],
    'TextField' => [{ 'type' => 'TextField', 'text' => '@{text}', 'onTextChange' => '@{typed}' }, 'data.typed?("textField_0_1", newValue)'],
    'EditText (an alias of TextField)' => [{ 'type' => 'EditText', 'text' => '@{text}', 'onTextChange' => '@{typed}' }, 'data.typed?("textField_0_1", newValue)'],
    'TextView' => [{ 'type' => 'TextView', 'text' => '@{text}', 'onTextChange' => '@{typed}' }, 'data.typed?("textView_0_1", newValue)'],
    'Button' => [{ 'type' => 'Button', 'text' => 'Go', 'onClick' => '@{tap}' }, 'data.tap?("button_0_1")']
    # Not here: a View's or an Image's plain tap, which calls its handler with
    # no argument whatever the handler takes (build_on_click_lines) — it hands
    # no viewId to change. Reported, not changed.
  }.each do |kind, (node, call)|
    it "#{kind}: its position, and an explicit id as it is" do
      # Second child: position 0_1 (a Label first, at 0_0).
      code = convert([{ 'type' => 'Label', 'text' => 'first' }, node])
      expect(code).to include(call)
      named = convert([{ 'type' => 'Label', 'text' => 'first' }, node.merge('id' => 'mine')])
      expect(named).to include(call.sub(/"[a-zA-Z]+_0_1"/, '"mine"'))
    end
  end

  # The calls, with their viewIds, type-checked over the handlers' declared
  # types — the kinds SwiftUI draws alone (CheckBox, SelectBox and TextView
  # draw SwiftJsonUI views, not on this machine's search path; so does
  # Button, StateAwareButtonView).
  it 'compiles: the kinds SwiftUI draws alone, every one id-less' do
    code, _actions, declarations = convert_all([
      { 'type' => 'Switch', 'isOn' => '@{on}', 'onValueChange' => '@{flip}' },
      { 'type' => 'Toggle', 'onValueChange' => '@{flip}' },
      { 'type' => 'Segment', 'items' => %w[a b], 'selectedIndex' => '@{idx}', 'onValueChange' => '@{pick}' },
      { 'type' => 'Slider', 'onValueChange' => '@{move}' },
      { 'type' => 'TextField', 'text' => '@{text}', 'onTextChange' => '@{typed}' },
      { 'type' => 'EditText', 'text' => '@{text}', 'onTextChange' => '@{typed}' }
    ])
    expect(code.to_s).to include('"switch_0_0"', '"switch_0_1"', '"segment_0_2"', '"slider_0_3"', '"textField_0_4"', '"textField_0_5"')
    body = code.to_s.lines.map { |l| "        #{l}" }.join
    swift = <<~SWIFT
      #{EmittedSwift::LIBRARY_STUBS}
      struct TestData {
          var tap: ((String) -> Void)? = nil
          var flip: ((String, Bool) -> Void)? = nil
          var pick: ((String, Int) -> Void)? = nil
          var move: ((String, Double) -> Void)? = nil
          var typed: ((String, String) -> Void)? = nil
          var on: Bool = false
          var idx: Int = 0
          var text: String = ""
      }
      struct EmittedHost: View {
          @Binding var data: TestData
      #{declarations.map { |d| "    #{d}" }.join("\n")}
          var body: some View {
      #{body}
          }
      }
    SWIFT
    expect(swift).to compile_as_swift.with_imports('SwiftUI')
  end

  it 'a SelectBox is its viewId to SelectBoxView too' do
    expect(convert([{ 'type' => 'SelectBox', 'items' => %w[a b] }])).to include('id: "selectBox_0_0",')
  end
end
