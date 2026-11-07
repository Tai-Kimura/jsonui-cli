# frozen_string_literal: true

require_relative '../spec_helper'
require_relative '../support/typescript_compiler'
require 'react/react_generator'

# A shadow drew nothing on the web whenever its colour was a colors.json key —
# and a build turns every hex in a layout into one. The key went into the
# `[box-shadow:…]` class or the style as written ("6px 6px 8px dark_blue"), which
# is no CSS colour, and the browser drops the whole declaration (measured in
# Chromium: computed box-shadow "none"). Its opacity was dropped with it, and on
# a TextField a style of its own overrode the pipe form with a fixed shadow.
# Ticket 2026-11-07-declared-binding-slots-and-dynamic-shadow.
RSpec.describe 'a shadow draws with its colour and opacity' do
  let(:generator) { RjuiTools::React::ReactGenerator.new({ 'use_tailwind' => true, 'typescript' => true }) }

  def emit(node)
    generator.send(:convert_component, { 'id' => 'p', 'type' => 'View' }.merge(node), 2).to_s
  end

  def shadow(**fields)
    { 'shadow' => { 'radius' => 8, 'offsetX' => 6, 'offsetY' => 6 }.merge(fields.transform_keys(&:to_s)) }
  end

  SHADOW_DRAWS = {
    'a key, as every colour style resolves one' =>
      [{ 'color' => 'dark_blue' }, "boxShadow: `6px 6px 8px ${ColorManager.resolveColor('dark_blue') ?? 'transparent'}`"],
    'a key with its opacity' =>
      [{ 'color' => 'dark_blue', 'opacity' => 0.5 },
       "boxShadow: `6px 6px 8px color-mix(in srgb, ${ColorManager.resolveColor('dark_blue') ?? 'transparent'} calc(0.5 * 100%), transparent)`"],
    'a key beside a bound radius' =>
      [{ 'color' => 'dark_blue', 'radius' => '@{r}' }, "boxShadow: `6px 6px ${data.r}px ${ColorManager.resolveColor('dark_blue') ?? 'transparent'}`"],
    'a bound colour, which may hold a key' =>
      [{ 'color' => '@{c}' }, "boxShadow: `6px 6px 8px ${ColorManager.resolveColor(data.c) ?? 'transparent'}`"],
    'a bound opacity on a key' =>
      [{ 'color' => 'dark_blue', 'opacity' => '@{o}' }, "calc(${data.o} * 100%)"]
  }.freeze

  %w[View Label Button TextField TextView SelectBox Switch Image].each do |type|
    SHADOW_DRAWS.each do |what, (fields, expected)|
      it "#{type}: #{what}" do
        code = emit({ 'type' => type }.merge(shadow(**fields.transform_keys(&:to_sym))))
        expect(code).to include(expected)
        expect(code).not_to include('dark_blue]')   # no key left in a class
        expect(code).not_to match(/px dark_blue[`']/) # nor bare in a style
      end
    end
  end

  it 'keeps a hex shadow the class it was, its opacity folded into the alpha byte' do
    code = emit(shadow(color: '#0000FF', opacity: 0.5))
    expect(code).to include('[box-shadow:6px_6px_8px_#0000FF80]')
    expect(code).not_to include('boxShadow')
  end

  it 'keeps a hex pipe shadow the class it was' do
    expect(emit({ 'shadow' => '#0000FF|6|6|0.5|8' })).to include('[box-shadow:6.0px_6.0px_8.0px_#0000FF80]')
  end

  it "keeps a TextField's written hex shadow as the bytes it was" do
    expect(emit({ 'type' => 'TextField' }.merge(shadow(color: 'rgba(0,0,0,0.1)')))).to include("boxShadow: '6px 6px 8px rgba(0,0,0,0.1)'")
  end

  it "draws a TextField's pipe shadow, which its own style overrode with a fixed one" do
    code = emit({ 'type' => 'TextField', 'shadow' => '#0000FF|6|6|0.5|8' })
    expect(code).to include('[box-shadow:6.0px_6.0px_8.0px_#0000FF80]')
    expect(code).not_to include('boxShadow')
  end

  it "folds a TextField's opacity into its colour, which it dropped" do
    expect(emit({ 'type' => 'TextField' }.merge(shadow(color: '#0000FF', opacity: 0.5)))).to include("boxShadow: '6px 6px 8px #0000FF80'")
  end

  it 'writes what it draws so that it compiles', :typescript_compile do
    drawn = %w[View TextField].flat_map do |type|
      SHADOW_DRAWS.values.map { |fields, _| emit({ 'type' => type }.merge(shadow(**fields.transform_keys(&:to_sym)))) }
    end
    source = "const data = {} as { [key: string]: any };\nconst refs: any = {};\nexport const view = (\n  <div>\n#{drawn.join("\n")}\n  </div>\n);\n"
    expect(source.gsub(/ ref=\{\w+\}/, '').gsub(/ on\w+=\{[^}]*\}\}?/, ''))
      .to compile_as_typescript.with_ambient('declare namespace React { type CSSProperties = Record<string, unknown>; }; ' \
                                             'declare const ColorManager: { resolveColor(value: unknown): string | undefined };')
  end
end
