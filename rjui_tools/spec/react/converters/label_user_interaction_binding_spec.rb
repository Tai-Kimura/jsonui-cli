# frozen_string_literal: true

require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require 'react/converters/label_converter'

# A bound `userInteractionEnabled` on a Label gates it as a View's does:
# `pointer-events-none` while the binding is false, on every shape the Label
# takes — plain, linkable (LinkifyText, whose links it stops too) and
# partialAttributes (the tap rule, shared/core/tap_accessibility.rb; 4f
# ruling, jsonui-cli 1.9.0). Only the literal `false` reached the Label (a
# static class); the binding was dropped, so the Label, its onClick and its
# links answered whatever the value was.
RSpec.describe 'rjui Label: a bound userInteractionEnabled' do
  def convert(node)
    RjuiTools::React::Converters::LabelConverter.new(node, { 'use_tailwind' => true }).convert
  end

  gate = "${!data.u ? 'pointer-events-none' : ''}"
  shapes = {
    'plain' => { 'type' => 'Label', 'id' => 'l', 'text' => 't', 'onClick' => '@{onTap}' },
    'linkable' => { 'type' => 'Label', 'id' => 'l', 'text' => 'See https://example.com', 'linkable' => true },
    'bound linkable' => { 'type' => 'Label', 'id' => 'l', 'text' => 'See https://example.com', 'linkable' => '@{isLinkable}' },
    'partialAttributes' => { 'type' => 'Label', 'id' => 'l', 'text' => 'Terms and Privacy',
                             'partialAttributes' => [{ 'range' => 'Terms', 'onclick' => 'onTerms' }] },
    'selected, with highlight' => { 'type' => 'Label', 'id' => 'l', 'text' => 't', 'selected' => '@{sel}',
                                    'highlightColor' => '#FF0000' }
  }

  shapes.each do |name, node|
    describe name do
      it 'carries the gate' do
        expect(convert(node.merge('userInteractionEnabled' => '@{u}'))).to include(gate)
      end

      it 'is written as before with no flag, and with the literal false as a static class' do
        expect(convert(node)).not_to include('pointer-events-none')
        literal = convert(node.merge('userInteractionEnabled' => false))
        expect(literal).to include('pointer-events-none')
        expect(literal).not_to include(gate)
      end
    end
  end

  it 'gates both sides of a selected / highlight swap' do
    jsx = convert(shapes['selected, with highlight'].merge('userInteractionEnabled' => '@{u}'))
    expect(jsx.scan(gate).size).to eq(2)
  end

  it 'compiles, every shape with the gate', :typescript_compile do
    elements = shapes.values.map { |n| convert(n.merge('userInteractionEnabled' => '@{u}')) }
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(<<~TS)
      declare namespace React { type CSSProperties = { [property: string]: string | number | undefined } }
      #{TypeScriptCompiler.template_declarations('linkify_text.tsx', 'LinkifyTextProps')}
      declare const LinkifyText: (props: LinkifyTextProps & { ref?: { current: HTMLSpanElement | null } }) => JSX.Element;
      type PartialSpec = { range: [number, number] | string; style?: Record<string, string | number>; className?: string; onClick?: () => void };
      declare function partialText(text: string, partials: PartialSpec[]): JSX.Element;
      declare const data: { u?: boolean; sel?: boolean; isLinkable?: boolean; onTap?: () => void; onTerms?: () => void };
      declare function jsonuiInert(stop: boolean): Record<string, unknown>;
    TS
  end
end
