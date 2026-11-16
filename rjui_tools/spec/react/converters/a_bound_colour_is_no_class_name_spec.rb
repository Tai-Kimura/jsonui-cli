# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/react_generator'
require_relative '../../support/typescript_compiler'

# A bound colour was put in a class name: the Segment wrote `bg-@{v}` and
# `text-@{v}` into its buttons, and the TabView built `'text-' + data.v` at run
# time. Neither is a class Tailwind made, so the selected segment's background,
# its label and a tab's colour drew nothing (getComputedStyle in Chromium; a
# name drew on a tab only when the same class was made elsewhere). A bound
# colour now rides the style, as the other components' do: the Segment's
# through custom properties its buttons read, the tab's as its own `color`.
RSpec.describe 'a bound colour is no class name' do
  def tsx(node)
    layout = { 'type' => 'View', 'id' => 'root', 'child' => [
      { 'data' => [{ 'name' => 'c', 'class' => 'String', 'defaultValue' => '' }] }, node
    ] }
    RjuiTools::React::ReactGenerator.new({ 'use_tailwind' => true, 'typescript' => true }).generate('Probe', layout).to_s
  end

  def segment(attrs)
    tsx({ 'type' => 'Segment', 'id' => 's', 'items' => %w[a b] }.merge(attrs))
  end

  def tabs(attrs)
    tsx({ 'type' => 'TabView', 'id' => 't', 'tabs' => [{ 'title' => 'a' }, { 'title' => 'b' }] }.merge(attrs))
  end

  {
    'tintColor' => ['bg-[var(--jui-segment-tint)]', '--jui-segment-tint'],
    'fontColor' => ['text-[var(--jui-segment-font)]', '--jui-segment-font'],
    'selectedFontColor' => ['text-[var(--jui-segment-selected-font)]', '--jui-segment-selected-font']
  }.each do |attr, (klass, property)|
    it "Segment.#{attr}: the buttons read a custom property the container sets" do
      out = segment(attr => '@{c}')
      expect(out).not_to include('-@{c}')
      expect(out).to include(klass)
      expect(out).to include("'#{property}': ColorManager.cssColor(data.c)")
    end
  end

  it 'Segment: a written colour is the class it was' do
    out = segment('tintColor' => '#FF0000', 'fontColor' => '#00FF00')
    expect(out).to include('bg-[#FF0000]')
    expect(out).to include('text-[#00FF00]')
    expect(out).not_to include('--jui-segment')
  end

  %w[tintColor unselectedColor].each do |attr|
    it "TabView.#{attr}: a binding is the tab's own colour, no class built at run time" do
      out = tabs(attr => '@{c}')
      expect(out).not_to match(/'[^']*text-'\s*\+/)
      expect(out).not_to include('-@{c}')
      expect(out).to include('ColorManager.cssColor(data.c)')
      expect(out).to match(/style=\{\{ color: .* === 0 \? /)
    end
  end

  it 'TabView: with one side bound, the written side keeps its class' do
    out = tabs('tintColor' => '@{c}', 'unselectedColor' => '#00FF00')
    expect(out).to include('text-[#00FF00]')
    expect(out).to include('color: (data.selectedTabIndex ?? seeded) === 0 ? ColorManager.cssColor(data.c) : undefined')
  end

  it 'TabView: written colours are the classes they were' do
    out = tabs('tintColor' => '#FF0000')
    expect(out).to include('text-[#FF0000]')
    expect(out).not_to include('style={{ color')
  end

  it 'the generated files parse', :typescript_compile do
    [segment('tintColor' => '@{c}', 'selectedFontColor' => '@{c}'), tabs('tintColor' => '@{c}', 'unselectedColor' => '@{c}')].each do |out|
      expect("// @ts-nocheck\n#{out}").to compile_as_typescript
    end
  end
end
