#!/usr/bin/env ruby

require_relative '../spec_helper'
require_relative '../../lib/core/typed_attributes'

RSpec.describe RjuiTools::Core::TypedAttributes do
  def attrs(json, normalized: false)
    described_class.new(json, normalized: normalized)
  end

  describe 'typed extraction' do
    it 'returns static values in raw layout representation' do
      a = attrs({'type' => 'Label', 'text' => 'Hello', 'fontSize' => 16})
      expect(a['text']).to eq('Hello')
      expect(a['fontSize']).to eq(16)
    end

    it 'returns binding-capable values as the original @{...} string' do
      a = attrs({'type' => 'Label', 'text' => '@{message}'})
      expect(a['text']).to eq('@{message}')
    end

    it 'preserves false booleans' do
      a = attrs({'type' => 'Button', 'text' => 'Tap', 'enabled' => false})
      expect(a['enabled']).to be false
      expect(a.key?('enabled')).to be true
    end

    it 'drops mistyped values (coercion)' do
      a = attrs({'type' => 'Label', 'fontSize' => { 'bad' => true }})
      expect(a['fontSize']).to be_nil
    end

    it 'merges common attributes for every component' do
      a = attrs({'type' => 'Slider', 'background' => '#FFFFFF'})
      expect(a['background']).to eq('#FFFFFF')
    end

    it 'falls back to CommonAttributes for unknown component types' do
      a = attrs({'type' => 'CustomThing', 'background' => '#FFFFFF', 'customProp' => 7})
      expect(a['background']).to eq('#FFFFFF')
      expect(a['customProp']).to eq(7) # undeclared → raw passthrough
    end
  end

  describe 'alias resolution' do
    it 'resolves alias spellings on L0 layouts' do
      a = attrs({'type' => 'Slider', 'minimumValue' => 5})
      expect(a['minimum']).to eq(5)
    end

    it 'prefers the canonical spelling when both are present' do
      a = attrs({'type' => 'Slider', 'minimum' => 3, 'minimumValue' => 5})
      expect(a['minimum']).to eq(3)
    end

    it 'redirects alias keys to the canonical row' do
      a = attrs({'type' => 'Slider', 'minimum' => 3})
      expect(a['minimumValue']).to eq(3)
    end

    it 'ignores alias spellings on normalized layouts' do
      a = attrs({ 'type' => 'Slider', 'minimumValue' => 5 }, normalized: true)
      expect(a['minimum']).to be_nil
    end

    it 'ignores alias spellings for standalone-row aliases on normalized layouts' do
      # `alpha` is both an alias of `opacity` and its own definitions row;
      # on an L1 layout the normalizer has rewritten it, so a leftover
      # spelling must not leak into the canonical name.
      a = attrs({ 'type' => 'View', 'alpha' => 0.5 }, normalized: true)
      expect(a['opacity']).to be_nil
    end

    it 'reads the alpha alias into opacity on L0 layouts' do
      a = attrs({'type' => 'View', 'alpha' => 0.5})
      expect(a['opacity']).to eq(0.5)
    end
  end

  describe 'raw lookup keys' do
    it 'passes arbitrary CSS width/height strings through' do
      a = attrs({'type' => 'View', 'width' => '50%', 'height' => 'calc(100vh - 4rem)'})
      expect(a['width']).to eq('50%')
      expect(a['height']).to eq('calc(100vh - 4rem)')
    end

    it 'passes edge-inset padding arrays through' do
      a = attrs({'type' => 'View', 'padding' => [8, 16]})
      expect(a['padding']).to eq([8, 16])
    end
  end

  describe 'binding-only attributes (kind :binding — raw preserved)' do
    it 'passes onClick action objects through the typed path' do
      handler = { 'action' => 'link', 'url' => 'https://example.invalid' }
      a = attrs({'type' => 'Button', 'text' => 'Go', 'onClick' => handler})
      expect(a['onClick']).to eq(handler)
    end

    it 'keeps onClick binding strings verbatim (@{} wrapper recovered)' do
      a = attrs({'type' => 'Button', 'text' => 'Go', 'onClick' => '@{handleTap}'})
      expect(a['onClick']).to eq('@{handleTap}')
    end

    it 'keeps bare handler names as-is' do
      a = attrs({'type' => 'Button', 'text' => 'Go', 'onClick' => 'handleTap'})
      expect(a['onClick']).to eq('handleTap')
    end
  end

  describe 'lenient enum matching' do
    it 'passes declared values through verbatim' do
      a = attrs({'type' => 'Label', 'text' => 'x', 'textAlign' => 'Left'})
      expect(a['textAlign']).to eq('Left')
    end

    it 'matches case-insensitively (spelling the enum does not declare)' do
      # Button only declares 'Left'/'Center'/'Right'; the web mapper is
      # case-insensitive, so lowercase spellings must survive extraction.
      a = attrs({'type' => 'Button', 'text' => 'Go', 'textAlign' => 'left'})
      expect(a['textAlign']).to eq('left')
    end

    it 'warns but passes unknown enum values through (never nil-drops)' do
      warnings = []
      JsonUI::Generated::AttrWarnings.handler = ->(msg) { warnings << msg }
      a = attrs({'type' => 'Label', 'text' => 'x', 'visibility' => 'bogus'})
      expect(a['visibility']).to eq('bogus')
      expect(warnings).to include(a_string_including('common.visibility'))
    ensure
      JsonUI::Generated::AttrWarnings.handler = nil
    end

    it 'passes non-string enum values through (resize boolean truthiness)' do
      a = attrs({'type' => 'TextView', 'resize' => true})
      expect(a['resize']).to be true
    end
  end

  describe 'declared? (metadata contract)' do
    it 'is true for canonical names, alias spellings, and common keys' do
      a = attrs({'type' => 'Slider'})
      expect(a.declared?('minimum')).to be true
      expect(a.declared?('minimumValue')).to be true
      expect(a.declared?('background')).to be true
    end

    it 'is false for undeclared keys' do
      a = attrs({'type' => 'Slider'})
      expect(a.declared?('customProp')).to be false
    end
  end

  describe 'undeclared keys' do
    it 'passes structural/internal keys through' do
      a = attrs({'type' => 'View', '_overlay' => true, 'shared_data' => { 'x' => 1 }})
      expect(a['_overlay']).to be true
      expect(a['shared_data']).to eq('x' => 1)
    end
  end
end
