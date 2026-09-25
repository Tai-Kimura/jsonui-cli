# frozen_string_literal: true

require 'swiftui/converter_factory'
require 'swiftui/views/modifier_bag'
require_relative '../../support/emitted_swift'
require 'core/tap_accessibility'
require 'core/image_accessibility'
require 'json'

# `userInteractionEnabled: false` (attribute_definitions.json common:
# "Enable user interaction"), static or bound, stops the view: its own tap,
# long press, pan and pinch, and what is in it. The stop is one
# `.allowsHitTesting`, and it has to sit OUTSIDE the view's own gestures — a
# gesture attached after it is not stopped.
#
# It sat before `.contentShape` + `.onTapGesture` (ModifierBag put
# :allows_hit_testing before :on_click): measured on iOS 18.6 and 26.4
# (SwiftJsonUI ConformanceHost -interactionGateProbe), a View under the flag
# still called its own handler — for a tap in its padding and for one in its
# child's frame — and a Label did too, while the child's tap stopped. And
# Button, TextField (the literal; the binding came through
# ViewBindingHandler), TextView and SelectBox read neither the flag nor its
# binding: a gated button acted, a field took focus, a select box opened
# (-interactionInputsProbe).
#
# So these arms look at the position, not the presence: for every type the
# declaration knows, under `false` and a binding, one `.allowsHitTesting` after
# the last of the view's gestures.
RSpec.describe 'sjui userInteractionEnabled stops the view' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  defs_path = File.expand_path('../../../../shared/core/attribute_definitions.json', __dir__)
  defs = JSON.parse(File.read(defs_path))
  types = (defs.keys - %w[common]).select { |k| defs[k].is_a?(Hash) && !k.start_with?('_', '$') }.sort

  # What each type needs to convert at all.
  extra = {
    'Image' => { 'srcName' => 'x' }, 'CircleImage' => { 'srcName' => 'x' },
    'NetworkImage' => { 'url' => 'https://e/x.png' }, 'Label' => { 'text' => 't' },
    'Text' => { 'text' => 't' }, 'IconLabel' => { 'text' => 't' }, 'Button' => { 'text' => 't' },
    'SelectBox' => { 'items' => ['a'] }, 'Segment' => { 'items' => ['a'] }, 'Embed' => { 'screen' => 'S' },
    'TextField' => { 'text' => '@{t}' }, 'TextView' => { 'text' => '@{t}' }
  }
  gestures = /\.onTapGesture|\.gesture\(TapGesture|\.onLongPressGesture|\.simultaneousGesture/

  emit = lambda do |type, gate, more = {}|
    comp = { 'type' => type, 'id' => 'n', 'onClick' => '@{onTap}', 'userInteractionEnabled' => gate }
           .merge(extra[type] || {}).merge(more)
    comp = JSON.parse(JSON.generate(comp))
    JsonUIShared::ImageAccessibility.annotate!(comp, source_path: 'probe.json')
    JsonUIShared::TapAccessibility.annotate!(comp)
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter(comp).convert.to_s
  end

  it 'reads every type the declaration knows' do
    expect(types.size).to be >= 29
    expect(types).to include('View', 'Label', 'Button', 'TextField', 'TextView', 'SelectBox', 'Switch', 'Image')
  end

  types.each do |type|
    { 'false' => [false, '.allowsHitTesting(false)'], 'a binding' => ['@{u}', '.allowsHitTesting((data.u ?? false))'] }
      .each do |name, (gate, line)|
      it "#{type} under #{name}: one stop, outside its own gestures" do
        code = emit.call(type, gate)
        expect(code.scan('.allowsHitTesting(').size).to eq(1), code
        expect(code).to include(line)
        last_gesture = code.rindex(gestures)
        expect(code.index('.allowsHitTesting(')).to be > last_gesture, code if last_gesture
      end
    end
  end

  it 'a long press, a pan and a pinch are inside the stop too' do
    code = emit.call('View', '@{u}', 'onLongPress' => '@{onHold}', 'onPan' => '@{onDrag}', 'onPinch' => '@{onZoom}')
    stop = code.index('.allowsHitTesting((data.u ?? false))')
    %w[.onLongPressGesture DragGesture MagnifyGesture].each do |g|
      expect(code.index(g)).to be < stop, "#{g}:\n#{code}"
    end
  end

  it 'ModifierBag writes :allows_hit_testing after the four gestures' do
    order = SjuiTools::SwiftUI::Views::ModifierBag::MODIFIER_ORDER
    %i[on_click on_long_press on_pan on_pinch].each do |g|
      expect(order.index(:allows_hit_testing)).to be > order.index(g)
    end
  end

  {
    'a View with a tap, a long press and a pan' =>
      ['View', { 'onLongPress' => '@{onHold}', 'onPan' => '@{onDrag}' }],
    'a Label' => ['Label', {}]
  }.each do |name, (type, more)|
    it "#{name} under a binding: the emitted Swift compiles" do
      code = emit.call(type, '@{u}', more)
      data = ['var onTap: (() -> Void)? = nil', 'var onHold: (() -> Void)? = nil', 'var onDrag: (() -> Void)? = nil',
              'var u: Bool? = nil']
      expect(compilable_view(code, data: data)).to compile_as_swift
    end
  end
end
