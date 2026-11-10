# frozen_string_literal: true

require 'tmpdir'
require_relative '../spec_helper'
require_relative '../support/headless_chromium'
require_relative '../support/rjui_chromium_draw'

# A constraint that names a gone element does not apply (attribute_semantics
# visibility.goneModel; ticket relative-constraint-to-gone-anchor-keeps-its-
# place). A bound "gone" leaves the element out of the DOM and the helper
# found no anchor; a literal "gone" draws it with display:none, and the helper
# measured that as a box — a point at the container's top-left. Measured by
# triage support 2 in Chromium on v2.5.26, a 20x20 anchor centred in a 100x100
# frame and a 10x10 child: 12 of the 20 literal rows were off the measure
# (the same child with no anchor and no constraint) — alignTopOfView put it at
# y=-10, alignCenterHorizontalView at x=-5. The child is now where the
# measure is, for each of the ten constraints, with its anchor an include's
# root, and inside an include with an id.
RSpec.describe 'a constraint naming a literal gone anchor, through rjui build' do
  GONE_CONSTRAINTS = %w[
    alignTopOfView alignBottomOfView alignLeftOfView alignRightOfView
    alignTopView alignBottomView alignLeftView alignRightView
    alignCenterVerticalView alignCenterHorizontalView
  ].freeze

  def self.subject_box(id, extra = {})
    { 'type' => 'View', 'id' => id, 'width' => 10, 'height' => 10, 'leftMargin' => 10, 'topMargin' => 10,
      'background' => '#FF0000' }.merge(extra)
  end

  def self.anchor(id)
    { 'type' => 'View', 'id' => id, 'width' => 20, 'height' => 20, 'centerInParent' => true,
      'visibility' => 'gone', 'background' => '#0000FF' }
  end

  def self.frame(key, kids)
    { 'type' => 'View', 'width' => 120, 'height' => 120,
      'child' => [{ 'type' => 'View', 'id' => "frame_#{key}", 'width' => 100, 'height' => 100, 'child' => kids }] }
  end

  # key => frame; `<n>_gone` with the anchor, `<n>_none` the measure.
  def self.layouts
    files = {}
    frames = []
    GONE_CONSTRAINTS.each_with_index do |attr, i|
      frames << frame("#{i}_gone", [subject_box("s_#{i}_gone", attr => "a_#{i}_gone"), anchor("a_#{i}_gone")])
      frames << frame("#{i}_none", [subject_box("s_#{i}_none")])
    end
    # the gone anchor is an include's root
    files['parts/gone_root'] = anchor('a_incroot')
    frames << frame('incroot_gone', [subject_box('s_incroot', 'alignTopOfView' => 'a_incroot'), { 'include' => 'parts/gone_root' }])
    # both inside a partial, under an include with an id
    files['parts/gone_pair'] = { 'type' => 'View', 'width' => 'matchParent', 'height' => 'matchParent',
                                 'child' => [subject_box('s_inner', 'alignCenterHorizontalView' => 'a_inner'), anchor('a_inner')] }
    frames << frame('inner_gone', [{ 'include' => 'parts/gone_pair', 'id' => 'inc' }])
    files['screen'] = { 'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'wrapContent',
                        'orientation' => 'horizontal', 'flexWrap' => 'wrap', 'child' => frames }
    files
  end

  it 'draws each child where the same child with no anchor and no constraint is' do
    HeadlessChromium.ensure!(self)
    unless RjuiChromiumDraw.tools_installed?
      reason = 'esbuild / tailwindcss / playwright are not installed under spec/support'
      raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

      skip reason
    end

    Dir.mktmpdir('rjui_gone_anchor') do |dir|
      got = RjuiChromiumDraw.draw(RjuiChromiumDraw.build(dir, self.class.layouts))
      at = ->(k) { got.fetch(k)[1..] }
      measure = at.call('0_none')
      expect(measure).to eq([10, 10]), got.inspect
      GONE_CONSTRAINTS.each_index do |i|
        expect(at.call("#{i}_none")).to eq(measure), got.inspect
        expect(at.call("#{i}_gone")).to eq(measure), "#{GONE_CONSTRAINTS[i]}: #{got.inspect}"
      end
      expect(at.call('incroot_gone')).to eq(measure), got.inspect
      expect(got['inner_gone']).to eq(['incSInner', *measure]), got.inspect
    end
  end
end
