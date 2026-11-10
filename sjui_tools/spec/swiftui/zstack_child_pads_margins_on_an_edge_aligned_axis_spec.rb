# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'swiftui/json_to_swiftui_converter'
require_relative '../support/emitted_swift'

# A ZStack child's margins on an axis the ZStack aligns to an edge are padding,
# in full (ticket sjui-overlay-child-far-margin-moves-it-out).
#
# They were an offset (left - right, top - bottom) with only the shared part
# padded, so a child at the top-left with a right or bottom margin moved out
# by it (x -10 for a right margin of 10, where Android and web draw 0), and a
# wrapContent ZStack left the margins out of its size (20 wide around a child
# 20 wide with a left margin of 10, the child drawn past its right edge;
# Android 30). Family table 2026-11-10, iOS dynamic and codegen alike. An
# axis the ZStack centres, and an axis the child centres, are drawn as before.
RSpec.describe 'sjui: a ZStack child pads its margins on an edge-aligned axis' do
  let(:dir) { Dir.mktmpdir('zstack_margin_edge') }

  after { FileUtils.rm_rf(dir) }

  def convert(parent, children)
    path = File.join(dir, 'parent.json')
    File.write(path, JSON.generate(parent.merge('child' => children)))
    SjuiTools::SwiftUI::JsonToSwiftUIConverter.new.convert_json_to_view(path)
  end

  def code_for(parent, child)
    convert(parent, [child]).first
  end

  let(:box) { { 'type' => 'View', 'width' => 20, 'height' => 20 } }

  it 'a right margin at the top-left is the trailing padding, not an offset' do
    code = code_for({ 'type' => 'View' }, box.merge('rightMargin' => 10))
    expect(code).to include('.padding(.trailing, 10)')
    expect(code).not_to include('.offset(')
  end

  it 'two different margins are each their own padding' do
    code = code_for({ 'type' => 'View' }, box.merge('leftMargin' => 10, 'rightMargin' => 30, 'topMargin' => 10, 'bottomMargin' => 30))
    expect(code).to include('.padding(.leading, 10)', '.padding(.trailing, 30)', '.padding(.top, 10)', '.padding(.bottom, 30)')
    expect(code).not_to include('.offset(')
  end

  it 'a ZStack aligned to the trailing edge pads the margins in full too' do
    code = code_for({ 'type' => 'View', 'gravity' => %w[right bottom] }, box.merge('rightMargin' => 8, 'bottomMargin' => 8))
    expect(code).to include('.padding(.trailing, 8)', '.padding(.bottom, 8)')
    expect(code).not_to include('.offset(')
  end

  it 'an axis the ZStack centres keeps the offset and the shared padding' do
    code = code_for({ 'type' => 'View', 'gravity' => 'center' }, box.merge('leftMargin' => 10, 'rightMargin' => 30))
    expect(code).to include('.offset(x: -20, y: 0)', '.padding(.leading, 10)', '.padding(.trailing, 10)')
  end

  # A child that aligns or centres itself is placed by the relative
  # container, which takes the margins itself: not this path.
  it 'a child that centres itself is not drawn through this path' do
    code = code_for({ 'type' => 'View' }, box.merge('centerHorizontal' => true, 'leftMargin' => 10, 'topMargin' => 10))
    expect(code).to include('RelativePositionContainer(')
    expect(code).not_to include('ZStack(alignment:')
  end

  it 'compiles: the padded and the offset forms, a bound margin among them' do
    code, _actions, decls, _root, functions = convert(
      { 'type' => 'View', 'gravity' => 'centerHorizontal' },
      [box.merge('leftMargin' => 10, 'rightMargin' => 30, 'topMargin' => '@{gap}', 'bottomMargin' => 30)]
    )
    expect(code).to include('.padding(.bottom, 30)')
    body = code.to_s.lines.map { |l| "        #{l}" }.join
    swift = <<~SWIFT
      #{EmittedSwift::LIBRARY_STUBS}
      struct TestData { var gap: CGFloat = 4 }
      struct EmittedHost: View {
          @Binding var data: TestData
      #{decls.map { |d| "    #{d}" }.join("\n")}
          var body: some View {
      #{body}
          }
      #{Array(functions).join("\n")}
      }
    SWIFT
    expect(swift).to compile_as_swift.with_imports('SwiftUI')
  end

  it 'a margins array keeps its padding, as before' do
    code = code_for({ 'type' => 'View' }, box.merge('margins' => [1, 2, 3, 4]))
    expect(code).not_to include('.offset(')
  end
end
