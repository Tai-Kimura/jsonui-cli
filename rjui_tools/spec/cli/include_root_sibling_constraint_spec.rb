# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'
require 'rbconfig'
require_relative '../spec_helper'
require_relative '../support/headless_chromium'
require_relative '../support/rjui_chromium_draw'
require 'core/config_manager'

# An included layout's root constrained against a sibling of the include
# (alignTopOfView and the other nine) is laid out against that sibling, as
# sjui and kjui (which expand the include first) lay it out (ticket
# rjui-include-root-sibling-constraint-dropped). Measured on v2.5.24 in
# Chromium, a 20x20 root and a 10x10 anchor at margin 50/50 in a 100x100
# frame: the direct child drew at (0,30) for alignTopOfView, (50,0) for
# alignLeftView, (0,45) for alignCenterVerticalView; the include's root drew
# at (0,0) for every one of the ten — the container never saw the constraint,
# and the hoisted applyRelativePositions had no spec for it. Under an include
# with an id the root carries the prefixed id; the anchor, a sibling of the
# include, does not.
#
# Each project is built by a copied rjui (jui build's prefix decision on);
# its generated components, with the helpers they call, are drawn in
# headless Chromium by a small element factory that runs the components'
# effects after mounting (include_reads_the_including_data_spec.rb takes the
# same route through esbuild).
RSpec.describe 'an included root constrained against a sibling of the include, through rjui build' do

  def self.box(id, extra = {})
    { 'type' => 'View', 'id' => id, 'width' => 20, 'height' => 20, 'background' => '#FF0000' }.merge(extra)
  end

  def self.anchor(id) = box(id, 'width' => 10, 'height' => 10, 'leftMargin' => 50, 'topMargin' => 50, 'background' => '#00AA00')

  def self.frame(key, kids)
    { 'type' => 'View', 'width' => 120, 'height' => 120,
      'child' => [{ 'type' => 'View', 'id' => "frame_#{key}", 'width' => 100, 'height' => 100, 'child' => kids }] }
  end

  # key => [constraint attribute, include id or nil, nested (the partial's
  # root is itself an include)]
  IRSC_CASES = {
    'ato' => ['alignTopOfView', nil, false],
    'aro' => ['alignRightOfView', nil, false],
    'al' => ['alignLeftView', nil, false],
    'ab' => ['alignBottomView', nil, false],
    'acv' => ['alignCenterVerticalView', nil, false],
    'idato' => ['alignTopOfView', 'inc', false],
    'nest' => ['alignTopOfView', 'outer', true],
    # row D4: both elements inside the partial, the include with an id —
    # the elements carry `incS…` / `incA…` and the constraint has to name
    # them so
    'inner' => ['alignTopOfView', 'inc', :inner],
    'innerl' => ['alignLeftView', 'inc', :inner]
  }.freeze

  def self.layouts
    files = {}
    frames = []
    IRSC_CASES.each do |key, (attr, include_id, nested)|
      %w[direct inc].each do |mode|
        k = "#{key}_#{mode}"
        if nested == :inner
          inner = { 'type' => 'View', 'width' => 'matchParent', 'height' => 'matchParent',
                    'child' => [box("s_#{k}", attr => "a_#{k}"), anchor("a_#{k}")] }
          if mode == 'inc'
            files["parts/p_#{k}"] = inner
            inner = { 'include' => "parts/p_#{k}", 'id' => include_id }
          end
          frames << frame(k, [inner])
          next
        end
        subject = box("s_#{k}", attr => "a_#{k}")
        if mode == 'inc'
          if nested
            files["parts/p_#{k}_inner"] = subject
            files["parts/p_#{k}"] = { 'include' => "parts/p_#{k}_inner", 'id' => 'mid' }
          else
            files["parts/p_#{k}"] = subject
          end
          subject = { 'include' => "parts/p_#{k}" }
          subject['id'] = include_id if include_id
        end
        frames << frame(k, [subject, anchor("a_#{k}")])
      end
    end
    files['screen'] = { 'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'wrapContent',
                        'orientation' => 'horizontal', 'flexWrap' => 'wrap', 'child' => frames }
    files
  end

  def self.build(dir) = RjuiChromiumDraw.build(dir, layouts)

  def self.draw(generated) = RjuiChromiumDraw.draw(generated)

  it 'hoists a spec for the include, found by the id its root carries here' do
    Dir.mktmpdir('rjui_include_sibling') do |dir|
      screen = File.read(File.join(self.class.build(dir), 'components', 'Screen.tsx'))
      expect(screen).to include("{ id: jsonuiIncludeId(idPrefix, \"s_ato_inc\"), above: 'a_ato_inc' }")
      expect(screen).to include("{ id: jsonuiIncludeId(jsonuiIncludePrefix(idPrefix, \"inc\"), \"s_idato_inc\"), above: 'a_idato_inc' }")
      expect(screen).to include('{ id: jsonuiIncludeId(jsonuiIncludePrefix(jsonuiIncludePrefix(idPrefix, "outer"), "mid"), ' \
                                "\"s_nest_inc\"), above: 'a_nest_inc' }")
      # control: a direct child's spec is as it was
      expect(screen).to include("{ id: 's_ato_direct', above: 'a_ato_direct' }")
      # inside an included layout the spec names its own elements as the DOM does
      part = File.read(File.join(dir, 'src', 'generated', 'components', 'parts', 'PInnerInc.tsx'))
      expect(part).to include('{ id: jsonuiIncludeId(idPrefix, "s_inner_inc"), above: jsonuiIncludeId(idPrefix, "a_inner_inc") }')
      # the include is absolute, as the constrained direct child is
      expect(screen).to match(/<PAtoInc idPrefix=\{idPrefix\} jsonuiPlace=\{\{ add: "absolute" \}\} \/>/)
    end
  end

  it 'draws the root where the same JSON draws as a direct child' do
    HeadlessChromium.ensure!(self)
    unless RjuiChromiumDraw.tools_installed?
      reason = 'esbuild / tailwindcss / playwright are not installed under spec/support'
      raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

      skip reason
    end

    Dir.mktmpdir('rjui_include_sibling') do |dir|
      got = self.class.draw(self.class.build(dir))
      at = ->(k) { got.fetch(k)[1..] }
      # the measure: the direct children are where the constraint puts them
      expect(%w[ato aro al ab acv].map { |k| at.call("#{k}_direct") })
        .to eq([[0, 30], [60, 0], [50, 0], [0, 40], [0, 45]]), got.inspect
      IRSC_CASES.each_key do |key|
        expect(at.call("#{key}_inc")).to eq(at.call("#{key}_direct")), "#{key}: #{got.inspect}"
      end
      expect(got['idato_inc'][0]).to eq('incSIdatoInc')
      expect(got['inner_inc'][0]).to eq('incSInnerInc')
    end
  end
end
