# frozen_string_literal: true

require 'swiftui/json_to_swiftui_converter'
require 'swiftui/view_updater'
require_relative '../support/swift_compiler'
require 'json'
require 'tmpdir'
require 'fileutils'

# A layout's root `visibility` (ticket sjui-cell-root-visibility-binding-dropped, 2.5.33): a parent wraps its
# child's visibility in a VisibilityWrapper (child_renderer), and the root of a layout has no parent — a screen's,
# a Collection cell's, header's or footer's, a tab's — so nothing drew it. A cell whose root said
# `"visibility": "@{keyVisibility}"` showed its background with `invisible` on iOS while Android hid it. Measured
# before the fix: binding, `invisible` and `gone` all dropped at the root, all drawn on a child; `hidden` and
# `opacity` drawn at both.
#
# These arms go through the build's own two steps, the converter and ViewUpdater#update_generated_body, and
# type-check the written body against VisibilityWrapper's declaration (SwiftJsonUI VisibilityWrapper.swift,
# transcribed: the signature, not the behaviour).
RSpec.describe 'a layout root\'s visibility (sjui)' do
  let(:work_dir) { File.realpath(Dir.mktmpdir('root_visibility')) }
  let(:converter) { SjuiTools::SwiftUI::JsonToSwiftUIConverter.new }

  before do
    allow(SjuiTools::SwiftUI::StyleLoader).to receive(:load_and_merge) { |data| data }
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
    FileUtils.rm_rf(work_dir)
  end

  DATA_DECL = [{ 'name' => 'keyVisibility', 'class' => 'String' }].freeze

  def body_for(root_extra, children: [{ 'type' => 'Label', 'text' => 'K' }])
    layout = File.join(work_dir, "cell#{rand(1 << 30)}.json")
    File.write(layout, JSON.generate({ 'type' => 'View', 'width' => 60, 'height' => 60, 'data' => DATA_DECL,
                                       'child' => children }.merge(root_extra)))
    code, _a, state, root_children, funcs = converter.convert_json_to_view(layout)
    swift = File.join(work_dir, 'KeyCellGeneratedView.swift')
    File.write(swift, "import SwiftUI\n\nstruct KeyCellGeneratedView: View {\n    var body: some View {\n        Text(\"old\")\n    }\n}\n")
    SjuiTools::SwiftUI::ViewUpdater.new.update_generated_body(swift, code, state_variables: state || [],
                                                               root_children: root_children,
                                                               responsive_functions: funcs || [],
                                                               root_visibility: converter.root_visibility)
    File.read(swift)
  end

  # The body's static branch, as the generated file draws it: the first `VisibilityWrapper(` line before the
  # root container, when there is one.
  def root_wrapper(text)
    static = text[/var body: some View \{(.*)/m, 1]
    first_view = static.lines.map(&:strip).find { |l| l.match?(/\A(VisibilityWrapper|VStack|ZStack|HStack|Weighted|Text|Group|if )/) }
    first_view
  end

  {
    'a binding' => ['@{keyVisibility}', 'VisibilityWrapper(data.keyVisibility) {'],
    'invisible' => ['invisible', 'VisibilityWrapper("invisible") {'],
    'gone' => ['gone', 'VisibilityWrapper("gone") {']
  }.each do |what, (value, line)|
    it "wraps the root in its visibility (#{what})" do
      text = body_for({ 'visibility' => value })
      expect(text).to include(line)
      expect(text.scan('VisibilityWrapper(').size).to eq(1)
    end
  end

  it 'wraps nothing when the root declares no visibility' do
    expect(body_for({})).not_to include('VisibilityWrapper(')
  end

  it 'keeps a child\'s visibility where its parent draws it, and draws the root\'s once around it' do
    text = body_for({ 'visibility' => 'invisible' },
                    children: [{ 'type' => 'Label', 'text' => 'K', 'visibility' => '@{keyVisibility}' }])
    expect(text.scan('VisibilityWrapper("invisible")').size).to eq(1)
    expect(text.scan('VisibilityWrapper(data.keyVisibility)').size).to eq(1)
    expect(text.index('VisibilityWrapper("invisible")')).to be < text.index('VisibilityWrapper(data.keyVisibility)')
  end

  it 'draws a size class\'s override of the root\'s visibility' do
    text = body_for({ 'visibility' => 'visible', 'responsive' => { 'regular' => { 'visibility' => 'gone' } } })
    expect(text).to match(/VisibilityWrapper\(.*horizontalSizeClass == \.regular.*"gone"/)
  end

  # A body long enough to split keeps its split (the split reads the root container off its first line) and is
  # wrapped once, around the split body.
  it 'wraps a split body once, after the split' do
    rows = Array.new(140) { |i| { 'type' => 'Label', 'text' => "row #{i}", 'weight' => 1 } }
    text = body_for({ 'visibility' => '@{keyVisibility}', 'orientation' => 'vertical', 'height' => 'matchParent' }, children: rows)
    expect(text.scan('VisibilityWrapper(data.keyVisibility)').size).to eq(1)
    expect(text).to match(/func (section|Section)\w*\(/)
  end

  it 'type-checks against VisibilityWrapper\'s declaration' do
    text = body_for({ 'visibility' => '@{keyVisibility}' })
    lines = text.lines
    open_at = lines.index { |l| l.include?('VisibilityWrapper(data.keyVisibility) {') }
    expect(open_at).not_to be_nil
    indent = lines[open_at][/\A */]
    close_at = (open_at + 1...lines.size).find { |i| lines[i] == "#{indent}}\n" }
    static = lines[open_at..close_at].join
    source = <<~SWIFT
      struct VisibilityWrapper<Content: View>: View {
          init(_ visibilityString: String?, @ViewBuilder content: () -> Content) { self.content = content() }
          let content: Content
          var body: some View { content }
      }
      struct KeyCellData { var keyVisibility: String = "visible" }
      struct Probe: View {
          var data = KeyCellData()
          var body: some View {
              #{static}
          }
      }
    SWIFT
    expect(source).to compile_as_swift.with_imports('SwiftUI')
  end
end
