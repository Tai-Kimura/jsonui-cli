# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/view_converter'
require 'react/converters/scroll_view_converter'
require_relative '../../support/typescript_compiler'

# A wrapContent (or undeclared) box stops at its parent's size when the parent
# has one — a number or matchParent, and not the axis it scrolls along (user
# ruling 2026-10-05, attribute_semantics wrapContentCap). Web drew the box at
# its content's size: Collection/flowOverflow__noneWrapInBox and its control
# were 168 high in a 100-high parent, where android stops at 100.
RSpec.describe 'a wrapContent box stops at its parent size' do
  let(:config) { { 'use_tailwind' => true } }

  def convert(json)
    RjuiTools::React::Converters::ViewConverter.new(json, config).convert
  end

  def child_tag(out, id)
    out.lines.find { |l| l.include?(%(id="#{id}")) }.to_s
  end

  def tree(parent, child)
    { 'type' => 'View', 'id' => 'root', 'width' => 150, 'height' => 100 }.merge(parent)
      .merge('child' => [{ 'type' => 'View', 'id' => 'c' }.merge(child)])
  end

  it 'caps a wrapContent height in a fixed parent (overlay root)' do
    expect(child_tag(convert(tree({}, 'height' => 'wrapContent')), 'c')).to include('max-h-full')
  end

  it 'caps an undeclared size in a fixed parent, both axes' do
    tag = child_tag(convert(tree({}, {})), 'c')
    expect(tag).to include('max-h-full')
    expect(tag).to include('max-w-full')
  end

  it 'caps inside a stacked (oriented) parent too' do
    expect(child_tag(convert(tree({ 'orientation' => 'vertical' }, 'height' => 'wrapContent')), 'c')).to include('max-h-full')
  end

  it 'leaves a fixed-size child alone (ruling S: it overflows)' do
    expect(child_tag(convert(tree({}, 'height' => 300)), 'c')).not_to include('max-h-full')
  end

  it 'does not cap under a wrapContent parent' do
    expect(child_tag(convert(tree({ 'height' => 'wrapContent' }, 'height' => 'wrapContent')), 'c')).not_to include('max-h-full')
  end

  it 'emits TypeScript a compiler reads' do
    out = convert(tree({}, 'height' => 'wrapContent'))
    expect(TypeScriptCompiler.component(out)).to compile_as_typescript
  end

  it 'does not cap a ScrollView content along the scroll axis' do
    out = convert({ 'type' => 'View', 'id' => 'root', 'width' => 200, 'height' => 200,
                    'child' => [{ 'type' => 'ScrollView', 'id' => 's', 'width' => 200, 'height' => 200,
                                  'child' => [{ 'type' => 'View', 'id' => 'c', 'height' => 'wrapContent' }] }] })
    tag = child_tag(out, 'c')
    expect(tag).not_to include('max-h-full')
    expect(tag).to include('max-w-full')
  end
end
