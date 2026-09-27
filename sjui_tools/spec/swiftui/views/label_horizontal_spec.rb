# frozen_string_literal: true

require 'swiftui/views/label_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

# Where a Label's text sits across a frame wider than it: textAlign, else the
# horizontal part of its gravity (center / centerHorizontal, right, left), else
# the start — the SSoT's Label.textAlign; the user ruled "align iOS to start"
# (4f round 6, 2026-09-27). The lines of a multi-line Label follow the same
# rule (PartialAttributedText's textAlignment). Measured 2026-09-27
# (ConformanceHost, iOS 26.5): until jsonui-cli 1.9.0 a fixed-width Label with
# neither textAlign nor gravity drew its text in the middle ("Mon" in 50,
# "Peaty" in 70, 200 x 44), a gravity right one at the start ("7" in 32, a
# matchParent or weighted one), a gravity center one at the start, and a
# gravity center multi-line one's lines at the start.
#
# The drawn arm is LabelHorizontalProbeUITests in SwiftJsonUI's
# ConformanceHost; the Dynamic half is DynamicModifierHelper.labelHorizontal.
RSpec.describe SjuiTools::SwiftUI::Views::LabelConverter do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emit(attrs)
    factory = SjuiTools::SwiftUI::ConverterFactory.new
    factory.create_converter({ 'type' => 'Label', 'text' => 'Go' }.merge(attrs), 0, nil, factory).convert.to_s
  end

  it 'a fixed width with neither textAlign nor gravity: the start' do
    expect(emit('width' => 50)).to include('.frame(width: 50, alignment: .topLeading)')
    expect(emit('width' => 200, 'height' => 44)).to include('.frame(width: 200, height: 44, alignment: .leading)')
    expect(emit('width' => 70, 'height' => 'matchParent')).to include('.frame(width: 70, alignment: .topLeading)')
  end

  it "without textAlign, gravity's horizontal part" do
    expect(emit('width' => 32, 'gravity' => 'right')).to include('.frame(width: 32, alignment: .trailing)')
    expect(emit('width' => 200, 'gravity' => 'center')).to include('.frame(width: 200, alignment: .center)')
    expect(emit('width' => 200, 'gravity' => 'centerHorizontal')).to include('.frame(width: 200, alignment: .center)')
    expect(emit('width' => 200, 'height' => 44, 'gravity' => 'right')).to include('.frame(width: 200, height: 44, alignment: .trailing)')
    expect(emit('width' => 'matchParent', 'gravity' => 'right')).to include('.frame(maxWidth: .infinity, alignment: .trailing)')
    expect(emit('width' => 0, 'weight' => 1, 'gravity' => 'right', 'parent_orientation' => 'horizontal'))
      .to include('.frame(maxWidth: .infinity, alignment: .trailing)')
  end

  it "the lines of a multi-line Label follow it: textAlign, else gravity's horizontal part, else the start" do
    expect(emit('lines' => 0)).to include('textAlignment: .leading')
    expect(emit('lines' => 0, 'gravity' => 'center')).to include('textAlignment: .center')
    expect(emit('lines' => 0, 'gravity' => 'right')).to include('textAlignment: .trailing')
    expect(emit('lines' => 0, 'gravity' => 'right', 'textAlign' => 'center')).to include('textAlignment: .center')
  end

  it 'control: textAlign owns the horizontal, and a named left stays at the start' do
    expect(emit('width' => 200, 'textAlign' => 'center')).to include('.frame(width: 200, alignment: .center)')
    expect(emit('width' => 200, 'textAlign' => 'right', 'gravity' => 'left')).to include('.frame(width: 200, alignment: .trailing)')
    expect(emit('width' => 200, 'gravity' => 'left')).to include('.frame(width: 200, alignment: .topLeading)')
  end

  it 'type-checks the alignments it emits', :swift_compile do
    codes = [{ 'width' => 50 }, { 'width' => 200, 'height' => 44 }, { 'width' => 32, 'gravity' => 'right' },
             { 'width' => 200, 'gravity' => 'center' }, { 'lines' => 0, 'gravity' => 'center' },
             { 'width' => 0, 'weight' => 1, 'gravity' => 'right', 'parent_orientation' => 'horizontal' }].map { |a| emit(a) }
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}")).to compile_as_swift
  end
end
