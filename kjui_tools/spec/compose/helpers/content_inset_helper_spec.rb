# frozen_string_literal: true

require 'spec_helper'
require 'compose/helpers/content_inset_helper'
require 'compose/components/scrollview_component'
require 'compose/components/collection_component'

# Plan 49 lane C, #4: `contentInsetAdjustmentBehavior` names something
# Compose does not have — UIScrollView adjusts for the safe area by default,
# Compose never does — so the values that need code are the opposite ones.
#
# What `always` adds is the part of the window's safe area the scrollable's
# frame OVERLAPS (UIKit's definition). Until jsonui-cli 2.5.40 kjui emitted
# the whole window's inset wherever the scrollable sat, and a Collection inside
# a SafeAreaView drew an empty band of the status bar's height (ticket
# kjui-collection-content-inset-always-adds-whole-window-insets). The overlap
# is KotlinJsonUI's rememberSafeAreaOverlap (its arithmetic is pinned in
# KotlinJsonUI's SafeAreaOverlapTest); this pins that every scrollable calls it
# and measures its own frame.
RSpec.describe KjuiTools::Compose::Helpers::ContentInsetHelper do
  described = KjuiTools::Compose::Helpers::ContentInsetHelper

  it 'emits nothing for never — Compose has no adjustment to switch off' do
    expect(described.safe_area_padding('never')).to be_nil
    expect(described.frame_modifiers('never')).to be_empty
    expect(described.imports_for('never')).to be_empty
    expect(described.wrap('X()', 'never', 1, horizontal: false)).to eq('X()')
  end

  it 'reads the overlap for always, automatic and scrollableAxes' do
    %w[always automatic scrollableAxes].each do |value|
      expect(described.safe_area_padding(value)).to eq('safeArea.contentPadding()'), value
      expect(described.frame_modifiers(value)).to eq(['.then(safeArea.modifier)']), value
    end
    expect(described.safe_area_padding('always', own: 'PaddingValues(all = 8.dp)')).to eq('safeArea.contentPadding(PaddingValues(all = 8.dp))')
  end

  it 'limits scrollableAxes to the scrolled axis' do
    expect(described.wrap('X()', 'always', 0, horizontal: false)).to include('val safeArea = rememberSafeAreaOverlap()')
    expect(described.wrap('X()', 'scrollableAxes', 0, horizontal: false)).to include('rememberSafeAreaOverlap(WindowInsetsSides.Vertical)')
    expect(described.wrap('X()', 'scrollableAxes', 0, horizontal: true)).to include('rememberSafeAreaOverlap(WindowInsetsSides.Horizontal)')
  end

  it 'accepts the declared spellings as written and ignores anything else' do
    expect(described.safe_area_padding('ALWAYS')).to be_nil
    expect(described.safe_area_padding('sideways')).to be_nil
    expect(described.safe_area_padding(nil)).to be_nil
  end

  it 'imports the helper, and WindowInsetsSides only for scrollableAxes' do
    expect(described.imports_for('always')).to eq([:safe_area_overlap])
    expect(described.imports_for('scrollableAxes')).to eq(%i[safe_area_overlap window_insets_sides_enum])
  end

  describe 'every scrollable that reads it' do
    def emit(json)
      imports = Set.new
      klass = json['type'] == 'Scroll' ? KjuiTools::Compose::Components::ScrollViewComponent
                                       : KjuiTools::Compose::Components::CollectionComponent
      result = klass.generate(json, 1, imports, 'Column')
      [result.is_a?(Hash) ? "#{result[:code]}#{result[:closing]}" : result, imports]
    end

    base = { 'type' => 'Collection', 'id' => 'list', 'items' => '@{i}', 'offsetY' => 4 }
    ROUTES_OF_THE_INSET = {
      'ScrollView' => { 'type' => 'Scroll', 'id' => 'list', 'offsetY' => 4, 'child' => [] },
      'lazy stack' => base.merge('sections' => [{ 'cell' => 'C', 'columns' => 1 }]),
      'lazy grid' => base.merge('sections' => [{ 'cell' => 'C', 'columns' => 2 }]),
      'pager' => base.merge('orientation' => 'horizontal', 'paging' => true, 'sections' => [{ 'cell' => 'C' }]),
      'flow' => base.merge('layout' => 'flow', 'sections' => [{ 'cell' => 'C' }]),
      'non-lazy column' => base.merge('lazy' => 'none', 'sections' => [{ 'cell' => 'C' }]),
      'non-lazy row' => base.merge('lazy' => 'none', 'orientation' => 'horizontal', 'sections' => [{ 'cell' => 'C' }])
    }.freeze

    ROUTES_OF_THE_INSET.each do |route, json|
      it "#{route}: measures its own frame and adds the overlap" do
        code, imports = emit(json.merge('insets' => 12, 'contentInsetAdjustmentBehavior' => 'always'))
        expect(code).to start_with("    // Requires KotlinJsonUI >= #{described::MIN_LIBRARY_VERSION} (safe-area overlap)\n    run {\n" \
                                   "        val safeArea = rememberSafeAreaOverlap()\n")
        expect(code.rstrip).to end_with("\n    }")
        expect(code).to include('safeArea.contentPadding(')
        expect(code).not_to include('WindowInsets.safeDrawing')
        # The frame: after the offset (the box drawn), before the padding and the scroll.
        chain = code.lines.map(&:strip)
        frame = chain.index('.then(safeArea.modifier)')
        expect(frame).not_to be_nil
        offset = chain.index { |l| l.start_with?('.offset(') }
        expect(offset).to be < frame if offset
        after = chain[frame..].find { |l| l.match?(/\A\.(padding|verticalScroll|horizontalScroll)\(/) }
        expect(chain.index(after)).to be > frame if after
        expect(imports).to include(:safe_area_overlap)
      end

      it "#{route}: never emits none of it" do
        code, imports = emit(json.merge('insets' => 12, 'contentInsetAdjustmentBehavior' => 'never'))
        expect(code).not_to include('safeArea')
        expect(code).not_to include('run {')
        expect(imports).not_to include(:safe_area_overlap)
      end
    end
  end
end
