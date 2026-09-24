# frozen_string_literal: true

require_relative '../spec_helper'
require 'react/tailwind_mapper'

# rjui-gravity-centervertical-centers-the-horizontal-axis-too: on a flex-col
# container (a vertical View, or a View with no orientation and one child) the
# horizontal axis was read with `include?('center')`, which also matches
# `centerVertical`. A gravity naming only the vertical axis centred the
# horizontal one as well — and `["centerVertical", "left"]` was centred despite
# naming `left` — on web only; ios and android leave an unnamed axis at the
# container default (attribute_semantics.json -> gravityDefaults).
RSpec.describe RjuiTools::React::TailwindMapper do
  def gravity_classes(gravity, orientation = nil)
    described_class.map_gravity(gravity, orientation)
  end

  [nil, 'vertical'].each do |orientation|
    context "on a flex-col container (orientation #{orientation.inspect})" do
      it 'leaves the horizontal axis alone for centerVertical' do
        expect(gravity_classes('centerVertical', orientation)).to eq(['justify-center'])
        expect(gravity_classes(['centerVertical'], orientation)).to eq(['justify-center'])
      end

      it 'honours the horizontal value named beside centerVertical' do
        expect(gravity_classes(%w[centerVertical left], orientation)).to eq(%w[items-start justify-center])
        expect(gravity_classes('centerVertical|right', orientation)).to eq(%w[items-end justify-center])
      end

      # Unchanged: the values that do name the horizontal axis.
      it 'still centres the horizontal axis for centerHorizontal and center' do
        expect(gravity_classes('centerHorizontal', orientation)).to eq(['items-center'])
        expect(gravity_classes(%w[centerVertical centerHorizontal], orientation))
          .to eq(%w[items-center justify-center])
        expect(gravity_classes('center', orientation)).to eq(%w[items-center justify-center])
      end
    end
  end

  it 'leaves a horizontal container as it was' do
    expect(gravity_classes('centerVertical', 'horizontal')).to eq(['items-center'])
    expect(gravity_classes('centerHorizontal', 'horizontal')).to eq(['justify-center'])
  end
end
