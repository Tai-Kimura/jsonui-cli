# frozen_string_literal: true

require 'swiftui/views/view_converter'
require 'swiftui/views/label_converter'
require 'swiftui/views/responsive_helper'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

# A wrapContent axis with a max sizes to its content, capped by the max (the
# user's ruling, 2026-09-27). `.frame(maxWidth:)` takes the width it is
# offered up to the max, so a wrapContent chip — maxWidth 160, minHeight 36,
# paddings [5, 16], 13pt medium, the text "chip" — was 160 wide on iOS
# (generated and Dynamic) where Compose drew 57dp and the web 58.4px.
# `.contentFit(_:)` (SwiftJsonUI 10.29.0) gives the view its ideal size on that
# axis — the frame's: the content's, clamped to the max — capped by the
# parent, so a longer text still wraps at the max.
#
# The drawn arm is WrapMaxProbeUITests in SwiftJsonUI's ConformanceHost; the
# Dynamic half is DynamicModifierHelper.applyFrameConstraints.
RSpec.describe SjuiTools::SwiftUI::Views::FrameHelper do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emit(node)
    factory = SjuiTools::SwiftUI::ConverterFactory.new
    factory.create_converter(node, 0, nil, factory).convert.to_s
  end

  CHIP = { 'type' => 'Label', 'text' => 'chip', 'width' => 'wrapContent', 'maxWidth' => 160, 'minHeight' => 36, 'paddings' => [5, 16] }.freeze

  it 'a wrapContent width with a maxWidth: the content fit right after the bounds frame' do
    lines = emit(CHIP).lines.map(&:strip)
    frame = lines.index { |l| l.start_with?('.frame(maxWidth: 160') }
    expect(frame).not_to be_nil
    expect(lines[frame + 1]).to eq('.contentFit(.horizontal)')
  end

  it 'a wrapContent height with a maxHeight, and an undeclared size, fit too; a bound max also caps' do
    expect(emit({ 'type' => 'View', 'child' => [{ 'type' => 'Label', 'text' => 'a' }], 'width' => 'matchParent', 'maxHeight' => 500 }))
      .to include('.contentFit(.vertical)')
    expect(emit(CHIP.merge('maxWidth' => '@{cap}'))).to include('.contentFit(.horizontal)')
  end

  it 'a responsive container: the branch that caps a wrapContent width fits it' do
    expect(SjuiTools::SwiftUI::Views::ResponsiveHelper.build_responsive_modifiers({ 'maxWidth' => 400 }, nil))
      .to eq(['.frame(maxWidth: 400, alignment: .topLeading)', '.contentFit(.horizontal)'])
  end

  it 'control: a declared width, a max of matchParent, and a min alone do not fit' do
    expect(emit(CHIP.merge('width' => 200))).not_to include('.contentFit')
    expect(emit(CHIP.merge('width' => 'matchParent'))).not_to include('.contentFit')
    expect(emit(CHIP.merge('maxWidth' => 'matchParent'))).not_to include('.contentFit')
    expect(emit(CHIP.reject { |k, _| k == 'maxWidth' })).not_to include('.contentFit')
  end

  it 'type-checks the modifier it emits', :swift_compile do
    codes = [emit(CHIP), emit({ 'type' => 'View', 'child' => [{ 'type' => 'Label', 'text' => 'a' }], 'maxWidth' => 200, 'maxHeight' => 80 })]
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}")).to compile_as_swift
  end
end
