# frozen_string_literal: true

require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'
require 'core/tap_accessibility'
require 'core/image_accessibility'
require 'json'

# Every tap sjui emits obeys the gates attribute_definitions.json declares on
# it, static and bound: `canTap` (common.canTap, the SwiftUI tap gate) as
# `.allowsHitTesting`, `enabled` as `.disabled` — and, under a bound canTap,
# the button trait only while the gate is open, which is what the dynamic
# runtime does (it attaches neither the tap nor its traits while the binding
# is false).
#
# A Label read neither `canTap: false` nor a bound `enabled` — it builds its
# own modifiers — and a bound canTap gated nothing on the types whose
# converters do not process bindings (IconLabel, GradientView, CircleView,
# Blur, Progress, the image aliases and the interactive types). One method,
# `register_interaction_gates`, now emits the gates for all of them.
#
# Driven by the tap rule's own list of types, each node annotated as `jui
# build` annotates it (image roles, then tap shapes) before conversion.
RSpec.describe 'sjui tap gates on every tap' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  tap = JsonUIShared::TapAccessibility

  # Types the tap rule counts as a tap for which no `.onTapGesture` is
  # emitted: a Button's tap is its action; the text inputs, SelectBox and
  # Embed take no onClick. Pinned, so a type joining or leaving is seen.
  no_gesture = %w[TextField EditText Input TextView Button SelectBox Embed]

  extra = {
    'Image' => { 'srcName' => 'x' }, 'CircleImage' => { 'srcName' => 'x' },
    'NetworkImage' => { 'url' => 'https://e/x.png' }, 'Label' => { 'text' => 't' },
    'Text' => { 'text' => 't' }, 'IconLabel' => { 'text' => 't' }, 'Button' => { 'text' => 't' },
    'SelectBox' => { 'items' => ['a'] }, 'Segment' => { 'items' => ['a'] }
  }

  emit = lambda do |type, gate, more = {}|
    comp = { 'type' => type, 'id' => 'n', 'onClick' => '@{onTap}' }.merge(extra[type] || {}).merge(gate).merge(more)
    comp = JSON.parse(JSON.generate(comp))
    JsonUIShared::ImageAccessibility.annotate!(comp, source_path: 'probe.json')
    tap.annotate!(comp)
    [SjuiTools::SwiftUI::ConverterFactory.new.create_converter(comp).convert.to_s, comp]
  end

  types = tap::KNOWN_TYPES.uniq

  it 'emits a tap gesture for every type the tap rule calls a tap, but these' do
    silent = types.reject { |type| emit.call(type, {}).first.include?('.onTapGesture') }
    expect(silent).to match_array(no_gesture)
  end

  (types - no_gesture).each do |type|
    describe type do
      it 'canTap: false shuts the tap, and it is no button' do
        code, = emit.call(type, 'canTap' => false)
        expect(code).to include('.allowsHitTesting(false)')
        expect(code).not_to include('.isButton')
      end

      it 'a bound canTap gates the tap, and the button trait with it' do
        code, comp = emit.call(type, 'canTap' => '@{c}')
        expect(code).to include('.onTapGesture')
        expect(code).to include('.allowsHitTesting((data.c ?? false))')
        expect(code).not_to include('.accessibilityAddTraits(.isButton)')
        if %w[button combine].include?(comp[tap::SHAPE_KEY])
          expect(code).to include('.accessibilityAddTraits((data.c ?? false) ? AccessibilityTraits.isButton : [])')
        else
          expect(code).not_to include('.isButton')
        end
      end

      it 'enabled: false leaves no tap it does not disable' do
        code, = emit.call(type, 'enabled' => false)
        expect(!code.include?('.onTapGesture') || code.include?('.disabled(true)')).to be(true), code
      end

      it 'a bound enabled disables it' do
        code, = emit.call(type, 'enabled' => '@{on}')
        expect(code).to include('.disabled(!((data.on ?? false)))')
      end
    end
  end

  it 'joins the gates that meet on one view into one condition' do
    code, = emit.call('Label', { 'canTap' => '@{c}', 'userInteractionEnabled' => '@{u}' })
    expect(code.scan('.allowsHitTesting(').size).to eq(1)
    expect(code).to include('.allowsHitTesting((data.u ?? false) && (data.c ?? false))')
    code, = emit.call('View', { 'canTap' => '@{c}', 'touchDisabledState' => true })
    expect(code.scan('.allowsHitTesting(').size).to eq(1)
    expect(code).to include('.allowsHitTesting(false)')
  end

  {
    'a Label under a bound canTap and a bound enabled' => ['Label', {}],
    'a View holding a Label, combined into one button' => ['View', { 'child' => [{ 'type' => 'Label', 'text' => 'x' }] }]
  }.each do |name, (type, more)|
    it "#{name}: the emitted Swift compiles" do
      code, = emit.call(type, { 'canTap' => '@{c}', 'enabled' => '@{on}' }, more)
      expect(code).to include('AccessibilityTraits.isButton : []')
      data = ['var onTap: (() -> Void)? = nil', 'var c: Bool? = nil', 'var on: Bool? = nil']
      expect(compilable_view(code, data: data)).to compile_as_swift
    end
  end
end
