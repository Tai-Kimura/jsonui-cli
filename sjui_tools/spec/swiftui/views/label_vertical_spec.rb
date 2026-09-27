# frozen_string_literal: true

require 'swiftui/views/label_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

# A Label's text in a box taller than it sits at the vertical its gravity
# names (top, bottom, centerVertical / center), else at the centre — the
# canon's leafOwnFrameChannel default for "a text block smaller than its fixed
# box" (attribute_semantics.json -> gravityDefaults). Measured 2026-09-27, a
# Label "Go" of height 44 (ConformanceHost, iOS 26.5): until jsonui-cli 1.9.0
# the position depended on the frame's shape — matchParent- or wrapContent-
# wide it was centred whatever the gravity (`top` and `bottom` did nothing);
# 200 wide, `left` / `right` put it at the top; matchParent × matchParent or a
# minHeight with no gravity, at the top. Its horizontal position is unchanged.
#
# The drawn arm is LabelVerticalProbeUITests in SwiftJsonUI's ConformanceHost;
# the Dynamic half is DynamicModifierHelper.labelVertical.
RSpec.describe SjuiTools::SwiftUI::Views::LabelConverter do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emit(attrs)
    factory = SjuiTools::SwiftUI::ConverterFactory.new
    factory.create_converter({ 'type' => 'Label', 'text' => 'Go' }.merge(attrs), 0, nil, factory).convert.to_s
  end

  HEIGHT_44 = '.frame(minHeight: 44, idealHeight: 44, maxHeight: 44'

  it 'a height-only frame: the vertical the gravity names' do
    expect(emit('width' => 'matchParent', 'height' => 44, 'gravity' => 'top')).to include("#{HEIGHT_44}, alignment: .top)")
    expect(emit('width' => 'matchParent', 'height' => 44, 'gravity' => 'bottom')).to include("#{HEIGHT_44}, alignment: .bottom)")
    expect(emit('width' => 'wrapContent', 'height' => 44, 'gravity' => 'top')).to include("#{HEIGHT_44}, alignment: .top)")
  end

  it 'a frame of both sizes: a horizontal gravity leaves the text centred vertically' do
    expect(emit('width' => 200, 'height' => 44, 'gravity' => 'left')).to include('.frame(width: 200, height: 44, alignment: .leading)')
    expect(emit('width' => 200, 'height' => 44, 'gravity' => 'right')).to include('.frame(width: 200, height: 44, alignment: .trailing)')
  end

  it 'a filled height or a height bound with gravity omitted: centred' do
    expect(emit('width' => 'matchParent', 'height' => 'matchParent'))
      .to include('.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)')
    expect(emit('width' => 'matchParent', 'minHeight' => 60)).to include('.frame(minHeight: 60, alignment: .leading)')
  end

  it 'control: centred or named as before, and a width-only frame spelled as before' do
    none = emit('width' => 'matchParent', 'height' => 44)
    expect(none).to include("#{HEIGHT_44})")
    expect(none).to include('.frame(maxWidth: .infinity, alignment: .topLeading)')
    expect(emit('width' => 200, 'height' => 44, 'gravity' => 'top')).to include('.frame(width: 200, height: 44, alignment: .topLeading)')
    expect(emit('width' => 200, 'height' => 44, 'gravity' => 'center', 'textAlign' => 'center'))
      .to include('.frame(width: 200, height: 44, alignment: .center)')
    expect(emit('width' => 'matchParent', 'height' => 'matchParent', 'gravity' => 'top'))
      .to include('.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)')
  end

  it 'type-checks the alignments it emits', :swift_compile do
    codes = [{ 'width' => 'matchParent', 'height' => 44, 'gravity' => 'top' }, { 'width' => 'matchParent', 'height' => 44, 'gravity' => 'bottom' },
             { 'width' => 200, 'height' => 44, 'gravity' => 'left' }, { 'width' => 'matchParent', 'height' => 'matchParent' },
             { 'width' => 'matchParent', 'minHeight' => 60 }].map { |a| emit(a) }
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}")).to compile_as_swift
  end
end
