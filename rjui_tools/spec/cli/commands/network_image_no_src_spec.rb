# frozen_string_literal: true

require_relative '../../spec_helper'

# The canonical no-src chain (attribute_semantics.json -> networkImage.noSrc)
# is "with no src, display defaultImage". The template seeded `loading` to
# `true` unconditionally, and the effect that corrects it runs only after the
# first paint — so a no-src view painted the LOADING state once before
# settling: with a placeholder declared it showed the placeholder over
# defaultImage (the exact inversion of the chain), and without one it flashed
# the pulsing grey box. A settled screenshot cannot see either; a
# MutationObserver on the shipped build recorded both (plan 51-A, #19).
#
# Asserted on the template text because that is what ships: `rjui build` copies
# this file into the consumer's components tree verbatim.
RSpec.describe 'NetworkImage template no-src state' do
  let(:template) do
    File.read(File.expand_path('../../../lib/react/templates/network_image.tsx', __dir__))
  end

  it 'seeds the loading state from src rather than assuming a load is in flight' do
    expect(template).to include('useState(!!src)')
    expect(template).not_to include('useState(true)')
  end

  it 'still seeds the displayed image with defaultImage ahead of placeholder' do
    expect(template).to include('useState<string | null>(defaultImage || placeholder || null)')
  end
end
