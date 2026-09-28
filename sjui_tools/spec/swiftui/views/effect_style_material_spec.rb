# frozen_string_literal: true

require 'swiftui/converter_factory'

# `common.effectStyle` on a node that is not a Blur.
#
# The attribute is declared on `common`, so every node takes it, and android
# (kjui modifier_builder) and web (rjui base_converter) draw a non-Blur node's
# material. sjui read it only in blur_converter.rb, so a View emitted exactly
# its control for every value — the ios `unread-spelling` row the
# codegen-effect gate carried for common.effectStyle.
#
# The material goes through the ONE library table the Blur converter calls
# (`jsonUIVisualEffect` / `VisualEffectStyle`), in the :glass slot, ahead of
# the glass call: a material over whatever background is already there, clipped
# by :corner_radius. The Dynamic runtime's `glass` stage applies the two in the
# same order.
RSpec.describe 'common.effectStyle on a non-Blur node (SwiftUI codegen)' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emit(component)
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter(component).convert.to_s
  end

  def view(extra = {})
    { 'type' => 'View', 'width' => 100, 'height' => 40 }.merge(extra)
  end

  it 'emits nothing when effectStyle is absent (the control is unchanged)' do
    expect(emit(view)).not_to include('jsonUIVisualEffect')
  end

  %w[Thick Regular Thin UltraThin Chrome Prominent Light Dark ExtraLight].each do |spelling|
    it "routes #{spelling} through the library table" do
      expect(emit(view('effectStyle' => spelling))).to include(".jsonUIVisualEffect(\"#{spelling}\")")
    end
  end

  # The system*Material names are declared valueAliases; the library folds
  # them (VisualEffectStyle.from), so the spelling is forwarded as written.
  %w[systemMaterial systemUltraThinMaterial systemThinMaterial systemThickMaterial systemChromeMaterial].each do |spelling|
    it "forwards the valueAlias #{spelling} as written" do
      expect(emit(view('effectStyle' => spelling))).to include(".jsonUIVisualEffect(\"#{spelling}\")")
    end
  end

  it 'gives every declared spelling a different emission (no value draws the control)' do
    spellings = %w[Thick Regular Thin UltraThin Chrome Prominent Light Dark ExtraLight]
    outputs = spellings.map { |s| emit(view('effectStyle' => s)) }
    expect(outputs.uniq.length).to eq(spellings.length)
    expect(outputs).not_to include(emit(view))
  end

  it 'draws the default for a binding instead of emitting the binding text' do
    code = emit(view('effectStyle' => '@{material}'))
    expect(code).to include('.jsonUIVisualEffect(nil)')
    expect(code).not_to include('@{material}')
  end

  # Label, Button and SelectBox assemble their own chain and call only
  # apply_common_decorations, which registers the material as well.
  [
    { 'type' => 'Label', 'text' => 'hi' },
    { 'type' => 'Button', 'text' => 'go' },
    { 'type' => 'Image', 'srcName' => 'star', 'width' => 20, 'height' => 20 }
  ].each do |node|
    it "reaches a #{node['type']} too" do
      code = emit(node.merge('effectStyle' => 'Thin'))
      expect(code.scan('.jsonUIVisualEffect("Thin")').length).to eq(1)
    end
  end

  it 'leaves a Blur to its own declaration (one call, from BlurConverter)' do
    code = emit({ 'type' => 'Blur', 'effectStyle' => 'Dark' })
    expect(code.scan('.jsonUIVisualEffect(').length).to eq(1)
    expect(code).to include('.jsonUIVisualEffect("Dark")')
  end

  it 'sits behind a declared background and before the corner clip' do
    # A View with a child: an empty one paints its background as the
    # Rectangle's fill, which the material then sits behind as well.
    code = emit(view('effectStyle' => 'Thick', 'background' => '#00FF00', 'cornerRadius' => 8,
                     'child' => [{ 'type' => 'View', 'width' => 10, 'height' => 10 }]))
    bg = code.index('.background(')
    material = code.index('.jsonUIVisualEffect(')
    clip = code.index('.cornerRadius(')
    expect([bg, material, clip]).to all(be_truthy)
    expect(bg).to be < material
    expect(material).to be < clip
  end

  it 'shares the :glass slot with glass, the material first' do
    code = emit(view('effectStyle' => 'Thin', 'glass' => true))
    material = code.index('.jsonUIVisualEffect("Thin")')
    glass = code.index('.sjuiGlassEffect(')
    expect([material, glass]).to all(be_truthy)
    expect(material).to be < glass
  end

  it 'keeps glass alone in the slot unchanged when no effectStyle is declared' do
    code = emit(view('glass' => true))
    expect(code).to include('.sjuiGlassEffect()')
    expect(code).not_to include('jsonUIVisualEffect')
  end
end
