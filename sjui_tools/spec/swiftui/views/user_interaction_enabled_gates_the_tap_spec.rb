# frozen_string_literal: true

require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'
require 'core/tap_accessibility'
require 'core/image_accessibility'
require 'json'

# `userInteractionEnabled` gates a tap as canTap does (the tap rule,
# shared/core/tap_accessibility.rb): `false` on the node, or on a node around
# it, is no tap — no gesture that calls the handler and no button trait — and
# a binding on either gates the gesture and the trait on the bound value. The
# runtime stop stays the view's own `.allowsHitTesting`: it stopped a touch,
# and the tap it stopped was still announced as a button.
#
# The arms compare whole emissions: the node under the flag against the same
# node with canTap set to what the flag says — on every type the tap rule
# gives a shape (the declaration's types that are not a control), and on the
# onClick call a control makes from its own operation, on the node and inside
# a View that carries the flag.
RSpec.describe 'sjui userInteractionEnabled gates the tap as canTap does' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  tap = JsonUIShared::TapAccessibility

  extra = {
    'Image' => { 'srcName' => 'x' }, 'CircleImage' => { 'srcName' => 'x' }, 'CircleImageView' => { 'srcName' => 'x' },
    'ImageView' => { 'srcName' => 'x' }, 'Img' => { 'srcName' => 'x' },
    'NetworkImage' => { 'url' => 'https://e/x.png' }, 'Label' => { 'text' => 't' },
    'Text' => { 'text' => 't' }, 'IconLabel' => { 'text' => 't' }
  }

  convert = lambda do |comp|
    comp = JSON.parse(JSON.generate(comp))
    JsonUIShared::ImageAccessibility.annotate!(comp, source_path: 'probe.json')
    tap.annotate!(comp)
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter(comp).convert.to_s
  end

  node = ->(type, more = {}) { { 'type' => type, 'id' => 'n', 'onClick' => '@{onTap}' }.merge(extra[type] || {}).merge(more) }
  inside = ->(flag, child) { { 'type' => 'View', 'id' => 'p', 'userInteractionEnabled' => flag, 'child' => [child] } }
  trait = /\.accessibilityAddTraits\(/

  types = (tap::KNOWN_TYPES - tap::INTERACTIVE_TYPES).uniq

  # A control calls onClick from its own operation (a Button's action — which
  # VoiceOver activates without a touch, so `.allowsHitTesting` does not stop
  # it — a Radio's selection, a CheckBox's value change, a Switch's write;
  # operation_click_call): the call is gated as canTap gates it.
  controls = {
    'Button' => { 'text' => 't' },
    'Radio' => { 'group' => 'g', 'text' => 't' },
    'CheckBox' => { 'label' => 't' },
    'Switch' => { 'isOn' => '@{on}' }
  }

  it 'reads every type the rule gives a shape' do
    expect(types).to include('View', 'Label', 'Image', 'IconLabel', 'NetworkImage')
    expect(types.size).to be >= 16
  end

  types.each do |type|
    describe type do
      it 'with no flag taps (the arms below are not empty)' do
        expect(convert.call(node.call(type))).to include('data.onTap?()')
      end

      it 'userInteractionEnabled: false emits what canTap: false emits: no tap, no trait' do
        code = convert.call(node.call(type, 'userInteractionEnabled' => false))
        expect(code).to eq(convert.call(node.call(type, 'userInteractionEnabled' => false, 'canTap' => false)))
        expect(code).not_to include('data.onTap?()')
        expect(code).not_to match(trait)
      end

      it 'inside a View with userInteractionEnabled: false, the same' do
        code = convert.call(inside.call(false, node.call(type)))
        expect(code).to eq(convert.call(inside.call(false, node.call(type, 'canTap' => false))))
        expect(code).not_to include('data.onTap?()')
      end

      it 'a bound userInteractionEnabled emits what a bound canTap on the same value emits' do
        code = convert.call(node.call(type, 'userInteractionEnabled' => '@{u}'))
        expect(code).to eq(convert.call(node.call(type, 'userInteractionEnabled' => '@{u}', 'canTap' => '@{u}')))
      end

      it 'inside a View with a bound userInteractionEnabled, the same' do
        code = convert.call(inside.call('@{u}', node.call(type)))
        expect(code).to eq(convert.call(inside.call('@{u}', node.call(type, 'canTap' => '@{u}'))))
      end
    end
  end

  # The gesture and the trait follow the binding (types whose tap is a gesture:
  # IconLabel's is its button's action).
  (types - %w[IconLabel]).each do |type|
    it "#{type} under a bound flag: the gesture is masked and the trait follows it" do
      code = convert.call(inside.call('@{u}', node.call(type)))
      expect(code).to include('including: (data.u ?? false) ? .all : .subviews)')
      expect(code).not_to include('.onTapGesture')
      expect(code).not_to include('.accessibilityAddTraits(.isButton)')
    end
  end

  controls.each do |type, more|
    describe "a #{type}'s own call" do
      it 'is there with no flag' do
        expect(convert.call(node.call(type, more))).to include('data.onTap')
      end

      [false, '@{u}'].each do |flag|
        it "under #{flag.inspect}, and inside a View with it, is what canTap #{flag.inspect} leaves" do
          expect(convert.call(node.call(type, more.merge('userInteractionEnabled' => flag))))
            .to eq(convert.call(node.call(type, more.merge('userInteractionEnabled' => flag, 'canTap' => flag))))
          expect(convert.call(inside.call(flag, node.call(type, more))))
            .to eq(convert.call(inside.call(flag, node.call(type, more.merge('canTap' => flag)))))
        end
      end

      it 'under false has no call' do
        expect(convert.call(inside.call(false, node.call(type, more)))).not_to include('data.onTap')
      end
    end
  end

  it 'a tap beside a View with userInteractionEnabled: false keeps its tap and its trait' do
    code = convert.call({ 'type' => 'View', 'id' => 'r', 'child' => [
                          inside.call(false, node.call('Label', 'id' => 'a', 'onClick' => '@{onA}')),
                          node.call('Label', 'id' => 'b', 'onClick' => '@{onB}')
                        ] })
    expect(code).not_to include('data.onA?()')
    expect(code.scan(/\.onTapGesture \{\n\s*data\.onB\?\(\)/).size).to eq(1)
    expect(code.scan('.accessibilityAddTraits(.isButton)').size).to eq(1)
  end

  it 'the selector spelling is gated too' do
    stopped = convert.call(inside.call(false, { 'type' => 'View', 'id' => 'n', 'onclick' => 'doIt' }))
    expect(stopped).not_to include('data.doIt?()')
    bound = convert.call(inside.call('@{u}', { 'type' => 'View', 'id' => 'n', 'onclick' => 'doIt' }))
    expect(bound).to include('}, including: (data.u ?? false) ? .all : .subviews)')
  end

  # canTap and each bound flag around the tap, outermost first, joined once.
  it 'joins a bound canTap and the bound flags around the tap into one condition' do
    code = convert.call({ 'type' => 'View', 'id' => 'o', 'userInteractionEnabled' => '@{a}', 'child' => [
                          inside.call('@{b}', node.call('Label', 'canTap' => '@{c}', 'userInteractionEnabled' => '@{a}'))
                        ] })
    gate = '(data.c ?? false) && (data.a ?? false) && (data.b ?? false)'
    expect(code).to include("including: #{gate} ? .all : .subviews)")
    expect(code).to include(".accessibilityAddTraits(#{gate} ? AccessibilityTraits.isButton : [])")
  end

  data = ['var onTap: (() -> Void)? = nil', 'var onA: (() -> Void)? = nil', 'var onB: (() -> Void)? = nil',
          'var u: Bool? = nil', 'var a: Bool? = nil', 'var b: Bool? = nil', 'var c: Bool? = nil']
  {
    'a Label inside a bound View' => ->(n) { inside.call('@{u}', n.call('Label')) },
    'a View holding a Label, combined, under two bound flags and a bound canTap' => lambda { |n|
      inside.call('@{a}', n.call('View', 'canTap' => '@{c}', 'userInteractionEnabled' => '@{b}',
                                         'child' => [{ 'type' => 'Label', 'text' => 'x' }]))
    },
    'a tap beside a false View' => lambda { |n|
      { 'type' => 'View', 'id' => 'r', 'child' => [inside.call(false, n.call('Label', 'id' => 'a', 'onClick' => '@{onA}')),
                                                    n.call('Label', 'id' => 'b', 'onClick' => '@{onB}')] }
    }
  }.each do |name, build|
    it "#{name}: the emitted Swift compiles" do
      expect(compilable_view(convert.call(build.call(node)), data: data)).to compile_as_swift
    end
  end
end
