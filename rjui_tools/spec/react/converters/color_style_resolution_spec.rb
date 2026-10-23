# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/label_converter'
require 'react/converters/view_converter'

# rjui-dynamic-color-binding-emits-raw-token
#
# A color attribute takes colors.json keys — that is what the static path
# means when it maps `background: warn_subtle` to `bg-warn_subtle`. When the
# same attribute has to land in an inline style, the key must still be
# resolved, at runtime, the way iOS (Configuration.getColor) and Android
# (ColorManager.compose.color) resolve theirs. Emitting it raw produced
# `background-color: warn_subtle`, which browsers drop in silence.
RSpec.describe 'inline color attributes resolve colors.json keys' do
  let(:config) { { 'typescript' => true } }

  def label(attrs)
    RjuiTools::React::Converters::LabelConverter.new(
      { 'type' => 'Label', 'text' => 'x' }.merge(attrs), config
    ).convert
  end

  describe 'dynamically bound colors' do
    # a custom property read by a class, so a state colour's class still wins
    # (ticket rjui-bound-background-overrides-tap-background)
    it 'resolves a bound background' do
      out = label('background' => '@{bgColor}')
      expect(out).to include("'--jui-bg': ColorManager.resolveColor(data.bgColor)")
      expect(out).to include('bg-[var(--jui-bg)]')
    end

    it 'resolves a bound fontColor' do
      out = label('fontColor' => '@{fgColor}')
      expect(out).to include("'--jui-color': ColorManager.resolveColor(data.fgColor)")
      expect(out).to include('text-[var(--jui-color)]')
    end

    it 'resolves a bound borderColor' do
      out = label('borderColor' => '@{lineColor}', 'borderWidth' => 1)
      expect(out).to include("'--jui-border-color': ColorManager.resolveColor(data.lineColor)")
    end

    it 'unwraps the JSX braces so the call is a valid argument' do
      out = label('background' => '@{bgColor}')
      expect(out).not_to include('resolveColor({')
    end
  end

  describe 'static values' do
    it 'resolves a key that shares an inline branch with a bound sibling' do
      # borderWidth is bound, so the whole border goes inline — the static
      # colour key rides along and used to be emitted raw.
      out = label('borderColor' => 'warn_border', 'borderWidth' => '@{w}')
      expect(out).to include("'--jui-border-color': ColorManager.resolveColor('warn_border')")
    end

    it 'leaves CSS literals alone rather than paying for a runtime call' do
      out = label('borderColor' => '#ff0000', 'borderWidth' => '@{w}')
      expect(out).to include("'--jui-border-color': '#ff0000'")
      expect(out).not_to include('resolveColor')
    end

    it 'leaves rgba() alone' do
      out = label('borderColor' => 'rgba(0, 0, 0, 0.5)', 'borderWidth' => '@{w}')
      expect(out).to include("'--jui-border-color': 'rgba(0, 0, 0, 0.5)'")
    end

    it 'keeps the class path untouched when nothing forces an inline style' do
      out = label('background' => 'warn_subtle')
      expect(out).to include('bg-warn_subtle')
      expect(out).not_to include('resolveColor')
    end
  end
end
