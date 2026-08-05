# frozen_string_literal: true

require 'spec_helper'
require 'compose/helpers/content_scale_helper'

# Plan 49 lane C, #11b. Image and NetworkImage each carried a copy of the
# contentMode vocabulary and the copies had drifted in two places — and the
# drift was interesting because neither copy was wholly right, which is why
# folding one into the other by inspection was impossible.
#
# The answer was recorded, not derivable: attribute_semantics.json#image holds
# the 2026-08-03 user rulings — the default is `fit` on every platform, and
# all three platforms implement the full mapping including the positional
# modes. NetworkImage was right about the default; Image was right about
# `center`.
RSpec.describe KjuiTools::Compose::Helpers::ContentScaleHelper do
  described = KjuiTools::Compose::Helpers::ContentScaleHelper

  around do |example|
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
    example.run
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  it 'maps the canonical `fit` spelling, which was missing from the table' do
    # It only ever worked because it fell through to a caller-supplied
    # default that happened to be Fit — and Image supplied none, so
    # `contentMode: "fit"` emitted nothing at all there.
    expect(described.scale_expression('fit')).to eq('ContentScale.Fit')
    expect(described.scale_expression('aspectfit')).to eq('ContentScale.Fit')
  end

  it 'resolves an unknown value to the declared default rather than to nothing' do
    expect(described.scale_expression('sideways')).to eq('ContentScale.Fit')
  end

  it 'still emits nothing when the attribute is absent' do
    expect(described.scale_expression(nil)).to be_nil
  end

  it 'treats fill and scaleToFill as the stretch' do
    expect(described.scale_expression('fill')).to eq('ContentScale.FillBounds')
    expect(described.scale_expression('scaletofill')).to eq('ContentScale.FillBounds')
  end

  it 'draws the positional modes unscaled' do
    %w[center top bottom left right].each do |mode|
      expect(described.scale_expression(mode)).to eq('ContentScale.None')
    end
  end

  it 'aligns all five positional modes, center included' do
    expect(described.alignment_expression('center')).to eq('Alignment.Center')
    expect(described.alignment_expression('top')).to eq('Alignment.TopCenter')
    expect(described.alignment_expression('bottom')).to eq('Alignment.BottomCenter')
    expect(described.alignment_expression('left')).to eq('Alignment.CenterStart')
    expect(described.alignment_expression('right')).to eq('Alignment.CenterEnd')
  end

  it 'gives a non-positional mode no alignment' do
    expect(described.alignment_expression('fit')).to be_nil
  end

  describe 'both callers see the same vocabulary and the same default' do
    # The regression this file exists to prevent: a caller narrowing the
    # table or supplying its own fallback, which is how the drift started.
    it 'exposes one table and one default' do
      expect(described::SCALE_MAPPING.keys).to include('fit', 'center')
      expect(described::ALIGNMENT_MAPPING.keys).to match_array(%w[top bottom left right center])
      expect(described::DEFAULT_SCALE).to eq('ContentScale.Fit')
    end

    it 'resolves a bound mode at runtime with the full table on both arms' do
      out = described.scale_expression('@{mode}')
      expect(out).to start_with('when (')
      expect(out).to include('"fit" -> ContentScale.Fit')
      expect(out).to include('else -> ContentScale.Fit')
    end
  end
end
