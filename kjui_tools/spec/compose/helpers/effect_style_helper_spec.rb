# frozen_string_literal: true

require 'spec_helper'
require 'compose/helpers/effect_style_helper'
require 'compose/helpers/modifier_builder'
require 'compose/components/blurview_component'

# Plan 49 lane C. `effectStyle` is declared on `common`, not just on Blur, and
# only the Blur component read it — so a plain View declaring a material got
# nothing. The vocabulary lives in one helper now so the component that owns
# the concept and the common spelling cannot answer differently, which is the
# shape rjui settled on (base_converter.rb:1033).
RSpec.describe KjuiTools::Compose::Helpers::EffectStyleHelper do
  described = KjuiTools::Compose::Helpers::EffectStyleHelper

  # The fourteen spellings `common.effectStyle` enumerates.
  DECLARED = %w[
    Light Dark ExtraLight Regular Prominent UltraThin Thin Thick Chrome
    systemMaterial systemUltraThinMaterial systemThinMaterial
    systemThickMaterial systemChromeMaterial
  ].freeze

  it 'answers for every declared spelling' do
    DECLARED.each do |v|
      expect(described.scrim(v)).not_to be_nil, "no scrim for #{v}"
      expect(described.blur_dp(v)).not_to be_nil, "no blur for #{v}"
    end
  end

  it 'resolves each alias onto the spelling it normalises to' do
    {
      'systemMaterial' => 'Regular', 'systemUltraThinMaterial' => 'UltraThin',
      'systemThinMaterial' => 'Thin', 'systemThickMaterial' => 'Thick',
      'systemChromeMaterial' => 'Chrome'
    }.each do |alias_name, target|
      expect(described.scrim(alias_name)).to eq(described.scrim(target))
      expect(described.blur_dp(alias_name)).to eq(described.blur_dp(target))
    end
  end

  it 'falls back to the declared default for an unknown value' do
    expect(described.scrim('sideways')).to eq(described.scrim('Regular'))
  end

  it 'emits nothing when the attribute is absent' do
    expect(described.scrim(nil)).to be_nil
    expect(described.blur_dp('')).to be_nil
  end

  describe 'the common path' do
    def background_for(json)
      KjuiTools::Compose::Helpers::ModifierBuilder.build_background(json, Set.new).join(' ')
    end

    it 'gives a plain View the material it declared' do
      out = background_for('type' => 'View', 'effectStyle' => 'Chrome')
      expect(out).to include('.background(Color.White.copy(alpha = 0.95f))')
      expect(out).to include('.blur(20.dp)')
    end

    it 'leaves Blur alone — it builds a richer chain from the same tables' do
      expect(background_for('type' => 'Blur', 'effectStyle' => 'Light')).to eq('')
    end

    it 'emits nothing when no material is declared' do
      expect(background_for('type' => 'View')).to eq('')
    end
  end

  describe 'Blur keeps the output it had before the tables were shared' do
    # Folding Blur onto the shared table must not move the component that
    # owned the concept: these are the alphas it emitted beforehand.
    {
      'Light' => 'Color.White.copy(alpha = 0.4f)',
      'Dark' => 'Color.Black.copy(alpha = 0.4f)',
      'ExtraLight' => 'Color.White.copy(alpha = 0.6f)'
    }.each do |style, scrim|
      it "keeps #{style} at #{scrim}" do
        result = KjuiTools::Compose::Components::BlurviewComponent.generate(
          { 'type' => 'Blur', 'effectStyle' => style, 'child' => [] }, 0, Set.new, nil
        )
        code = result.is_a?(Hash) ? result[:code] : result
        expect(code).to include(".background(#{scrim})")
        # blurRadius stays its own attribute, not derived from the style.
        expect(code).to include('.blur(10.dp)')
      end
    end
  end
end
