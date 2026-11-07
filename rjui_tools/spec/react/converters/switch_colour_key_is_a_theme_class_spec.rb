# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/switch_converter'
require 'react/react_generator'
require_relative '../../support/typescript_compiler'

# The Switch put every written colour in brackets: `bg-[primary]`,
# `peer-checked:bg-[primary]`. A colors.json name is no CSS colour there, and
# Tailwind drew nothing (measured with getComputedStyle in Chromium: the track
# and the knob kept no colour). A hex `jui build` had already turned into its
# colors.json name — it does so for tint and tintColor — met the same end. The
# three colours now go through TailwindMapper.map_color, as every other
# converter's do: a name is the theme class, a hex the arbitrary class it was.
RSpec.describe 'a Switch colour that names colors.json' do
  before do
    RjuiTools::React::TailwindMapper.configure_palette(
      theme_safe: Set.new(%w[primary half]), fallbacks: { 'primary' => '#FF0000', 'half' => '#800000FF' }
    )
  end
  after { RjuiTools::React::TailwindMapper.reset_palette! }

  def html(attrs)
    RjuiTools::React::Converters::SwitchConverter.new({ 'type' => 'Switch', 'id' => 's' }.merge(attrs),
                                                      { 'use_tailwind' => true }).convert
  end

  SWITCH_COLOUR_SLOTS = {
    'onTintColor' => 'peer-checked:bg', 'tint' => 'peer-checked:bg', 'tintColor' => 'peer-checked:bg',
    'trackTintColor' => 'bg', 'offTintColor' => 'bg', 'thumbTintColor' => 'bg'
  }.freeze

  SWITCH_COLOUR_SLOTS.each do |attr, prefix|
    it "#{attr}: a name is the theme class" do
      out = html(attr => 'primary')
      expect(out).to include("#{prefix}-primary")
      expect(out).not_to include('[primary]')
    end

    it "#{attr}: a hex is the arbitrary class it was, an 8-digit one reordered for CSS" do
      expect(html(attr => '#34C759')).to include("#{prefix}-[#34C759]")
      expect(html(attr => '#800000FF')).to include("#{prefix}-[#0000FF80]")
    end

    it "#{attr}: a binding still rides the inline style" do
      out = html(attr => '@{c}')
      expect(out).not_to include('[@{')
      expect(out).to include('data.c')
    end
  end

  it 'a name outside colors.json resolves through the fallback, as map_color does elsewhere' do
    RjuiTools::React::TailwindMapper.configure_palette(theme_safe: Set.new, fallbacks: { 'brand' => '#123456' })
    expect(html('onTintColor' => 'brand')).to include('peer-checked:bg-[#123456]')
  end

  it 'the generated file with a named colour parses', :typescript_compile do
    layout = { 'type' => 'View', 'id' => 'root', 'child' => [
      { 'type' => 'Switch', 'id' => 's', 'onTintColor' => 'primary', 'thumbTintColor' => 'half', 'trackTintColor' => '#34C759' }
    ] }
    tsx = RjuiTools::React::ReactGenerator.new({ 'use_tailwind' => true, 'typescript' => true }).generate('Probe', layout).to_s
    expect(tsx).to include('peer-checked:bg-primary')
    expect("// @ts-nocheck\n#{tsx}").to compile_as_typescript
  end

  it 'the default colours are written as before' do
    out = html({})
    expect(out).to include('peer-checked:bg-[#34C759]')
  end
end
