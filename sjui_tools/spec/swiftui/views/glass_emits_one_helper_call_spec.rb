# frozen_string_literal: true

# `glass` is declared on `common` with `platform: swift` and
# `mode: ["uikit", "swiftui"]` — the first declaration in the file to pair
# those two modes. This is the SwiftUI codegen half.
#
# 🔻 ONE HELPER CALL, NEVER AN `if #available` IN GENERATED CODE.
# `.glassEffect` is `@available(iOS 26.0, …)`, so something has to check.
# Putting the check in the emitted source would copy it to every site that
# declares `glass`, and each copy asks the RUNNING OS — the rendered picture
# would then depend on the device, which is how a fallback stopped being
# reproducible in b7056242 and had to come out. The library holds the single
# check; this emitter writes `.sjuiGlassEffect(…)` and nothing else.
# (Ruling: iOS lane, 2026-09-14.)
#
# 🔻 `shape` IS PASSED THROUGH, NOT RESOLVED.
# `rounded(N)` and `rect` could be resolved statically. `capsule` and
# `circle` cannot — they depend on the laid-out height, which codegen does
# not know. Resolving the two that are knowable would split one mapping
# across two layers by an accident of what is statically available, so all
# four go to the helper as a string.
#
# ⚠️ THE DECLARED SET IS NOT HONOURED BY BOTH MODES, measured from the SDK:
#   SwiftUI  SwiftUICore.Glass       regular / clear / identity, and
#            `.glassEffect(_:in:)`   takes a shape          -> all four keys
#   UIKit    UIGlassEffectStyle      Regular / Clear only (no identity), and
#            UIGlassEffect is a UIVisualEffect subclass with NO shape
# So `identity` and `shape` are SwiftUI-only. This file is the SwiftUI path
# and passes everything through; the UIKit limits belong in the declaration's
# prose, one sentence per limit with the mode as its subject.

require 'swiftui/views/blur_converter'

RSpec.describe 'glass on the SwiftUI codegen path' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all)  { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  # Any converter that inherits the common modifier pass will do; Blur takes a
  # single argument, so it is the cheapest host for a `common` attribute.
  def emit(component)
    SjuiTools::SwiftUI::Views::BlurConverter.new({ 'type' => 'Blur' }.merge(component)).convert.to_s
  end

  def glass_line(component)
    emit(component).lines.map(&:strip).find { |l| l.include?('sjuiGlassEffect') }
  end

  describe 'when the attribute is not asking for glass' do
    it 'emits nothing when absent' do
      expect(glass_line({})).to be_nil
    end

    it 'emits nothing for false' do
      expect(glass_line('glass' => false)).to be_nil
    end

    it 'emits nothing for the string "false"' do
      # JSON from a layout can carry either; `true`/`false` arrive as strings
      # through some bound paths.
      expect(glass_line('glass' => 'false')).to be_nil
    end
  end

  describe 'the boolean form' do
    it 'emits the helper with no arguments' do
      expect(glass_line('glass' => true)).to eq('.sjuiGlassEffect()')
    end
  end

  describe 'the object form' do
    it 'passes style through' do
      expect(glass_line('glass' => { 'style' => 'clear' }))
        .to eq('.sjuiGlassEffect(style: "clear")')
    end

    it 'passes shape through unresolved, including the height-dependent ones' do
      expect(glass_line('glass' => { 'shape' => 'capsule' }))
        .to eq('.sjuiGlassEffect(shape: "capsule")')
      expect(glass_line('glass' => { 'shape' => 'rounded(12)' }))
        .to eq('.sjuiGlassEffect(shape: "rounded(12)")')
    end

    it 'emits interactive: false rather than dropping it' do
      # `false` is a value the author wrote, not an absence. The helper's own
      # default is what an ABSENT key means, and the two must stay
      # distinguishable in the generated source.
      expect(glass_line('glass' => { 'interactive' => false }))
        .to eq('.sjuiGlassEffect(interactive: false)')
    end

    it 'routes tint through the colour helper, not as a raw string' do
      line = glass_line('glass' => { 'tint' => '#FF0000' })
      expect(line).to include('tint: ')
      expect(line).not_to include('tint: "#FF0000"'), 'the hex reached Swift as a string literal'
      expect(line).to include('#FF0000')
    end

    it 'emits all four keys in a stable order' do
      line = glass_line('glass' => { 'style' => 'regular', 'tint' => '#FF0000',
                                     'interactive' => true, 'shape' => 'capsule' })
      expect(line).to match(/\A\.sjuiGlassEffect\(style: .*, tint: .*, interactive: true, shape: .*\)\z/)
    end
  end

  describe 'what the generated code must NOT contain' do
    it 'never writes an availability check into the output' do
      %w[true regular].each do |_|
        out = emit('glass' => { 'style' => 'regular', 'shape' => 'capsule' })
        expect(out).not_to include('#available'),
                           'an availability check in generated code is duplicated per site ' \
                           'and asks the running OS, making the picture device-dependent'
        expect(out).not_to include('@available')
      end
    end

    it 'never writes the SwiftUI API directly' do
      out = emit('glass' => true)
      expect(out).not_to include('.glassEffect('),
                         'codegen must go through the library helper so the availability ' \
                         'check and the shape resolution live in one place'
      expect(out).not_to include('Glass.regular')
      expect(out).not_to include('UIGlassEffect')
    end

    it 'emits exactly one helper call per component' do
      out = emit('glass' => { 'style' => 'regular' })
      expect(out.scan('sjuiGlassEffect').size).to eq(1)
    end
  end

  describe 'where it sits among the other modifiers' do
    it 'comes after background and before cornerRadius' do
      # `.glassEffect` renders over whatever background is there and carries
      # its own shape, so it belongs between the background entries and the
      # clip. Asserted on the emitted order rather than on the constant, so a
      # reordering of MODIFIER_ORDER that changes the output fails here.
      out = emit('glass' => true, 'background' => '#00FF00', 'cornerRadius' => 8)
      bg    = out.index('.background(')
      glass = out.index('.sjuiGlassEffect(')
      clip  = out.index('.cornerRadius(')
      expect([bg, glass, clip]).to all(be_truthy)
      expect(bg).to be < glass
      expect(glass).to be < clip
    end

    it 'the slot exists in the declared order' do
      order = SjuiTools::SwiftUI::Views::ModifierBag::MODIFIER_ORDER
      expect(order).to include(:glass)
      expect(order.index(:gradient)).to be < order.index(:glass)
      expect(order.index(:glass)).to be < order.index(:corner_radius)
    end
  end
end
