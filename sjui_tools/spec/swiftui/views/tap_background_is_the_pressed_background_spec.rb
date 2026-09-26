# frozen_string_literal: true

require 'swiftui/views/view_converter'
require 'swiftui/views/label_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require 'swiftui/binding/view_binding_handler'
require_relative '../../support/emitted_swift'

# tapBackground is the background while pressed, on every node with a tap
# (onClick) and on a Button (jsonui-cli 1.9.0). A Button drew it
# (StateAwareButtonView). Every other node drew nothing for a literal value, and
# a bound one became `.background(…)` in the background slot — the node's
# background at rest, replaced by the pressed colour, permanently.
#
# A node with a tap now draws it in two halves (SwiftJsonUI
# PressedBackground.swift): `.pressedBackground(pressed, base:)` in the
# background slot, and `.tracksPress()` after the tap gesture, which holds the
# press and hands it down. A node without a tap draws neither.
RSpec.describe 'sjui: tapBackground is the background while a node with a tap is pressed' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  TAPBG_RED = 'SwiftJsonUIConfiguration.shared.getColor(for: "#FF0000") ?? Color.black'
  TAPBG_BLUE = 'SwiftJsonUIConfiguration.shared.getColor(for: "#0000FF") ?? Color.black'

  def view(extra)
    node = { 'type' => 'View', 'width' => 50, 'height' => 20, 'child' => [{ 'type' => 'Label', 'text' => 'a' }] }
    SjuiTools::SwiftUI::Views::ViewConverter.new(node.merge(extra)).convert
  end

  def label(extra)
    SjuiTools::SwiftUI::Views::LabelConverter.new({ 'type' => 'Label', 'text' => 'x' }.merge(extra)).convert
  end

  it 'a View with a tap draws it in the background slot and tracks the press after the tap' do
    code = view('onClick' => '@{t}', 'tapBackground' => '#FF0000', 'background' => '#0000FF')
    expect(code).to include(".pressedBackground(#{TAPBG_RED}, base: #{TAPBG_BLUE})")
    expect(code).not_to include(".background(#{TAPBG_BLUE})")
    frame = code.index('.frame(')
    pressed = code.index('.pressedBackground(')
    tap = code.index('.onTapGesture')
    tracks = code.index('.tracksPress()')
    expect([frame, pressed, tap, tracks]).to all(be_a(Integer)), code
    expect(frame).to be < pressed
    expect(pressed).to be < tap
    expect(tap).to be < tracks
  end

  it 'a Label with a tap draws it, over no background' do
    code = label('onClick' => '@{t}', 'tapBackground' => '#FF0000')
    expect(code).to include(".pressedBackground(#{TAPBG_RED})")
    expect(code).to include('.tracksPress()')
  end

  it 'an empty View with a tap fills with it while pressed' do
    node = { 'type' => 'View', 'width' => 50, 'height' => 20, 'onClick' => '@{t}', 'tapBackground' => '#FF0000', 'background' => '#0000FF' }
    code = SjuiTools::SwiftUI::Views::ViewConverter.new(node).convert
    expect(code).to include("PressedFill(pressed: #{TAPBG_RED}, base: #{TAPBG_BLUE})")
    expect(code).not_to match(/^\s*Rectangle\(\)\s*$/)
    expect(code).to include('.tracksPress()')
  end

  # A node without a tap is not pressed: neither half, and its background is
  # its background.
  it 'a node without a tap draws neither half' do
    [view('tapBackground' => '#FF0000', 'background' => '#0000FF'), label('tapBackground' => '#FF0000')].each do |code|
      expect(code).not_to include('pressedBackground')
      expect(code).not_to include('tracksPress')
      expect(code).not_to include(TAPBG_RED)
    end
    expect(view('tapBackground' => '#FF0000', 'background' => '#0000FF')).to include(".background(#{TAPBG_BLUE})")
  end

  # The regression: a bound tapBackground became the background at rest.
  it 'a bound tapBackground is not the background at rest' do
    handler = SjuiTools::SwiftUI::Binding::ViewBindingHandler.new
    %w[tapBackground highlightBackground].each do |attr|
      expect(handler.send(:handle_common_binding, { 'type' => 'View' }, attr, '@{tb}')).to be_nil
    end
    code = view('tapBackground' => '@{tb}', 'background' => '#0000FF')
    expect(code).not_to include('data.tb')
  end

  it 'a bound canTap gates the press with the tap' do
    code = view('onClick' => '@{t}', 'canTap' => '@{c}', 'tapBackground' => '@{tb}')
    expect(code).to include('.pressedBackground(SwiftJsonUIConfiguration.shared.getColor(for: data.tb)')
    expect(code).to include('.tracksPress(enabled: (data.c ?? false))')
  end

  it 'canTap false, enabled false and no handler: no tap, so no pressed colour' do
    [{ 'onClick' => '@{t}', 'canTap' => false }, { 'onClick' => '@{t}', 'enabled' => false }, { 'onClick' => '' }].each do |extra|
      code = view(extra.merge('tapBackground' => '#FF0000'))
      expect(code).not_to include('pressedBackground'), extra.inspect
      expect(code).not_to include('tracksPress'), extra.inspect
    end
  end

  # View: `highlighted` swaps the background to highlightBackground; pressed,
  # tapBackground replaces whichever it is.
  it 'on a highlighted View the pressed colour replaces the highlight' do
    code = view('onClick' => '@{t}', 'highlighted' => '@{h}', 'highlightBackground' => '#00FF00', 'tapBackground' => '#FF0000')
    expect(code).to include(".pressedBackground(#{TAPBG_RED}, base: data.h ? ")
  end

  # ⚠️ Against stubs: the three declarations below are transcribed from
  # SwiftJsonUI Sources/SwiftJsonUI/Classes/SwiftUI/Components/
  # PressedBackground.swift — a transcription, not a compile against it. The
  # SwiftJsonUI ConformanceHost pastes this emission and builds it against
  # the library.
  it 'compiles as emitted' do
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
    data = ['var t: (() -> Void)? = nil', 'var c: Bool? = nil', 'var tb: String = ""', 'var h: Bool = false']
    [
      view('onClick' => '@{t}', 'tapBackground' => '#FF0000', 'background' => '#0000FF'),
      view('onClick' => '@{t}', 'canTap' => '@{c}', 'tapBackground' => '@{tb}'),
      view('onClick' => '@{t}', 'highlighted' => '@{h}', 'highlightBackground' => '#00FF00', 'tapBackground' => '#FF0000'),
      label('onClick' => '@{t}', 'tapBackground' => '#FF0000'),
      SjuiTools::SwiftUI::Views::ViewConverter.new({ 'type' => 'View', 'width' => 50, 'height' => 20, 'onClick' => '@{t}',
                                                     'tapBackground' => '#FF0000', 'background' => '#0000FF' }).convert
    ].each do |code|
      expect(compilable_view(code, data: data, stubs: stubs)).to compile_as_swift
    end
  end
end
