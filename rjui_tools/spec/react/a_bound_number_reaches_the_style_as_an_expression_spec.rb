# frozen_string_literal: true

require 'json'
require_relative '../spec_helper'
require_relative '../support/typescript_compiler'
require 'react/react_generator'

# A binding on a value a converter writes itself. `borderRadius: '@{x}px'` is a
# string, so it compiled and the browser dropped it; `src={/images/@{x}.svg}` did
# not compile; the shadow went into a Tailwind class that no stylesheet holds.
# The build said nothing about any of them. The sweep is over the attribute table,
# so a new attribute or component is in it the day it is declared.
RSpec.describe 'a bound number reaches the style as an expression' do
  DEFS = JSON.parse(File.read(File.expand_path('../../../shared/core/attribute_definitions.json', __dir__)))
  BOUND = '@{v}'
  let(:generator) { RjuiTools::React::ReactGenerator.new({ 'use_tailwind' => true, 'typescript' => true }) }

  def emit(node)
    generator.send(:convert_component, { 'id' => 'p' }.merge(node), 2).to_s
  end

  # The attributes that take a number or a color, and what that draws.
  DRAWS = {
    { 'type' => 'TextField', 'cornerRadius' => BOUND } => 'borderRadius: `${data.v}px`',
    { 'type' => 'TextView', 'cornerRadius' => BOUND } => 'borderRadius: `${data.v}px`',
    { 'type' => 'TextView', 'minHeight' => BOUND } => 'minHeight: `${data.v}px`',
    { 'type' => 'TextView', 'maxHeight' => BOUND } => 'maxHeight: `${data.v}px`',
    { 'type' => 'TextView', 'containerInset' => BOUND } => 'padding: `${Number(data.v) / 16}rem`',
    { 'type' => 'TextView', 'containerInset' => [BOUND, 8] } => 'padding: `${Number(data.v) / 16}rem 0.5rem`',
    { 'type' => 'ScrollView', 'contentInset' => BOUND } => 'padding: `${Number(data.v) / 16}rem`',
    { 'type' => 'Label', 'edgeInset' => BOUND } => 'padding: `${Number(data.v) / 16}rem`',
    { 'type' => 'TextView', 'containerInset' => [BOUND] } => 'padding: `${Number(data.v) / 16}rem`',
    { 'type' => 'TextView', 'containerInset' => [BOUND, 8, 8, 8] } => 'padding: `${Number(data.v) / 16}rem 0.5rem 0.5rem 0.5rem`',
    { 'type' => 'ScrollView', 'contentInset' => [BOUND] } => 'padding: `${Number(data.v) / 16}rem`',
    { 'type' => 'ScrollView', 'contentInset' => [BOUND, 8] } => 'padding: `${Number(data.v) / 16}rem 0.5rem`',
    { 'type' => 'ScrollView', 'contentInset' => [BOUND, 8, 8, 8] } => 'padding: `${Number(data.v) / 16}rem 0.5rem 0.5rem 0.5rem`',
    { 'type' => 'ScrollView', 'contentInset' => { 'top' => BOUND } } => 'padding: `${Number(data.v) / 16}rem 0rem 0rem 0rem`',
    { 'type' => 'Label', 'edgeInset' => [BOUND] } => 'padding: `${Number(data.v) / 16}rem`',
    { 'type' => 'Label', 'edgeInset' => [BOUND, 8] } => 'padding: `${Number(data.v) / 16}rem 0.5rem`',
    { 'type' => 'Label', 'edgeInset' => [BOUND, 8, 8] } => 'padding: `${Number(data.v) / 16}rem 0.5rem 0.5rem`',
    { 'type' => 'Label', 'edgeInset' => [BOUND, 8, 8, 8] } => 'padding: `${Number(data.v) / 16}rem 0.5rem 0.5rem 0.5rem`',
    { 'type' => 'View', 'margins' => [BOUND, 8] } => 'margin: `${Number(data.v) / 16}rem 0.5rem`',
    { 'type' => 'View', 'shadow' => { 'radius' => BOUND } } => 'boxShadow: `0px 2px ${data.v}px rgba(0,0,0,0.1)`',
    { 'type' => 'Label', 'shadow' => { 'offsetX' => BOUND, 'color' => '#000000' } } => 'boxShadow: `${data.v}px 2px 5px #000000`',
    { 'type' => 'Label', 'shadow' => { 'opacity' => BOUND, 'color' => '#000000' } } => 'color-mix(in srgb, #000000 calc(${data.v} * 100%), transparent)',
    { 'type' => 'Label', 'shadow' => "#{BOUND}|1|2|0.5|3" } => 'boxShadow: `1px 2px 3px color-mix',
    { 'type' => 'TextField', 'shadow' => { 'color' => BOUND } } => 'boxShadow: `0px 0px 5px ${data.v}`',
    { 'type' => 'CircleView', 'shadow' => { 'radius' => BOUND } } => 'boxShadow: `0px 2px ${data.v}px rgba(0,0,0,0.1)`',
    { 'type' => 'Label', 'textShadow' => BOUND } => 'textShadow: data.v',
    { 'type' => 'Label', 'textShadow' => { 'color' => '#000000', 'blur' => BOUND, 'offset' => [1, 2] } } => 'textShadow: `1px 2px ${data.v}px #000000`',
    { 'type' => 'IconLabel', 'textShadow' => BOUND } => 'textShadow: data.v',
    { 'type' => 'Label', 'hint' => BOUND } => '>{data.v}</span>',
    { 'type' => 'Label', 'text' => '@{t}', 'hint' => BOUND } => '>{data.v}</span>',
    { 'type' => 'TabView', 'width' => BOUND } => 'width: `${data.v}px`',
    { 'type' => 'TabView', 'height' => BOUND } => 'height: `${data.v}px`',
    { 'type' => 'Indicator', 'borderWidth' => BOUND } => "'--jui-indicator-width': `${data.v}px`",
    { 'type' => 'Image', 'defaultImage' => BOUND } => 'src={data.v}'
  }.freeze

  DRAWS.each do |node, expression|
    it "#{node.reject { |k, _| k == 'type' }.to_json} on #{node['type']} draws #{expression}" do
      code = emit(node)
      expect(code).to include(expression)
      expect(code).not_to include('@{')
    end
  end

  it 'writes one boxShadow on a CircleView' do
    expect(emit({ 'type' => 'CircleView', 'shadow' => { 'radius' => BOUND } }).scan('boxShadow').size).to eq(1)
  end

  # A written value keeps the bytes it always had.
  WRITTEN = {
    { 'type' => 'TextField', 'cornerRadius' => 7 } => "borderRadius: '7px'",
    { 'type' => 'TextView', 'minHeight' => 7 } => "minHeight: '7px'",
    { 'type' => 'TextView', 'containerInset' => [8, 16] } => "padding: '0.5rem 1rem'",
    { 'type' => 'ScrollView', 'contentInset' => { 'top' => 8 } } => "padding: '0.5rem 0rem 0rem 0rem'",
    { 'type' => 'Label', 'edgeInset' => [8, 16, 8, 16] } => "padding: '0.5rem 1rem 0.5rem 1rem'",
    { 'type' => 'View', 'margins' => [8, 16] } => 'my-[0.5rem] mx-[1rem]',
    { 'type' => 'View', 'shadow' => { 'radius' => 3, 'offsetX' => 1, 'offsetY' => 2 } } => '[box-shadow:1px_2px_3px_rgba(0,0,0,0.1)]',
    { 'type' => 'Label', 'textShadow' => { 'color' => '#000000', 'blur' => 3, 'offset' => [1, 2] } } => "textShadow: '1px 2px 3px #000000'",
    { 'type' => 'Label', 'textShadow' => '1px 1px red' } => "textShadow: '1px 1px red'",
    { 'type' => 'TabView', 'width' => 7 } => 'w-[7px]',
    { 'type' => 'Indicator', 'borderWidth' => 3 } => 'border-3',
    { 'type' => 'CircleView', 'shadow' => { 'radius' => 3 } } => "boxShadow: '0px 2px 3px rgba(0,0,0,0.25)'"
  }.freeze

  WRITTEN.each do |node, written|
    it "a written #{node.reject { |k, _| k == 'type' }.to_json} on #{node['type']} stays #{written}" do
      expect(emit(node)).to include(written)
    end
  end

  it 'says screen does not take a binding, and pastes it nowhere' do
    expect(RjuiTools::Core::Logger).to receive(:warn).with(/'screen' .*does not take a binding/).at_least(:once)
    expect(emit({ 'type' => 'Embed', 'screen' => BOUND })).not_to include('@{')
  end

  it 'writes what it draws so that it compiles', :typescript_compile do
    drawn = DRAWS.keys.reject { |node| %w[Image TabView].include?(node['type']) }.each_with_index.map { |node, i| emit(node.merge('id' => "p#{i}")) }
    source = "const data = {} as { v: any; [key: string]: any };\nconst refs: any = {};\nexport const view = (\n  <div>\n#{drawn.join("\n")}\n  </div>\n);\n"
    expect(source.gsub(/ ref=\{\w+\}/, '').gsub(/ on\w+=\{[^}]*\}\}?/, '')).to compile_as_typescript.with_ambient('declare namespace React { type CSSProperties = Record<string, unknown>; }')
  end
end
