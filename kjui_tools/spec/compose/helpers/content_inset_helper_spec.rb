# frozen_string_literal: true

require 'spec_helper'
require 'compose/helpers/content_inset_helper'
require 'compose/components/scrollview_component'
require 'compose/components/collection_component'

# Plan 49 lane C, #4. `contentInsetAdjustmentBehavior` names something Compose
# does not have — UIScrollView adjusts for the safe area by default and the
# attribute stops it, while Compose never adjusts at all. The EFFECT ports:
# `WindowInsets.safeDrawing.asPaddingValues()` is the value UIKit would have
# computed, handed to the `contentPadding` kjui already passes for the numeric
# spelling. So the values that need code are the opposite ones from iOS.
RSpec.describe KjuiTools::Compose::Helpers::ContentInsetHelper do
  described = KjuiTools::Compose::Helpers::ContentInsetHelper

  it 'emits nothing for never — Compose has no adjustment to switch off' do
    # This is also what keeps every existing Compose screen where it is.
    expect(described.safe_area_padding('never')).to be_nil
    expect(described.imports_for('never')).to be_empty
  end

  it 'emits the full safe-area inset for always and automatic' do
    # Compose has no "depending on context", so automatic is always.
    expect(described.safe_area_padding('always')).to eq('WindowInsets.safeDrawing.asPaddingValues()')
    expect(described.safe_area_padding('automatic')).to eq('WindowInsets.safeDrawing.asPaddingValues()')
  end

  it 'insets only the scrolled axis for scrollableAxes' do
    expect(described.safe_area_padding('scrollableAxes'))
      .to eq('WindowInsets.safeDrawing.only(WindowInsetsSides.Vertical).asPaddingValues()')
    expect(described.safe_area_padding('scrollableAxes', horizontal: true))
      .to eq('WindowInsets.safeDrawing.only(WindowInsetsSides.Horizontal).asPaddingValues()')
  end

  it 'accepts the declared spellings case-insensitively and ignores anything else' do
    expect(described.safe_area_padding('ALWAYS')).not_to be_nil
    expect(described.safe_area_padding('sideways')).to be_nil
    expect(described.safe_area_padding(nil)).to be_nil
  end

  it 'asks for WindowInsetsSides only when the axis form is emitted' do
    expect(described.imports_for('always')).to eq([:window_insets])
    expect(described.imports_for('scrollableAxes')).to eq(%i[window_insets window_insets_sides])
  end

  describe 'both scrollables, and both of Collection\'s emitters' do
    def padding_line(json)
      imports = Set.new
      result = described_klass(json).generate(json, 0, imports, nil)
      code = result.is_a?(Hash) ? result[:code] : result
      [code.lines.grep(/contentPadding/).map(&:strip).first, imports]
    end

    def described_klass(json)
      json['type'] == 'Scroll' ? KjuiTools::Compose::Components::ScrollViewComponent
                               : KjuiTools::Compose::Components::CollectionComponent
    end

    let(:scroll)       { { 'type' => 'Scroll', 'child' => [] } }
    # `single_column_sections?` picks the emitter, so both shapes are pinned:
    # a change that reaches only one reaches about half the collections.
    let(:stack_path)   { { 'type' => 'Collection', 'items' => '@{i}', 'sections' => [{ 'cell' => 'C', 'columns' => 1 }] } }
    let(:grid_path)    { { 'type' => 'Collection', 'items' => '@{i}', 'sections' => [{ 'cell' => 'C', 'columns' => 2 }] } }

    it 'emits the inset from every path' do
      [scroll, stack_path, grid_path].each do |base|
        line, imports = padding_line(base.merge('contentInsetAdjustmentBehavior' => 'always'))
        expect(line).to include('WindowInsets.safeDrawing.asPaddingValues()')
        expect(imports).to include(:window_insets)
      end
    end

    it 'emits nothing for never from every path' do
      [scroll, stack_path, grid_path].each do |base|
        line, = padding_line(base.merge('contentInsetAdjustmentBehavior' => 'never'))
        expect(line).to be_nil
      end
    end

    it 'lets a declared numeric contentPadding win from every Collection path' do
      # The author named an exact value; this attribute only says "clear the
      # system bars", not "and discard the number I wrote".
      [stack_path, grid_path].each do |base|
        line, = padding_line(base.merge('contentPadding' => 12, 'contentInsetAdjustmentBehavior' => 'always'))
        expect(line).to eq('contentPadding = PaddingValues(12.dp),')
      end
    end
  end
end
