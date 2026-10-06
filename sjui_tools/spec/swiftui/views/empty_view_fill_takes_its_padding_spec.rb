# frozen_string_literal: true

require 'swiftui/views/view_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

# An empty View whose background is its content (Rectangle / PressedFill)
# paints its padding too: the padding is part of the element (user ruling
# 2026-10-06). The padding used to be applied outside the fill, inside the
# frame, so a 100 x 40 View with padding 8 painted only its 84 x 24 inner box
# (ticket ios-an-empty-view-with-a-background-paints-only-inside-its-padding;
# SwiftJsonUI Dynamic skips the padding in the same case). Everything else
# keeps its padding: a spacer (Color.clear), a View with children.
RSpec.describe 'sjui codegen: an empty View painted by its fill takes no padding' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emit(node)
    factory = SjuiTools::SwiftUI::ConverterFactory.new
    factory.create_converter(node, 0, nil, factory).convert.to_s
  end

  FILL_SPEC_BOX = { 'type' => 'View', 'width' => 100, 'height' => 40, 'padding' => 8 }.freeze

  it 'a background fill: no padding' do
    out = emit(FILL_SPEC_BOX.merge('background' => '#FFDD00'))
    expect(out.lines.first.strip).to eq('Rectangle()')
    expect(out).not_to include('.padding(')
  end

  it 'a pressed background fill: no padding' do
    out = emit(FILL_SPEC_BOX.merge('background' => '#FFDD00', 'tapBackground' => '#000000', 'onClick' => '@{tap}'))
    expect(out.lines.first.strip).to start_with('PressedFill(')
    expect(out).not_to include('.padding(')
  end

  # The same padding on the other side of the boundary keeps it.
  it 'a spacer keeps its padding (control)' do
    out = emit(FILL_SPEC_BOX)
    expect(out.lines.first.strip).to eq('Color.clear')
    expect(out).to include('.padding(')
  end

  it 'a View with children keeps its padding (control)' do
    out = emit(FILL_SPEC_BOX.merge('background' => '#FFDD00', 'child' => [{ 'type' => 'Label', 'text' => 'a' }]))
    expect(out).to include('.padding(')
  end

  it 'every case compiles' do
    codes = [FILL_SPEC_BOX.merge('background' => '#FFDD00'),
             FILL_SPEC_BOX.merge('background' => '#FFDD00', 'tapBackground' => '#000000', 'onClick' => '@{tap}'),
             FILL_SPEC_BOX].map { |n| emit(n) }
    # PressedFill / tracksPress transcribed from PressedBackground.swift, as
    # tap_background_is_the_pressed_background_spec does.
    stubs = <<~SWIFT
      extension View {
          func tracksPress(enabled: Bool = true) -> some View { self }
          func pressedBackground(_ pressed: Color, base: Color? = nil) -> some View { self }
      }
      struct PressedFill: View {
          init(pressed: Color, base: Color? = nil) {}
          var body: some View { EmptyView() }
      }
    SWIFT
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}", data: ['var tap: (() -> Void)? = nil'], stubs: stubs)).to compile_as_swift
  end
end
