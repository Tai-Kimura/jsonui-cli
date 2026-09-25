# frozen_string_literal: true

require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'
require 'core/tap_accessibility'
require 'core/image_accessibility'
require 'json'

# `canTap` (attribute_definitions.json common.canTap, the SwiftUI tap gate)
# stops the onClick / onclick handler's call and nothing else; `enabled`
# disables the view. On every type the tap rule calls a tap:
#
# - `canTap: false` emits exactly what the node emits with no onClick: no
#   tap, no button trait, and nothing that stops the view — a control's own
#   operation (a Switch switching, a Radio selecting) and the controls inside
#   a container are `enabled`'s.
# - A bound canTap emits exactly what the ungated node emits but for the
#   gesture that calls the handler, masked while the binding is false
#   (`.gesture(TapGesture()…, including: c ? .all : .subviews)`), and the
#   button trait, which follows the gate as the dynamic runtime's does.
# - A Button calls the handler from its action, gated there; it stays an
#   enabled button.
# - `enabled` is `.disabled`, outside the tap.
#
# The arms compare whole emissions, not the presence of a modifier. The gate
# was `.allowsHitTesting(c)` placed before `.contentShape` + `.onTapGesture`:
# present, and — measured on iOS 18.6 and 26.4 (SwiftJsonUI ConformanceHost,
# CanTapGateProbe) — it stopped the child's tap and not the view's own. An arm
# that looked for the modifier passed it.
#
# Driven by the tap rule's own list of types, each node annotated as `jui
# build` annotates it (image roles, then tap shapes) before conversion.
RSpec.describe 'sjui canTap stops the tap handler and nothing else' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  tap = JsonUIShared::TapAccessibility

  # Types the tap rule counts as a tap for which no tap gesture is emitted: a
  # Button's tap is its action; the text inputs, SelectBox and Embed take no
  # onClick. Pinned, so a type joining or leaving is seen.
  no_gesture = %w[TextField EditText Input TextView Button SelectBox Embed]

  extra = {
    'Image' => { 'srcName' => 'x' }, 'CircleImage' => { 'srcName' => 'x' },
    'NetworkImage' => { 'url' => 'https://e/x.png' }, 'Label' => { 'text' => 't' },
    'Text' => { 'text' => 't' }, 'IconLabel' => { 'text' => 't' }, 'Button' => { 'text' => 't' },
    'SelectBox' => { 'items' => ['a'] }, 'Segment' => { 'items' => ['a'] }
  }

  convert = lambda do |comp|
    comp = JSON.parse(JSON.generate(comp))
    JsonUIShared::ImageAccessibility.annotate!(comp, source_path: 'probe.json')
    tap.annotate!(comp)
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter(comp).convert.to_s
  end

  node = ->(type, more = {}) { { 'type' => type, 'id' => 'n' }.merge(extra[type] || {}).merge(more) }
  emit = ->(type, gate = {}, more = {}) { convert.call(node.call(type, { 'onClick' => '@{onTap}' }.merge(gate).merge(more))) }
  untapped = ->(type, more = {}) { convert.call(node.call(type, more)) }

  # The ungated emission with its tap gated by `c`: the gesture that calls
  # the handler masked, the button trait after it following the gate, and a
  # call the component makes from its own operation (a Radio's selection, a
  # CheckBox's value change, an IconLabel's action) run while `c` is true.
  gated = lambda do |code, call = 'data.onTap?()'|
    masked = nil
    code = code.sub(/\.onTapGesture \{\n(\s*)#{Regexp.escape(call)}\n(\s*)\}/) do
      masked = ".gesture(TapGesture().onEnded {\n#{Regexp.last_match(1)}#{call}\n#{Regexp.last_match(2)}}, " \
               'including: (data.c ?? false) ? .all : .subviews)'
      "\0MASKED\0"
    end
    code = code.gsub(call, "if (data.c ?? false) { #{call} }")
    at = code.index("\0MASKED\0")
    if at
      trait = code.index('.accessibilityAddTraits(.isButton)', at)
      code[trait, '.accessibilityAddTraits(.isButton)'.size] = '.accessibilityAddTraits((data.c ?? false) ? AccessibilityTraits.isButton : [])' if trait
      code = code.sub("\0MASKED\0", masked)
    end
    code
  end

  types = tap::KNOWN_TYPES.uniq

  it 'emits a tap gesture for every type the tap rule calls a tap, but these' do
    silent = types.reject { |type| emit.call(type).include?('.onTapGesture') }
    expect(silent).to match_array(no_gesture)
  end

  (types - no_gesture).each do |type|
    describe type do
      it 'canTap: false emits what no onClick emits' do
        expect(emit.call(type, 'canTap' => false)).to eq(untapped.call(type))
      end

      it 'a bound canTap masks the gesture that calls the handler, and changes nothing else' do
        expect(emit.call(type, 'canTap' => '@{c}')).to eq(gated.call(emit.call(type)))
      end

      it 'enabled: false leaves no tap it does not disable' do
        code = emit.call(type, 'enabled' => false)
        expect(!code.include?('data.onTap?()') || code.include?('.disabled(true)')).to be(true), code
      end

      it 'a bound enabled disables it outside its tap' do
        code = emit.call(type, 'enabled' => '@{on}')
        disabled_at = code.rindex('.disabled(!((data.on ?? false)))')
        expect(disabled_at).not_to be_nil, code
        expect(disabled_at).to be > code.index('data.onTap?()'), code
      end
    end
  end

  # The column the old gate failed: what a control does by itself, and the
  # controls inside a tappable container, under a shut or bound gate. The
  # emission of the control is the ungated one, and nothing in it stops hit
  # testing or disables. (Measured on iOS, CanTapGateProbe: a Switch under a
  # shut gate still switches; a child's tap still reaches its handler.)
  describe "a control's own operation" do
    controls = tap::INTERACTIVE_TYPES - no_gesture
    containers = {
      'a View holding a Switch' => ['View', { 'child' => [{ 'type' => 'Switch', 'id' => 's', 'isOn' => '@{on}' }] }],
      'a View holding a child with its own tap' =>
        ['View', { 'child' => [{ 'type' => 'View', 'id' => 'k', 'width' => 10, 'height' => 10, 'onClick' => '@{onKid}' }] }]
    }
    cases = controls.map { |type| [type, [type, {}]] } + containers.to_a

    cases.each do |name, (type, more)|
      it "#{name} under canTap false is what it is with no onClick" do
        expect(emit.call(type, { 'canTap' => false }, more)).to eq(untapped.call(type, more))
      end

      it "#{name} under a bound canTap: only its own tap is gated" do
        code = emit.call(type, { 'canTap' => '@{c}' }, more)
        expect(code).to eq(gated.call(emit.call(type, {}, more)))
        expect(code).not_to include('.allowsHitTesting')
        expect(code).not_to include('.disabled')
      end
    end

    it 'the child keeps its own tap, ungated' do
      _, (type, more) = containers.to_a.last
      code = emit.call(type, { 'canTap' => '@{c}' }, more)
      expect(code.scan(/\.onTapGesture \{\n\s*data\.onKid\?\(\)\n\s*\}/).size).to eq(1)
    end
  end

  describe 'the onclick spelling' do
    it 'canTap: false emits what no onclick emits' do
      expect(convert.call(node.call('View', 'onclick' => 'doIt', 'canTap' => false))).to eq(untapped.call('View'))
    end

    it 'a bound canTap masks the gesture that calls it' do
      open = convert.call(node.call('View', 'onclick' => 'doIt'))
      expect(convert.call(node.call('View', 'onclick' => 'doIt', 'canTap' => '@{c}'))).to eq(gated.call(open, 'data.doIt?()'))
    end
  end

  # A Button's tap is its action. canTap gates the handler's call in it; the
  # button is not disabled (that is `enabled`'s, `isEnabled:`).
  describe 'Button' do
    it 'canTap: false leaves the action empty and the button enabled' do
      code = emit.call('Button', 'canTap' => false)
      expect(code).to include('action: { }')
      expect(code).not_to include('onTap')
      expect(code).to include('isEnabled: true')
    end

    it 'a bound canTap gates the call inside the action, and changes nothing else' do
      open = emit.call('Button')
      expect(open).to include('action: { data.onTap?() }')
      expect(emit.call('Button', 'canTap' => '@{c}'))
        .to eq(open.sub('action: { data.onTap?() }', 'action: { if (data.c ?? false) { data.onTap?() } }'))
    end
  end

  it 'joins the view-wide gates on one view into one condition' do
    code = emit.call('Label', 'userInteractionEnabled' => '@{u}', 'touchDisabledState' => true)
    expect(code.scan('.allowsHitTesting(').size).to eq(1)
    expect(code).to include('.allowsHitTesting(false)')
    code = emit.call('View', 'userInteractionEnabled' => '@{u}')
    expect(code.scan('.allowsHitTesting(').size).to eq(1)
    expect(code).to include('.allowsHitTesting((data.u ?? false))')
  end

  gate_data = ['var onTap: (() -> Void)? = nil', 'var onKid: (() -> Void)? = nil', 'var c: Bool? = nil']
  {
    'a Label under a bound canTap and a bound enabled' => ['Label', {}],
    'a View holding a Label, combined into one button' => ['View', { 'child' => [{ 'type' => 'Label', 'text' => 'x' }] }],
    'a View holding a child with its own tap' =>
      ['View', { 'child' => [{ 'type' => 'View', 'id' => 'k', 'width' => 10, 'height' => 10, 'onClick' => '@{onKid}' }] }]
  }.each do |name, (type, more)|
    it "#{name}: the emitted Swift compiles" do
      code = emit.call(type, { 'canTap' => '@{c}', 'enabled' => '@{on}' }, more)
      expect(code).to include('including: (data.c ?? false) ? .all : .subviews)')
      expect(compilable_view(code, data: gate_data + ['var on: Bool? = nil'])).to compile_as_swift
    end
  end

  # StateAwareButtonView is SwiftJsonUI's; its init, as far as the emission
  # reaches (text:, action:, isEnabled: in that order — Swift rejects them
  # out of order), declared here. `isEnabled:` takes a Bool, which a bound
  # `enabled` passes as it is (swift_value_expr).
  button_stub = <<~SWIFT
    struct StateAwareButtonView: View {
        init(text: String, action: @escaping () -> Void, isEnabled: Bool = true) {}
        var body: some View { EmptyView() }
    }
  SWIFT

  it 'a Button under a bound canTap and a bound enabled: the emitted Swift compiles' do
    code = emit.call('Button', 'canTap' => '@{c}', 'enabled' => '@{on}')
    expect(code).to include('action: { if (data.c ?? false) { data.onTap?() } }')
    expect(compilable_view(code, data: gate_data + ['var on: Bool = true'], stubs: button_stub)).to compile_as_swift
  end
end
