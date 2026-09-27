# frozen_string_literal: true

require_relative '../spec_helper'
require_relative '../support/typescript_compiler'
require 'react/converters/label_converter'
require 'react/converters/view_converter'

# A single-run web label is a flex ROW: `items-*` is its vertical, `justify-*`
# its horizontal. Its text sits at the vertical its gravity names (top /
# bottom / centerVertical, center), else the middle; across, at textAlign's
# position, else at the horizontal its gravity names (left / right /
# centerHorizontal, center), else the start (4f 2026-09-27). Until jsonui-cli
# 1.9.0 BaseConverter also mapped gravity as a COLUMN's onto the row — measured
# in Chromium on 200 x 44 labels: `right` drew the text at the bottom,
# `bottom` at the bottom end, `centerVertical` in the middle across as well,
# `centerHorizontal` at the start. A container keeps TailwindMapper.map_gravity.
#
# The drawn arm is conformance/hosts/web/scripts/label_gravity_probe.mjs
# (`npm run label-gravity-probe`, at 400px and at the regular 1100px).
RSpec.describe RjuiTools::React::Converters::LabelConverter do
  def classes(extra)
    json = { 'type' => 'Label', 'id' => 'l', 'text' => 'Go', 'width' => 200, 'height' => 44 }.merge(extra)
    described_class.new(json, { 'use_tailwind' => true }).convert[/className="([^"]*)"/, 1].split
  end

  def alignment(extra)
    classes(extra).select { |c| c.start_with?('items-', 'justify-') }
  end

  it 'the vertical from gravity, else the middle' do
    expect(alignment({})).to eq(%w[items-center])
    expect(alignment('gravity' => 'top')).to eq(%w[items-start])
    expect(alignment('gravity' => 'bottom')).to eq(%w[items-end])
    expect(alignment('gravity' => 'centerVertical')).to eq(%w[items-center])
  end

  it 'the horizontal from gravity when textAlign is absent' do
    expect(alignment('gravity' => 'left')).to eq(%w[items-center justify-start])
    expect(alignment('gravity' => 'right')).to eq(%w[items-center justify-end])
    expect(alignment('gravity' => 'centerHorizontal')).to eq(%w[items-center justify-center])
    expect(alignment('gravity' => 'center')).to eq(%w[items-center justify-center])
    expect(alignment('gravity' => %w[bottom right])).to eq(%w[items-end justify-end])
  end

  it 'textAlign owns the horizontal when it is declared' do
    expect(alignment('gravity' => 'right', 'textAlign' => 'center')).to eq(%w[items-center justify-center])
  end

  it 'the labels it emits type-check' do
    elements = [{ 'gravity' => 'right' }, { 'gravity' => %w[bottom right] }, { 'gravity' => 'right', 'textAlign' => 'center' }].map do |extra|
      described_class.new({ 'type' => 'Label', 'id' => 'l', 'text' => 'Go', 'width' => 200, 'height' => 44 }.merge(extra),
                          { 'use_tailwind' => true }).convert
    end
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript
  end

  # A size class's gravity replaces the base one on the same axes (the
  # responsive override went through TailwindMapper.map_gravity, a column's
  # mapping, until jsonui-cli 1.9.0: a regular `right` put the text at the
  # bottom inside lg:, measured at 1100px).
  it 'a responsive gravity maps onto the same row axes' do
    json = { 'type' => 'Label', 'id' => 'l', 'text' => 'Go', 'width' => 200, 'height' => 44, 'gravity' => 'top',
             'responsive' => { 'regular' => { 'gravity' => 'right' } } }
    cls = described_class.new(json, { 'use_tailwind' => true }).convert[/className="([^"]*)"/, 1].split
    # (and its lines follow it: label_lines_follow_gravity_spec)
    expect(cls.select { |c| c.start_with?('lg:') }).to contain_exactly('lg:items-center', 'lg:justify-end', 'lg:text-right')
    expect(cls).to include('items-start')
  end

  it 'control: a container still maps gravity along its orientation' do
    view = RjuiTools::React::Converters::ViewConverter.new(
      { 'type' => 'View', 'id' => 'v', 'orientation' => 'vertical', 'gravity' => 'right', 'child' => [] }, { 'use_tailwind' => true }
    ).convert[/className="([^"]*)"/, 1].split
    expect(view).to include('items-end')
  end
end
