# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/react_generator'
require_relative '../../support/typescript_compiler'

# `canTap` (attribute_definitions common.canTap) gates the tap — every
# spelling of it: the onClick binding, the onclick selector (a string or an
# array) and the link action. Only the binding went through the gate
# (BaseConverter#can_tap_gated_click); the selector and the link action went
# out ungated on every type, and ImageConverter replaced build_onclick_attr
# with its own, which read the gate on no spelling — `canTap: false` still
# tapped. The tap rule's family: sjui (tap_shut?, tap_gate_condition) and kjui
# (click_call) gate every spelling.
RSpec.describe 'rjui: canTap gates every spelling of the tap' do
  let(:config) { { 'use_tailwind' => true } }

  TAP_TYPES = {
    'View' => { 'child' => [] }, 'Label' => { 'text' => 'x' }, 'Image' => { 'srcName' => 'x' },
    'NetworkImage' => { 'url' => 'https://e/x.png' }
  }.freeze
  SPELLINGS = {
    'onClick binding' => { 'onClick' => '@{tap}' },
    'onclick selector' => { 'onclick' => 'go' },
    'onclick selectors' => { 'onclick' => %w[first second] },
    'link action' => { 'onClick' => { 'action' => 'link', 'url' => 'https://example.com' } }
  }.freeze

  def convert(type, extra)
    node = { 'type' => type }.merge(TAP_TYPES.fetch(type)).merge(extra)
    klass = RjuiTools::React::Converters::ViewConverter.new({ 'type' => 'View' }, config).send(:get_converter_class, type)
    klass.new(node, config).convert(2)
  end

  it 'taps without a gate' do
    TAP_TYPES.each_key do |type|
      SPELLINGS.each do |name, spelling|
        expect(convert(type, spelling)).to include(' onClick={'), "#{type} #{name}"
      end
    end
  end

  it 'does not tap under canTap false' do
    TAP_TYPES.each_key do |type|
      SPELLINGS.each do |name, spelling|
        expect(convert(type, spelling.merge('canTap' => false))).not_to include('onClick='), "#{type} #{name}"
      end
    end
  end

  it 'taps while a bound canTap holds' do
    TAP_TYPES.each_key do |type|
      SPELLINGS.each do |name, spelling|
        gated = type == 'NetworkImage' ? 'onClick={() => { if (data.gate) ' : 'onClick={(e) => { if (data.gate) '
        expect(convert(type, spelling.merge('canTap' => '@{gate}'))).to include(gated), "#{type} #{name}"
      end
    end
  end

  # An Image's selector is a method on the data, as on every other type. Its
  # own build_onclick_attr wrote the name bare: `onClick={go}`.
  it "calls an Image's selector on the data" do
    expect(convert('Image', 'onclick' => 'go')).to include('onClick={data.go}')
  end

  # The gated shapes, as a component returns them, under --strict, against
  # NetworkImage's own props (its template's NetworkImageProps, whose onClick
  # takes no event — the gated binding there did not compile before): a member
  # path is called with the event where the element hands one, an arrow
  # function (the selector array's, the link action's) in parentheses with none.
  it 'writes TSX that compiles', :typescript_compile do
    elements = TAP_TYPES.keys.product(SPELLINGS.values).map do |type, spelling|
      convert(type, spelling.merge('canTap' => '@{gate}'))
    end
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(<<~TS)
      declare namespace JSX {
        interface IntrinsicElements {
          div: { [attr: string]: unknown; onClick?: (e: MouseEvent) => void };
          span: { [attr: string]: unknown; onClick?: (e: MouseEvent) => void };
          img: { [attr: string]: unknown; onClick?: (e: MouseEvent) => void };
        }
      }
      declare namespace React { type CSSProperties = { [property: string]: string | number | undefined } }
      declare namespace React { type FC<P> = (props: P) => JSX.Element }
      #{TypeScriptCompiler.template_declarations('network_image.tsx', 'NetworkImageProps')}
      declare const NetworkImage: React.FC<NetworkImageProps>;
      declare const data: { gate?: boolean; tap?: (e?: unknown) => void; go?: (e?: unknown) => void;
                            first?: () => void; second?: () => void };
    TS
  end
end
