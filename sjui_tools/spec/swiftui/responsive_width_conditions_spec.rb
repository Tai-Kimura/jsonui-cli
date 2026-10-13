# frozen_string_literal: true

require 'swiftui/json_to_swiftui_converter'
require 'swiftui/view_updater'
require 'json'
require 'fileutils'
require_relative '../support/emitted_swift'
require_relative '../support/swift_compiler'

# responsive minWidth:N / maxWidth:N (jui-responsive-width-threshold-conditions):
# the window's width, read from the library's SJUIWindowWidth, which the view
# owns and view_updater ties to its window. Which key wins is the resolver's
# (shared/core/responsive_resolution_vectors.json, responsive_resolver_spec);
# this holds the emitted conditions to it: maxWidth:N is `< N`, minWidth:N is
# `>= N`, most narrowing first.
RSpec.describe 'responsive width conditions (SwiftUI codegen)' do
  let(:converter) { SjuiTools::SwiftUI::JsonToSwiftUIConverter.new }
  let(:temp_dir) { File.realpath(Dir.mktmpdir('responsive_width_conditions')) }
  let(:declaration) { SjuiTools::SwiftUI::Views::ResponsiveHelper::WINDOW_WIDTH_DECLARATION }

  before do
    allow(SjuiTools::SwiftUI::StyleLoader).to receive(:load_and_merge) { |data| data }
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
    FileUtils.rm_rf(temp_dir)
  end

  def convert(tree)
    path = File.join(temp_dir, 'width_test.json')
    File.write(path, JSON.generate(tree))
    converter.convert_json_to_view(path)
  end

  let(:split) do
    { 'type' => 'View', 'orientation' => 'vertical', 'spacing' => 8,
      'responsive' => { 'minWidth:700' => { 'orientation' => 'horizontal', 'spacing' => 24 },
                        'maxWidth:400' => { 'spacing' => 4 } },
      'child' => [{ 'type' => 'Label', 'text' => 'Hello' }] }
  end

  it 'reads the window width: maxWidth first as `< N`, then minWidth as `>= N`' do
    _code, _actions, _state, _root, functions = convert(split)
    body = functions.join("\n")
    first = body.index('if sjuiWindowWidth.value < 400 {')
    second = body.index('} else if sjuiWindowWidth.value >= 700 {')
    expect(first).not_to be_nil, body
    expect(second).not_to be_nil, body
    expect(first).to be < second
    expect(body).not_to include('horizontalSizeClass')
  end

  it 'gives the view an SJUIWindowWidth when a node has width conditions, nested too' do
    nested = { 'type' => 'View', 'child' => [{ 'type' => 'View', 'child' => [split] }] }
    _code, _actions, state = convert(nested)
    expect(state).to include(declaration)
  end

  it 'leaves a view with size classes only as it was: no SJUIWindowWidth' do
    tree = split.merge('responsive' => { 'regular' => { 'spacing' => 24 } })
    _code, _actions, state = convert(tree)
    expect(state).not_to include(declaration)
    expect(state).to include(a_string_matching(/horizontalSizeClass/))
  end

  it 'draws a leaf per width condition too (a Label override)' do
    tree = { 'type' => 'View', 'child' => [
      { 'type' => 'Label', 'text' => 'x', 'fontSize' => 12, 'responsive' => { 'minWidth:600' => { 'fontSize' => 20 } } }
    ] }
    code, _actions, state, _root, functions = convert(tree)
    expect(state).to include(declaration)
    expect([code, *functions].join("\n")).to include('sjuiWindowWidth.value >= 600')
  end

  it 'compiles against the library surface it names', :swift_compile do
    skip("swiftc: #{SwiftCompiler.unavailable_reason}") if SwiftCompiler.unavailable_reason
    code, _actions, state, _root, functions = convert(split)
    source = <<~SWIFT
      #{EmittedSwift::LIBRARY_STUBS}
      // SwiftJsonUI Classes/SwiftUI/SJUIWindowWidth.swift: its public surface.
      @MainActor final class SJUIWindowWidth: ObservableObject {
          @Published private(set) var value: CGFloat = 0
          init() {}
      }
      struct EmittedHost: View {
      #{state.map { |s| "    #{s}" }.join("\n")}
          var body: some View {
      #{code.lines.map { |l| "        #{l}" }.join}
          }
      #{functions.join("\n")}
      }
    SWIFT
    expect(source).to compile_as_swift
  end

  describe 'view_updater' do
    let(:updater) { SjuiTools::SwiftUI::ViewUpdater.new }
    let(:swift_file_path) { File.join(temp_dir, 'WidthTestGeneratedView.swift') }

    before do
      File.write(swift_file_path, <<~SWIFT)
        import SwiftUI

        struct WidthTestGeneratedView: View {
            @Binding var data: WidthTestData

            var body: some View {
                Text("Old content")
            }
        }
      SWIFT
    end

    it 'ties the SJUIWindowWidth to the window on the outer Group' do
      updater.update_generated_body(swift_file_path, 'Text("x")', state_variables: [declaration])
      content = File.read(swift_file_path)
      expect(content).to include("    #{declaration}\n")
      expect(content).to include(".receiveEmbedInitParams(to: viewModel)\n" \
                                 "            // Requires SwiftJsonUI >= #{SjuiTools::SwiftUI::ViewUpdater::WINDOW_WIDTH_MIN_LIBRARY_VERSION} " \
                                 "(responsive minWidth / maxWidth)\n" \
                                 "            .sjuiTracksWindowWidth(sjuiWindowWidth)")
    end

    it 'adds nothing to a view without one' do
      updater.update_generated_body(swift_file_path, 'Text("x")',
                                    state_variables: ['@Environment(\.horizontalSizeClass) private var horizontalSizeClass'])
      expect(File.read(swift_file_path)).not_to include('sjuiTracksWindowWidth')
    end
  end
end
