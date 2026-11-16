# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/button_converter'
require 'react/converters/label_converter'
require 'react/converters/icon_label_converter'

# The SSoT declares fontWeight ["string","number"] on all three platforms,
# and CSS takes a numeric font-weight verbatim — but FONT_WEIGHT_MAP is a
# name table, so the numeric face answered '' and vanished from the emit.
# Run 6 measured the divergence: ios active, android/web inert, on the same
# declaration (ruled a cross-platform divergence to fix in this release, not
# to ledger). One mapper answers every call site, so Button, Label and
# IconLabel are pinned through the same table.
RSpec.describe 'fontWeight numeric face' do
  let(:config) { { 'use_tailwind' => true } }

  def emit(klass, attrs)
    klass.new({ 'id' => 't', 'text' => 'S' }.merge(attrs), config).convert_node(1)
  end

  it 'Button: the fixture face (JSON number 600) reaches the class list' do
    out = emit(RjuiTools::React::Converters::ButtonConverter,
               'type' => 'Button', 'fontWeight' => 600)
    expect(out).to include('font-[600]')
  end

  it 'Label and IconLabel take the same table' do
    label = emit(RjuiTools::React::Converters::LabelConverter,
                 'type' => 'Label', 'fontWeight' => 600)
    icon = emit(RjuiTools::React::Converters::IconLabelConverter,
                'type' => 'IconLabel', 'fontWeight' => 600)
    expect(label).to include('font-[600]')
    expect(icon).to include('font-[600]')
  end

  it 'the string spelling of a number lands on the same class' do
    out = emit(RjuiTools::React::Converters::ButtonConverter,
               'type' => 'Button', 'fontWeight' => '600')
    expect(out).to include('font-[600]')
  end

  it 'name weights keep their exact previous emit' do
    out = emit(RjuiTools::React::Converters::ButtonConverter,
               'type' => 'Button', 'fontWeight' => 'bold')
    expect(out).to include('font-bold')
    expect(out).not_to include('font-[')
  end

  it 'an unknown name still answers nothing rather than a dead class' do
    out = emit(RjuiTools::React::Converters::ButtonConverter,
               'type' => 'Button', 'fontWeight' => 'chunky')
    expect(out).not_to include('font-[')
    expect(out).not_to match(/\bfont-chunky\b/)
  end
end
