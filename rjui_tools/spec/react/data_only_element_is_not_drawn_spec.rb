# frozen_string_literal: true

require_relative '../spec_helper'
require_relative '../support/typescript_compiler'
require 'react/react_generator'
require 'core/layout_path'

# A data-only element — `{ "data": [...] }`, the layout's data declared as a
# child — is not drawn. The generator stamps every node with its position
# (JsonUIShared::LayoutPath::KEY) before converting, and the data-only check
# compared the node's keys with ['data'] exactly, so from 2de6da9b the stamped
# element was drawn as an empty <div className="" /> — on every web face
# that declares its data that way (found by rebuilding the web faces and
# comparing the bytes). The stamp is not a key the layout wrote.
RSpec.describe 'a data-only element, after the generator stamps positions' do
  let(:generator) { RjuiTools::React::ReactGenerator.new({ 'typescript' => true, 'use_tailwind' => true }) }

  def screen(children)
    layout = { 'type' => 'View', 'id' => 'root', 'child' => children }
    generator.generate('Home', layout, screen_id: 'home')
  end

  let(:data) { { 'data' => [{ 'name' => 'title', 'class' => 'String' }] } }
  let(:label) { { 'type' => 'Label', 'id' => 'l', 'text' => 'x' } }

  it 'is not drawn among the root children' do
    out = screen([data, label])
    expect(out).not_to include('<div className="" />')
    expect(out.scan(/<(div|span)\b/).size).to eq(2), out # the root and the label
  end

  it 'is not drawn inside a nested container either' do
    out = screen([{ 'type' => 'View', 'id' => 'box', 'child' => [data, label] }])
    expect(out).not_to include('<div className="" />')
    expect(out.scan(/<(div|span)\b/).size).to eq(3), out # the root, the box and the label
  end

  it 'is stamped all the same, as every node is' do
    layout = { 'type' => 'View', 'id' => 'root', 'child' => [data.dup, label.dup] }
    generator.generate('Home', layout, screen_id: 'home')
    expect(layout['child'][0][JsonUIShared::LayoutPath::KEY]).to eq('0_0')
  end

  # Both screens as the generator writes them, imports cut, under --strict:
  # what is drawn in the data-only element's place is nothing, not markup.
  it 'writes screens that compile', :typescript_compile do
    [screen([data, label]), screen([{ 'type' => 'View', 'id' => 'box', 'child' => [data, label] }])].each do |out|
      expect(out.lines.reject { |l| l.start_with?('import ') }.join).to compile_as_typescript.with_ambient(<<~TS)
        interface HomeData { title?: string }
        declare function createHomeData(): HomeData;
        declare function useStringManager(): Record<string, string>;
        declare function screenMarker(screenId: string): Record<string, string>;
      TS
    end
  end
end
