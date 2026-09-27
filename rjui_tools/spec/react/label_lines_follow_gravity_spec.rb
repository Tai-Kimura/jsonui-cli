# frozen_string_literal: true

require_relative '../spec_helper'
require_relative '../support/typescript_compiler'
require 'react/converters/label_converter'

# The lines of a multi-line or wrapped Label follow the Label rule across:
# textAlign, else the horizontal part of gravity (center / centerHorizontal,
# right, left), else the start (the SSoT's Label.textAlign, 4f round 6,
# jsonui-cli 1.9.0). The flex `justify-*` of a single-run label places its
# text's box; a wrapped text fills the row, and only text-align places its
# lines — so gravity also gives `text-center` / `text-right` / `text-left`
# when textAlign is not declared, on the single-run, the clamped and the
# multi-run label alike. Measured in Chromium: until then a 150px label with
# gravity center or right drew every wrapped line at the start, and so did the
# shorter line of a two-line wrapContent one.
#
# The drawn arm is conformance/hosts/web/scripts/label_gravity_probe.mjs (the
# ml_* and wrap_* labels, `npm run label-gravity-probe`).
RSpec.describe RjuiTools::React::Converters::LabelConverter do
  def label(extra, config = {})
    described_class.new({ 'type' => 'Label', 'id' => 'l', 'text' => "Go\nGo Go Go Go", 'lines' => 0 }.merge(extra),
                        { 'use_tailwind' => true }.merge(config)).convert
  end

  def line_align(extra)
    label(extra)[/className="([^"]*)"/, 1].split.grep(/\Atext-(left|center|right|start)\z/)
  end

  it "without textAlign, gravity's horizontal part aligns the lines" do
    expect(line_align('gravity' => 'center')).to eq(%w[text-center])
    expect(line_align('gravity' => 'centerHorizontal')).to eq(%w[text-center])
    expect(line_align('gravity' => 'right')).to eq(%w[text-right])
    expect(line_align('gravity' => %w[bottom right])).to eq(%w[text-right])
    expect(line_align('gravity' => 'left')).to eq(%w[text-left])
  end

  it 'a clamped and a multi-run label too' do
    expect(line_align('gravity' => 'center', 'lines' => 3)).to eq(%w[text-center])
    expect(line_align('gravity' => 'right', 'linkable' => true)).to eq(%w[text-right])
  end

  it 'control: textAlign owns the lines, and with neither they stay at the start' do
    expect(line_align('gravity' => 'right', 'textAlign' => 'center')).to eq(%w[text-center])
    expect(line_align({})).to eq([])
    expect(line_align('gravity' => 'top')).to eq([])
  end

  it 'a responsive gravity re-aligns the lines inside its size class, and back to the start without one' do
    cls = label('gravity' => 'center', 'responsive' => { 'regular' => { 'gravity' => 'top' } })[/className="([^"]*)"/, 1].split
    expect(cls).to include('text-center', 'lg:text-start')
  end

  it 'the labels it emits type-check' do
    elements = [{ 'gravity' => 'center' }, { 'gravity' => 'right', 'lines' => 3 }].map { |e| label(e, 'typescript' => true) }
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript
  end
end
