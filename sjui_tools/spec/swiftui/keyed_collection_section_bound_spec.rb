# frozen_string_literal: true

require 'json'
require 'stringio'
require 'tmpdir'
require 'fileutils'
require 'swiftui/json_to_swiftui_converter'
require 'swiftui/view_updater'
require 'swiftui/section_bounder'
require 'core/stage_failures'
require_relative '../support/emitted_swift'

# jsonui-cli 1.9.0 (reported 2026-09-28, two consumer apps): `jui build`
# printed, where 1.8.120 printed nothing,
#
#   warning: [section-bounder] …GeneratedView.swift section0(+1): depth 7 / 35 lines
#   exceeds the bound and has no safe cut (no safe cut point). …
#
# on four list screens, and the apps' depth check wants every function at 5
# or less. The four shapes below are theirs, with synthetic names: a
# weighted Collection keyed by cellIdProperty, with a regular-size-class
# variant (columns, or a maxWidth) — so the function the bounder gets is the
# size-class switch, and the compact route is the keyed collection skeleton
# (section_bounder_spec.rb, "the if at the budget"). Not wrapContent: a
# weighted Collection is not content-fitted, and a content-fitted one was
# already cut at its CollectionContentFit (the last example).
#
# This runs the layouts down `jui build`'s emit path — convert_json_to_view,
# then update_generated_body, which bounds the body and prints the waivers.
# That a cut moves lines and changes none is section_bounder_spec.rb's.
RSpec.describe 'a keyed Collection with a size-class variant, on the jui build emit path' do
  include EmittedSwift

  let(:dir) { Dir.mktmpdir('keyed_collection_section_bound') }

  before { JsonUI::StageFailures.clear! }
  after { FileUtils.rm_rf(dir) }

  def collection(extra)
    {
      'type' => 'Collection', 'id' => 'rows_list', 'width' => 'matchParent', 'weight' => 1,
      'cellClasses' => ['probe/row_cell'], 'sections' => [{ 'cell' => 'probe/row_cell' }],
      'items' => '@{rows}', 'cellIdProperty' => 'cellId'
    }.merge(extra)
  end

  def screen(collection_node, siblings)
    {
      'type' => 'SafeAreaView', 'width' => 'matchParent', 'height' => 'matchParent', 'orientation' => 'vertical',
      'child' => [
        { 'data' => [
          { 'name' => 'rows', 'class' => 'CollectionDataSource', 'defaultValue' => 'CollectionDataSource()' },
          { 'name' => 'listVisibility', 'class' => 'String', 'defaultValue' => 'visible' },
          { 'name' => 'emptyVisibility', 'class' => 'String', 'defaultValue' => 'gone' }
        ] }
      ] + siblings.first + [collection_node] + siblings.last
    }
  end

  def empty_label
    { 'type' => 'Label', 'id' => 'empty_label', 'width' => 'matchParent', 'height' => 'wrapContent',
      'text' => 'empty', 'visibility' => '@{emptyVisibility}' }
  end

  def empty_view
    { 'type' => 'View', 'id' => 'empty_view', 'width' => 'matchParent', 'weight' => 1, 'gravity' => 'center',
      'visibility' => '@{emptyVisibility}', 'child' => [empty_label.merge('visibility' => nil).compact] }
  end

  # The four screens' shapes, one each.
  def shapes
    {
      'A: columns 3, insets, visibility; a weighted sibling after' => screen(
        collection('visibility' => '@{listVisibility}', 'lineSpacing' => 12, 'insets' => [24, 16, 16, 16],
                   'responsive' => { 'regular' => { 'columns' => 3, 'columnSpacing' => 12 } }),
        [[], [empty_view]]
      ),
      'B: columns 2, paddings; a label after' => screen(
        collection('lineSpacing' => 12, 'paddings' => [16, 16, 16, 16],
                   'responsive' => { 'regular' => { 'columns' => 2, 'columnSpacing' => 12 } }),
        [[], [empty_label]]
      ),
      'C: columns 3, paddings, autoChangeTrackingId, visibility; a sibling before' => screen(
        collection('orientation' => 'vertical', 'lineSpacing' => 12, 'paddings' => [16, 16, 16, 16],
                   'autoChangeTrackingId' => true, 'visibility' => '@{listVisibility}',
                   'responsive' => { 'regular' => { 'columns' => 3, 'columnSpacing' => 12 } }),
        [[empty_view], []]
      ),
      'D: a regular maxWidth, insets, autoChangeTrackingId, visibility; a label before' => screen(
        collection('insets' => [16, 16, 16, 16], 'autoChangeTrackingId' => true, 'visibility' => '@{listVisibility}',
                   'responsive' => { 'regular' => { 'maxWidth' => 720, 'centerHorizontal' => true } }),
        [[empty_label], []]
      )
    }
  end

  # [the GeneratedView's text, what update_generated_body printed, the unbounded body]
  def emit(layout)
    path = File.join(dir, 'probe.json')
    File.write(path, JSON.generate(layout))
    body, _, state, root_children, responsive = SjuiTools::SwiftUI::JsonToSwiftUIConverter.new.convert_json_to_view(path)
    swift = File.join(dir, 'ProbeGeneratedView.swift')
    File.write(swift, "import SwiftUI\nstruct ProbeGeneratedView: View {\n    @Binding var data: ProbeData\n    var body: some View {\n        Text(\"x\")\n    }\n}\n")
    printed = StringIO.new
    kept = $stdout
    begin
      $stdout = printed
      SjuiTools::SwiftUI::ViewUpdater.new.update_generated_body(
        swift, body, state_variables: state || [], root_children: root_children, responsive_functions: responsive || []
      )
    ensure
      $stdout = kept
    end
    [File.read(swift), printed.string, body]
  end

  # Every function body's brace depth, as the consumer's measure_view_depth.py
  # counts it: the peak inside the function, less its own brace.
  def function_depths(text)
    lines = text.split("\n")
    lines.each_index.select { |i| lines[i] =~ /\A\s*(?:@ViewBuilder\s+)?private\s+(?:func\s+\w+\s*\(|var\s+\w+\s*:\s*some\s+View)/ }.to_h do |start|
      depth = peak = 0
      lines[start..].each do |line|
        code = SjuiTools::SwiftUI::SectionBounder.strip_noise(line)
        code.each_char do |ch|
          if ch == '{'
            depth += 1
            peak = depth if depth > peak
          elsif ch == '}'
            depth -= 1
          end
        end
        break if depth.zero? && peak.positive?
      end
      [lines[start][/(?:func|var)\s+(\w+)/, 1], peak - 1]
    end
  end

  it 'reaches the bounder at depth 7, and comes out with no waiver and every function at 5 or less' do
    shapes.each do |name, layout|
      text, printed, body = emit(layout)
      expect(SjuiTools::SwiftUI::SectionBounder.max_brace_depth(body.split("\n"))).to be >= 7, name
      expect(printed).not_to include('[section-bounder]'), "#{name}\n#{printed}"
      depths = function_depths(text)
      expect(depths.values.max).to be <= SjuiTools::SwiftUI::SectionBounder::BODY_DEPTH_HARD, "#{name}: #{depths}"
    end
  end

  it 'keeps the keyed loop, its ids and the scrollTo keys in the function that lifts them whole' do
    shapes.each do |name, layout|
      text, = emit(layout)
      lifted = text.scan(/@ViewBuilder private func (section[\d_]+)\(section: CollectionDataSection\) -> some View \{\n\s*if let cellsData = section\.cells\?\.data \{/)
      expect(lifted).not_to be_empty, name
      lifted.flatten.each do |fn|
        own = text[/private func #{fn}\(.*?\n    \}\n/m]
        expect(own).to include('let ids: [AnyHashable] = {'), name
        expect(own).to include('ForEach(zip(ids, items).map { pair in (id: pair.0, cell: pair.1) }, id: \.id) { item in'), name
      end
    end
  end

  # The whole GeneratedView, cut, type-checks: the lifted function's
  # `section: CollectionDataSection` and the argument its call site passes.
  # Stand-ins mirror SwiftJsonUI 10.29.0's declarations (WeightedStackView.swift,
  # VisibilityWrapper.swift, CellIdGenerator.swift, EmbedContainer.swift); the
  # Dynamic-mode branch is `#if DEBUG` and is not compiled here.
  def compilable_generated_view(text)
    view = text.lines.reject { |l| l.start_with?('import SwiftJsonUI', 'import Combine') }.join
    <<~SWIFT
      #{EmittedSwift::LIBRARY_STUBS}
      #{EmittedSwift::COLLECTION_DATA_SOURCE_STUB}
      #{EmittedSwift::COLLECTION_STACK_VIEW_STUB}
      #{cell_view_stub('RowCellView')}
      struct WeightedVStack: View {
          init(alignment: HorizontalAlignment = .leading, spacing: CGFloat = 0, children: [(view: AnyView, weight: CGFloat)]) {}
          var body: some View { EmptyView() }
      }
      struct VisibilityWrapper<Content: View>: View {
          init(_ visibilityString: String?, @ViewBuilder content: () -> Content) {}
          var body: some View { EmptyView() }
      }
      extension View {
          func receiveEmbedInitParams(to viewModel: Any) -> some View { self }
      }
      extension Array where Element == [String: Any] {
          func reconfigured(cellIdProperty: String?, autoChangeTrackingId: Bool) -> [[String: Any]] { self }
      }
      struct ProbeData {
          var rows: CollectionDataSource = CollectionDataSource()
          var listVisibility: String = "visible"
          var emptyVisibility: String = "gone"
      }
      #{view}
    SWIFT
  end

  it 'type-checks, cut', :swift_compile do
    shapes.each do |name, layout|
      text, = emit(layout)
      expect(compilable_generated_view(text)).to compile_as_swift.with_imports('SwiftUI'), name
    end
    # Control: the same file with the lifted function's argument dropped at its call site.
    text, = emit(shapes.values.first)
    broken = text.sub(/AnyView\((section[\d_]+)\(section: section\)\)/) { "AnyView(#{Regexp.last_match(1)}())" }
    expect(broken).not_to eq(text)
    expect(compilable_generated_view(broken)).not_to compile_as_swift.with_imports('SwiftUI')
  end

  # Control: the same keyed Collection unweighted is content-fitted, and the
  # CollectionContentFit container was a cut before this pass existed.
  it 'control: a wrapContent keyed Collection is cut at its CollectionContentFit' do
    layout = screen(collection('weight' => nil, 'insets' => [24, 16, 16, 16],
                               'responsive' => { 'regular' => { 'columns' => 3, 'columnSpacing' => 12 } }).compact,
                    [[], [empty_label]])
    text, printed, = emit(layout)
    expect(text).to include('CollectionContentFit(axis: .vertical) {')
    expect(printed).not_to include('[section-bounder]')
    expect(function_depths(text).values.max).to be <= SjuiTools::SwiftUI::SectionBounder::BODY_DEPTH_HARD
  end
end
