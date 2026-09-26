# frozen_string_literal: true

require 'swiftui/json_to_swiftui_converter'
require 'core/stage_failures'
require 'core/layout_path'
require_relative '../support/emitted_swift'

# A stateful node's view-local state is named by its `id`, else by its
# position in the layout — `<kind>_<path>` (shared/core/layout_path.rb,
# stamped on the include-expanded, style-merged tree the build converts) —
# and a name two nodes declare stops the layout's generation instead of
# folding into one state (ticket
# sjui-codegen-state-declarations-collide-by-name; 4f's ruling).
#
# Before, an id-less node was named by its kind alone (`toggleIsOn`,
# `selectedSegment`, `sliderValue`, …) and the view kept `.uniq` of whole
# lines: two id-less Switches with one seed shared one state (a tap on one
# flipped both), and with different seeds did not compile ("invalid
# redeclaration"); an id-less Radio's value was `radio`, so the id-less Radios
# of a group were one option; a group of single Radios declared its selection
# once per Radio, the checked one's seed beside the others' "", and did not
# compile. Measured end to end by SwiftJsonUI ConformanceHost
# StateNamesProbeUITests on both iOS paths.
RSpec.describe 'sjui: a node without an id is named by its position' do
  include EmittedSwift

  let(:converter) { SjuiTools::SwiftUI::JsonToSwiftUIConverter.new }
  let(:dir) { Dir.mktmpdir('state_names') }

  before { JsonUI::StageFailures.clear! }
  after { FileUtils.rm_rf(dir) }

  def convert(children, name: 'probe')
    path = File.join(dir, "#{name}.json")
    File.write(path, JSON.generate('type' => 'View', 'orientation' => 'vertical', 'child' => children))
    converter.convert_json_to_view(path)
  end

  def names(declarations)
    declarations.map { |line| line[/private var (\w+)/, 1] }
  end

  # Two id-less nodes of each kind, seeded alike (they shared one state) and
  # apart (they did not compile), and the names they must now take — the
  # kind and the position, the path's `_` kept.
  pairs = {
    'Switch' => [[{ 'type' => 'Switch', 'isOn' => false }, { 'type' => 'Switch', 'isOn' => true }], %w[toggle_0_0IsOn toggle_0_1IsOn]],
    'CheckBox' => [[{ 'type' => 'CheckBox', 'label' => 'a' }, { 'type' => 'CheckBox', 'label' => 'b', 'isOn' => true }], %w[checkbox_0_0IsOn checkbox_0_1IsOn]],
    'Radio over items' => [[{ 'type' => 'Radio', 'items' => %w[a b], 'selectedValue' => 'a' }, { 'type' => 'Radio', 'items' => %w[c d] }], %w[selectedRadio_0_0 selectedRadio_0_1]],
    'Segment' => [[{ 'type' => 'Segment', 'items' => %w[a b] }, { 'type' => 'Segment', 'items' => %w[a b], 'selectedIndex' => 1 }], %w[selectedSegment_0_0 selectedSegment_0_1]],
    'Slider' => [[{ 'type' => 'Slider', 'value' => 0.2 }, { 'type' => 'Slider', 'value' => 0.7 }], %w[slider_0_0Value slider_0_1Value]],
    # A TabView keeps a state only for a literal selectedIndex.
    'TabView' => [[{ 'type' => 'TabView', 'tabs' => [{ 'title' => 'A' }], 'selectedIndex' => 0 }, { 'type' => 'TabView', 'tabs' => [{ 'title' => 'A' }], 'selectedIndex' => 1 }], %w[tabView_0_0Selection tabView_0_1Selection]],
    'TextField' => [[{ 'type' => 'TextField', 'text' => 'one' }, { 'type' => 'TextField', 'text' => 'two' }], %w[textField_0_0Text textField_0_1Text]],
    'TextField focus' => [[{ 'type' => 'TextField', 'text' => '@{a}', 'onFocus' => 'focused' }, { 'type' => 'TextField', 'text' => '@{b}', 'onFocus' => 'focused' }], %w[field_0_0IsFocused field_0_1IsFocused]],
    'TextView' => [[{ 'type' => 'TextView', 'text' => 'one' }, { 'type' => 'TextView', 'text' => 'two' }], %w[textEditor_0_0Text textEditor_0_1Text]],
    'Progress' => [[{ 'type' => 'Progress', 'progress' => 0.2 }, { 'type' => 'Progress', 'progress' => 0.7 }], %w[progress_0_0Value progress_0_1Value]],
    'Image highlight' => [[{ 'type' => 'Image', 'srcName' => 'x', 'highlightSrc' => 'x2' }, { 'type' => 'Image', 'srcName' => 'y', 'highlightSrc' => 'y2' }], %w[image_0_0IsPressed image_0_1IsPressed]]
  }

  pairs.each do |kind, (children, expected)|
    it "#{kind}: two without an id keep a state each, named by their positions" do
      _code, _actions, declarations = convert(children)
      got = names(declarations)
      expect(got).to include(*expected), declarations.inspect
      expect(got.uniq.size).to eq(got.size), declarations.inspect
    end
  end

  it 'an explicit id is spelled as it always was' do
    _code, _actions, declarations = convert([
      { 'type' => 'Switch', 'id' => 'sw' }, { 'type' => 'Segment', 'id' => 'a_b', 'items' => %w[x] },
      { 'type' => 'Slider', 'id' => 'vol' }, { 'type' => 'TextField', 'id' => 'first_name', 'text' => 'x' }
    ])
    expect(names(declarations)).to include('swIsOn', 'selectedAB', 'sliderValuevol', 'firstNameText')
  end

  it 'an include takes the one position of the root it expands to' do
    File.write(File.join(dir, 'part.json'), JSON.generate('type' => 'View', 'child' => [{ 'type' => 'Switch' }]))
    path = File.join(dir, 'host.json')
    File.write(path, JSON.generate('type' => 'View', 'child' => [{ 'include' => 'part' }, { 'type' => 'Switch' }]))
    _code, _actions, declarations = converter.convert_json_to_view(path)
    expect(names(declarations)).to eq(%w[toggle_0_0_0IsOn toggle_0_1IsOn])
  end

  describe 'a group of single Radios' do
    group = lambda do |first, second|
      [{ 'type' => 'Radio', 'group' => 'g', 'text' => 'a' }.merge(first),
       { 'type' => 'Radio', 'group' => 'g', 'text' => 'b' }.merge(second)]
    end

    it 'declares its selection once, seeded by the checked Radio, in either order' do
      [[{ 'checked' => true }, {}], [{}, { 'checked' => true }]].each_with_index do |(first, second), checked|
        _code, _actions, declarations = convert(group.call(first, second))
        expect(declarations.grep(/selectedG\b/)).to eq(["@State private var selectedG: String = \"radio_0_#{checked}\""]), declarations.inspect
      end
    end

    it 'the value of an id-less Radio is its position — the Radios are two options' do
      code, = convert(group.call({}, {}))
      expect(code.to_s).to include('selectedG = "radio_0_0"').and include('selectedG = "radio_0_1"')
      expect(code.to_s).not_to include('selectedG = "radio"')
    end

    it 'a literal selectedValue is the group\'s seed; an explicit id or value is the option' do
      _code, _actions, declarations = convert(group.call({ 'id' => 'first', 'checked' => true }, { 'selectedValue' => 'second' }))
      expect(declarations.grep(/selectedG\b/)).to eq(['@State private var selectedG: String = "second"'])
      _code, _actions, declarations = convert(group.call({ 'value' => 'v1' }, { 'id' => 'two', 'checked' => true }))
      expect(declarations.grep(/selectedG\b/)).to eq(['@State private var selectedG: String = "two"'])
    end

    # RadioButton and RadioGroup are drawn as Radio (type_synonyms.json), so
    # they are Radios of the group. Read by the spelling, two RadioButtons
    # were two nodes declaring one name (the layout stopped), and a checked
    # RadioGroup did not seed its group.
    it 'counts a node by the type it is drawn as: RadioButton and RadioGroup are Radios of the group' do
      _code, _actions, declarations = convert(group.call({ 'type' => 'RadioButton' }, { 'type' => 'RadioButton', 'checked' => true }))
      expect(declarations).not_to be_nil
      expect(declarations.grep(/selectedG\b/)).to eq(['@State private var selectedG: String = "radio_0_1"'])
      _code, _actions, declarations = convert(group.call({ 'type' => 'RadioGroup', 'checked' => true }, {}))
      expect(declarations.grep(/selectedG\b/)).to eq(['@State private var selectedG: String = "radio_0_0"'])
    end
  end

  describe 'a name two nodes declare stops the layout' do
    it 'two nodes with one id: not generated, and the ledger names the state' do
      expect(convert([{ 'type' => 'Switch', 'id' => 'sw' }, { 'type' => 'Switch', 'id' => 'sw', 'isOn' => true }])).to be_nil
      entries = JsonUI::StageFailures.entries
      expect(entries.map { |e| e[:stage] }).to eq(['layout'])
      expect(entries.first[:message]).to include('was not generated').and include('`swIsOn`')
    end

    it 'two nodes with one id and one seed are not folded into one state' do
      expect(convert([{ 'type' => 'Switch', 'id' => 'sw' }, { 'type' => 'Switch', 'id' => 'sw' }])).to be_nil
      expect(JsonUI::StageFailures.entries.first[:message]).to include('`swIsOn`')
    end

    it 'two groups whose names read alike once camelCased (a_b, A_b)' do
      expect(convert([{ 'type' => 'Radio', 'group' => 'a_b', 'text' => 'x' },
                      { 'type' => 'Radio', 'group' => 'A_b', 'text' => 'y' }])).to be_nil
      expect(JsonUI::StageFailures.entries.first[:message]).to include('`selectedAB`')
    end

    it 'a layout whose names are apart is generated' do
      expect(convert([{ 'type' => 'Switch' }, { 'type' => 'Switch' }])).not_to be_nil
      expect(JsonUI::StageFailures.entries).to be_empty
    end
  end

  it 'the same layout converts to the same bytes twice' do
    children = pairs.values.flat_map(&:first)
    first = convert(children, name: 'twice')
    second = SjuiTools::SwiftUI::JsonToSwiftUIConverter.new.convert_json_to_view(File.join(dir, 'twice.json'))
    expect(second[0]).to eq(first[0])
    expect(second[2]).to eq(first[2])
  end

  # The pairs that are SwiftUI alone, their declarations and body type-checked
  # together — the "invalid redeclaration" the old names made.
  it 'compiles: id-less pairs of every SwiftUI-only kind, and a group with a checked Radio' do
    children = %w[Switch Segment Slider TabView TextField].flat_map { |k| pairs.find { |name, _| name == k }.last.first } +
               [{ 'type' => 'Radio', 'group' => 'g', 'text' => 'a', 'checked' => true }, { 'type' => 'Radio', 'group' => 'g', 'text' => 'b' }]
    code, _actions, declarations = convert(children)
    body = code.to_s.lines.map { |l| "        #{l}" }.join
    swift = <<~SWIFT
      #{EmittedSwift::LIBRARY_STUBS}
      struct TestData {}
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
end
