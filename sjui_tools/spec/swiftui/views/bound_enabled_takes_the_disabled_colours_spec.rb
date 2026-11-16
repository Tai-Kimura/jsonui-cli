# frozen_string_literal: true

require 'swiftui/views/base_view_converter'
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

# The disabled colours follow `enabled` whether it is written or bound (ticket
# 2026-10-23-bound-enabled-disabled-colors-three-faces). A bound `enabled`
# used to take the base colour always: only a literal `enabled: false` drew
# disabledBackground or disabledFontColor. Now the emit chooses by the
# binding — the base while it is true, the disabled colour while it is false —
# on each surface a View paints (a Rectangle's fill, a PressedFill's base, a
# container's background) and on a Label's font colour.
#
# The drawn arm is DisabledColoursProbeUITests in SwiftJsonUI's
# ConformanceHost (the codegen host builds this emission against the library
# and reads the pixels with `enabled` true and false); this one keeps the
# direction of the choice in jsonui-cli's own gate.
module BoundEnabledColourExprs
  def base_bg = 'SwiftJsonUIConfiguration.shared.getColor(for: "#0000FF") ?? Color.black'
  def bound_bg = 'SwiftJsonUIConfiguration.shared.getColor(for: data.bg) ?? Color.clear'
  def grey = 'SwiftJsonUIConfiguration.shared.getColor(for: "#999999") ?? Color.black'
  def base_fg = 'SwiftJsonUIConfiguration.shared.getColor(for: "#123456") ?? Color.black'
  def dim = 'SwiftJsonUIConfiguration.shared.getColor(for: "#555555") ?? Color.black'
  def on_ = '(data.on ?? false)'
end

RSpec.describe 'sjui disabled colours follow a bound enabled' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  include BoundEnabledColourExprs

  def emit(node)
    factory = SjuiTools::SwiftUI::ConverterFactory.new
    factory.create_converter(node, 0, nil, factory).convert.to_s
  end

  def view(extra)
    emit({ 'type' => 'View', 'width' => 60, 'height' => 40, 'disabledBackground' => '#999999' }.merge(extra))
  end

  def label(extra)
    emit({ 'type' => 'Label', 'text' => 'x', 'disabledFontColor' => '#555555' }.merge(extra))
  end

  def choice(base, disabled) = "(#{on_} ? #{base} : #{disabled})"

  describe 'a View' do
    it 'a bound enabled: the base while true, disabledBackground while false (fixed and bound base)' do
      expect(view('background' => '#0000FF', 'enabled' => '@{on}')).to include(".fill(#{choice(base_bg, grey)})")
      expect(view('background' => '@{bg}', 'enabled' => '@{on}')).to include(".fill(#{choice(bound_bg, grey)})")
    end

    it 'with children the background chooses the same way' do
      code = view('background' => '#0000FF', 'enabled' => '@{on}', 'child' => [{ 'type' => 'Label', 'text' => 'x' }])
      expect(code).to include(".background(#{choice(base_bg, grey)})")
    end

    it 'with a tapBackground the pressed fill takes the choice as its base' do
      code = view('background' => '#0000FF', 'enabled' => '@{on}', 'tapBackground' => '#00FF00', 'onClick' => '@{go}')
      expect(code).to include("base: #{choice(base_bg, grey)})")
    end

    it 'a literal false: disabledBackground alone, never the base' do
      code = view('background' => '#0000FF', 'enabled' => false)
      expect(code).to include(".fill(#{grey})")
      expect(code).not_to include('#0000FF')
    end

    it 'no enabled: the base alone, no choice' do
      code = view('background' => '#0000FF')
      expect(code).to include(".fill(#{base_bg})")
      expect(code).not_to include('#999999')
    end
  end

  describe 'a Label' do
    it 'a bound enabled: fontColor while true, disabledFontColor while false (fixed and bound base)' do
      expect(label('fontColor' => '#123456', 'enabled' => '@{on}')).to include("fontColor: #{choice(base_fg, dim)},")
      expect(label('fontColor' => '@{fg}', 'enabled' => '@{on}')).to include("fontColor: #{choice('data.fg', dim)},")
    end

    it 'a literal false: disabledFontColor alone, never the base' do
      code = label('fontColor' => '#123456', 'enabled' => false)
      expect(code).to include("fontColor: #{dim},")
      expect(code).not_to include('#123456')
    end
  end

  # ⚠️ Against stubs: PressedFill / tracksPress are transcribed from SwiftJsonUI
  # PressedBackground.swift (as tap_background_is_the_pressed_background_spec
  # transcribes them), and getColor(for:) takes Any in the library — the
  # overload below stands in for the bound colour's face. The ConformanceHost
  # builds this emission against the library itself.
  it 'compiles as emitted', :swift_compile do
    stubs = <<~SWIFT
      extension View {
          func tracksPress(enabled: Bool = true) -> some View { self }
      }
      struct PressedFill: View {
          init(pressed: Color, base: Color? = nil) {}
          var body: some View { EmptyView() }
      }
      extension SwiftJsonUIConfiguration {
          func getColor(for color: Color?) -> Color? { color }
      }
    SWIFT
    data = ['var on: Bool? = nil', 'var bg: String = ""', 'var fg: Color? = nil', 'var go: (() -> Void)? = nil']
    [
      view('background' => '#0000FF', 'enabled' => '@{on}'),
      view('background' => '@{bg}', 'enabled' => '@{on}'),
      view('background' => '#0000FF', 'enabled' => '@{on}', 'child' => [{ 'type' => 'Label', 'text' => 'x' }]),
      view('background' => '#0000FF', 'enabled' => '@{on}', 'tapBackground' => '#00FF00', 'onClick' => '@{go}'),
      label('fontColor' => '#123456', 'enabled' => '@{on}'),
      label('fontColor' => '@{fg}', 'enabled' => '@{on}')
    ].each do |code|
      expect(compilable_view(code, data: data, stubs: stubs)).to compile_as_swift
    end
  end
end
