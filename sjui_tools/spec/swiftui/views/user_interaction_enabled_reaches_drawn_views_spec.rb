# frozen_string_literal: true

require 'swiftui/converter_factory'
require 'swiftui/json_to_swiftui_converter'
require 'swiftui/interaction_stop_index'
require_relative '../../support/emitted_swift'
require 'core/tap_accessibility'
require 'core/image_accessibility'
require 'json'
require 'tmpdir'
require 'fileutils'

# `userInteractionEnabled` stops a view and everything in it, and the tap rule
# says no tap for what it holds (annotate!). What it draws in a view of its
# own — a Collection's cells, headers and footers, an Embed's screen, a
# TabView tab's view — is another layout, another file: annotate! does not
# reach it, and its taps were still announced as buttons (measured at
# jsonui-cli 0ad0d32e, before 1.9.0: a cell with onClick inside a Collection inside a View
# with the flag false was emitted with `.accessibilityAddTraits(.isButton)`
# and nothing that knew of the stop).
#
# The stop is handed down at run time, as the Dynamic runtime hands it down:
# the stopping view sets SwiftJsonUI's `jsonuiInteractionStopped` environment
# value, and the layouts it can reach (InteractionStopIndex, over the whole
# project) declare it and gate every tap on it. Every other layout is emitted
# as it was.
RSpec.describe 'sjui userInteractionEnabled reaches what is drawn in a view of its own' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
    SjuiTools::SwiftUI::Views::BaseViewConverter.reads_interaction_environment = false
  end
  after { SjuiTools::SwiftUI::Views::BaseViewConverter.reads_interaction_environment = false }

  tap = JsonUIShared::TapAccessibility

  convert = lambda do |comp, reads: false|
    SjuiTools::SwiftUI::Views::BaseViewConverter.reads_interaction_environment = reads
    comp = JSON.parse(JSON.generate(comp))
    JsonUIShared::ImageAccessibility.annotate!(comp, source_path: 'probe.json')
    tap.annotate!(comp)
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter(comp).convert.to_s
  ensure
    SjuiTools::SwiftUI::Views::BaseViewConverter.reads_interaction_environment = false
  end

  collection = { 'type' => 'Collection', 'id' => 'list', 'cellClasses' => ['row_cell'], 'items' => '@{rows}' }
  stopping = ->(flag, child) { { 'type' => 'View', 'id' => 'stop', 'userInteractionEnabled' => flag, 'child' => [child] } }
  static_line = '.environment(\.jsonuiInteractionStopped, true)'
  bound_line = '.transformEnvironment(\.jsonuiInteractionStopped) { $0 = $0 || !(data.u ?? false) }'

  describe 'the rule: what a node draws elsewhere' do
    {
      'a Collection cell, header and footer, and a section cell' =>
        [{ 'type' => 'Collection', 'cell' => 'a', 'header' => 'b', 'footer' => 'c', 'sections' => [{ 'cell' => 'd' }] }, %w[a b c d]],
      'cellClasses, by name and by className' =>
        [{ 'type' => 'Collection', 'cellClasses' => ['e', { 'className' => 'f' }], 'headerClasses' => ['g'] }, %w[e f g]],
      'a Table is a Collection' => [{ 'type' => 'Table', 'cellClasses' => ['h'] }, %w[h]],
      "an Embed's screen" => [{ 'type' => 'Embed', 'screen' => 'i' }, %w[i]],
      "a TabView's tab views" => [{ 'type' => 'TabView', 'tabs' => [{ 'view' => 'j' }, { 'title' => 'no view' }] }, %w[j]],
      'a bound reference names no layout' => [{ 'type' => 'Embed', 'screen' => '@{s}' }, []],
      'a View draws nothing elsewhere' => [{ 'type' => 'View', 'cell' => 'k' }, []]
    }.each do |name, (node, refs)|
      it name do
        expect(tap.drawn_elsewhere(node)).to match_array(refs)
      end
    end

    # A node is read as the type it is drawn as (type_synonyms.rb): every
    # spelling the table draws as a Collection draws its cells elsewhere, as
    # a Collection does. Read by the spelling, a TableView, a List, a
    # ListView or a RecyclerView drew nothing elsewhere, and a stop around it
    # did not reach its cells. Given a table without TableView's entry, a
    # TableView draws nothing elsewhere: the answer follows the table.
    it 'every spelling the table draws as a Collection draws its cells elsewhere' do
      spellings = JsonUIShared::TypeSynonyms.entries.select { |_, e| (e['render_as'] || e['canonical']) == 'Collection' }.keys
      expect(spellings).to include('TableView', 'List', 'ListView', 'RecyclerView') # (control)
      spellings.each do |spelling|
        expect(tap.drawn_elsewhere({ 'type' => spelling, 'cellClasses' => ['h'] })).to eq(%w[h]), spelling
      end
      table = JsonUIShared::TypeSynonyms.entries.reject { |spelling, _| spelling == 'TableView' }
      allow(JsonUIShared::TypeSynonyms).to receive(:entries).and_return(table)
      expect(tap.drawn_elsewhere({ 'type' => 'TableView', 'cellClasses' => ['h'] })).to eq([])
    end

    it 'hands the stop down only where the flag is false or bound and something below draws elsewhere' do
      expect(tap.hands_stop_down?(stopping.call(false, collection))).to be(true)
      expect(tap.hands_stop_down?(stopping.call('@{u}', { 'type' => 'View', 'child' => [collection] }))).to be(true)
      expect(tap.hands_stop_down?(stopping.call(true, collection))).to be(false)
      expect(tap.hands_stop_down?(stopping.call(false, { 'type' => 'Label', 'text' => 'x' }))).to be(false)
      expect(tap.hands_stop_down?({ 'type' => 'View', 'child' => [collection] })).to be(false)
      expect(tap.hands_stop_down?(collection.merge('userInteractionEnabled' => false))).to be(true)
    end

    it 'reaches what a stop draws, and what that draws in turn, and nothing else' do
      trees = {
        'screen' => { 'type' => 'View', 'child' => [
          stopping.call(false, { 'type' => 'Collection', 'cellClasses' => ['stopped_cell'] }),
          { 'type' => 'Collection', 'cellClasses' => ['free_cell'] },
          stopping.call('@{u}', { 'type' => 'Embed', 'screen' => 'bound_embed' })
        ] },
        'stopped_cell' => { 'type' => 'View', 'child' => [{ 'type' => 'Embed', 'screen' => 'nested_screen' }] },
        'nested_screen' => { 'type' => 'Label', 'text' => 'x', 'onClick' => '@{onOpen}' },
        'free_cell' => { 'type' => 'View', 'child' => [{ 'type' => 'Collection', 'cellClasses' => ['free_nested'] }] },
        'free_nested' => { 'type' => 'Label', 'text' => 'x' },
        'bound_embed' => { 'type' => 'View' }
      }
      expect(tap.stoppable_layouts(trees).to_a).to match_array(%w[stopped_cell nested_screen bound_embed])
    end
  end

  describe 'InteractionStopIndex, over a layouts directory' do
    around do |example|
      Dir.mktmpdir do |dir|
        @dir = dir
        example.run
      end
    end

    def write(name, tree)
      path = File.join(@dir, "#{name}.json")
      FileUtils.mkdir_p(File.dirname(path))
      File.write(path, JSON.generate(tree))
    end

    it 'reaches a cell through an include, and maps references to screen ids' do
      write('screen', { 'type' => 'View', 'userInteractionEnabled' => false, 'child' => [{ 'include' => 'part' }] })
      write('part', { 'type' => 'View', 'child' => [{ 'type' => 'Collection', 'cellClasses' => ['row_cell.json'] }] })
      write('row_cell', { 'type' => 'View', 'onClick' => '@{onRow}' })
      write('other', { 'type' => 'Collection', 'cellClasses' => ['free_cell'] })
      write('free_cell', { 'type' => 'View', 'onClick' => '@{onRow}' })
      expect(SjuiTools::SwiftUI::InteractionStopIndex.build(@dir).to_a).to eq(['row_cell'])
    end

    it 'is empty with no directory' do
      expect(SjuiTools::SwiftUI::InteractionStopIndex.build(nil)).to be_empty
    end
  end

  describe 'the stopping view' do
    it 'with false, sets the environment after its own stop, once' do
      code = convert.call(stopping.call(false, collection))
      expect(code.scan(static_line).size).to eq(1)
      expect(code.index(static_line)).to be > code.index('.allowsHitTesting(false)')
    end

    it 'with a binding, sets it from the stop around it and the binding' do
      code = convert.call(stopping.call('@{u}', collection))
      expect(code.scan(bound_line).size).to eq(1), code
    end

    it 'holding nothing drawn elsewhere, sets nothing' do
      code = convert.call(stopping.call(false, { 'type' => 'Label', 'id' => 'l', 'text' => 't' }))
      expect(code).not_to include('jsonuiInteractionStopped')
      expect(code).to include('.allowsHitTesting(false)')
    end

    it 'with no flag, sets nothing' do
      expect(convert.call({ 'type' => 'View', 'id' => 'v', 'child' => [collection] })).not_to include('jsonuiInteractionStopped')
    end
  end

  describe 'a view a stop can reach' do
    extra = {
      'Image' => { 'srcName' => 'x' }, 'CircleImage' => { 'srcName' => 'x' }, 'CircleImageView' => { 'srcName' => 'x' },
      'ImageView' => { 'srcName' => 'x' }, 'Img' => { 'srcName' => 'x' },
      'NetworkImage' => { 'url' => 'https://e/x.png' }, 'Label' => { 'text' => 't' },
      'Text' => { 'text' => 't' }, 'IconLabel' => { 'text' => 't' }
    }
    node = ->(type, more = {}) { { 'type' => type, 'id' => 'n', 'onClick' => '@{onTap}' }.merge(extra[type] || {}).merge(more) }

    (tap::KNOWN_TYPES - tap::INTERACTIVE_TYPES - %w[IconLabel]).uniq.each do |type|
      it "#{type}: its tap is masked and its trait follows the stop handed down" do
        code = convert.call(node.call(type), reads: true)
        expect(code).to include('including: !jsonuiInteractionStopped ? .all : .subviews)')
        expect(code).not_to include('.onTapGesture')
        expect(code).not_to include('.accessibilityAddTraits(.isButton)')
      end

      it "#{type}: in a view no stop can reach, it is emitted as it was" do
        expect(convert.call(node.call(type))).not_to include('jsonuiInteractionStopped')
      end
    end

    it 'joins the handed-down stop after a bound canTap and the bound flags in the file' do
      code = convert.call(stopping.call('@{u}', node.call('Label', 'canTap' => '@{c}')), reads: true)
      gate = '(data.c ?? false) && (data.u ?? false) && !jsonuiInteractionStopped'
      expect(code).to include("including: #{gate} ? .all : .subviews)")
      expect(code).to include(".accessibilityAddTraits(#{gate} ? AccessibilityTraits.isButton : [])")
    end

    it "a Button's action is gated on it too" do
      code = convert.call({ 'type' => 'Button', 'id' => 'b', 'text' => 't', 'onClick' => '@{onTap}' }, reads: true)
      expect(code).to include('action: { if !jsonuiInteractionStopped {')
    end
  end

  describe 'sjui build, per layout' do
    around do |example|
      Dir.mktmpdir do |dir|
        @dir = dir
        example.run
      end
    end

    it 'declares the environment in the views a stop can reach, and only there' do
      File.write(File.join(@dir, 'screen.json'),
                 JSON.generate(stopping.call(false, collection)))
      File.write(File.join(@dir, 'row_cell.json'), JSON.generate({ 'type' => 'View', 'id' => 'r', 'onClick' => '@{onRow}' }))
      File.write(File.join(@dir, 'free.json'), JSON.generate({ 'type' => 'View', 'id' => 'f', 'onClick' => '@{onRow}' }))
      converter = SjuiTools::SwiftUI::JsonToSwiftUIConverter.new
      converter.interaction_stoppable_ids = SjuiTools::SwiftUI::InteractionStopIndex.build(@dir)
      declaration = SjuiTools::SwiftUI::Views::BaseViewConverter::INTERACTION_ENVIRONMENT_DECLARATION
      cell_code, _, cell_state = converter.convert_json_to_view(File.join(@dir, 'row_cell.json'))
      free_code, _, free_state = converter.convert_json_to_view(File.join(@dir, 'free.json'))
      screen_code, = converter.convert_json_to_view(File.join(@dir, 'screen.json'))
      expect(cell_state).to include(declaration)
      expect(cell_code).to include('!jsonuiInteractionStopped ? AccessibilityTraits.isButton : []')
      expect(free_state).not_to include(declaration)
      expect(free_code).to include('.accessibilityAddTraits(.isButton)')
      expect(screen_code).to include(static_line)
      expect(declaration).to eq('@Environment(\.jsonuiInteractionStopped) private var jsonuiInteractionStopped')
    end
  end

  # SwiftJsonUI declares the key (JsonUIInteractionStop.swift); the stub here
  # is that declaration, so the emitted modifiers and the reading view are
  # checked against SwiftUI's own `environment` / `transformEnvironment`.
  env_stub = <<~SWIFT
    private struct JsonUIInteractionStoppedKey: EnvironmentKey { static var defaultValue: Bool { false } }
    extension EnvironmentValues {
        var jsonuiInteractionStopped: Bool {
            get { self[JsonUIInteractionStoppedKey.self] }
            set { self[JsonUIInteractionStoppedKey.self] = newValue }
        }
    }
  SWIFT

  # The two lines a stopping view emits, as emitted (the views around them
  # draw library types the stub universe does not declare), and a whole
  # reading view.
  it 'the stopping lines and a reading view compile' do
    expect(convert.call(stopping.call(false, collection))).to include(static_line)
    bound = convert.call(stopping.call('@{u}', { 'type' => 'Embed', 'id' => 'e', 'screen' => 'row_cell' }))
    reading = convert.call({ 'type' => 'View', 'id' => 'r', 'onClick' => '@{onTap}',
                             'child' => [{ 'type' => 'Label', 'text' => 'x' }] }, reads: true)
    expect(bound).to include(bound_line)
    source = <<~SWIFT
      #{EmittedSwift::LIBRARY_STUBS}
      #{env_stub}
      struct TestData { var onTap: (() -> Void)? = nil; var u: Bool? = nil }
      struct Reading: View {
          let data = TestData()
          @Environment(\\.jsonuiInteractionStopped) private var jsonuiInteractionStopped
          var body: some View {
      #{reading.lines.map { |l| "        #{l}" }.join}
          }
      }
      struct Bound: View {
          let data = TestData()
          var body: some View {
              Color.clear
                  #{bound_line}
          }
      }
      struct Static: View {
          var body: some View {
              Color.clear
                  #{static_line}
          }
      }
    SWIFT
    expect(source).to compile_as_swift
  end
end
