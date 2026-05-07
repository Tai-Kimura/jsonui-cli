# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/label_converter'
require 'react/converters/view_converter'

RSpec.describe 'BaseConverter FontSpec routing' do
  let(:config) { { 'use_tailwind' => true } }

  def make_label(json)
    RjuiTools::React::Converters::LabelConverter.new(json.merge('type' => 'Label'), config)
  end

  context 'when fontFamily is absent' do
    it 'emits the legacy Tailwind font-bold class for font: "bold"' do
      converter = make_label('text' => 'Hi', 'font' => 'bold')
      classes = converter.send(:build_class_name)
      expect(classes).to include('font-bold')
    end

    it 'emits the legacy Tailwind text-base class for fontSize: 16' do
      converter = make_label('text' => 'Hi', 'fontSize' => 16)
      classes = converter.send(:build_class_name)
      expect(classes).to include('text-base')
    end

    it 'does not emit a Configuration.Font.resolve spread on the inline style' do
      converter = make_label('text' => 'Hi', 'font' => 'bold', 'fontSize' => 16)
      converter.send(:build_class_name)
      style_attr = converter.send(:build_style_attr)
      expect(style_attr).not_to include('Configuration.Font.resolve(')
    end
  end

  context 'when fontFamily is present' do
    it 'emits Configuration.Font.resolve(...) as a JS spread inside the inline style' do
      converter = make_label(
        'text'       => 'Hello',
        'fontFamily' => 'Helvetica',
        'font'       => 'bold',
        'fontSize'   => 16
      )
      converter.send(:build_class_name)
      style_attr = converter.send(:build_style_attr)
      expect(style_attr).to include(
        "...Configuration.Font.resolve({ family: 'Helvetica', weight: 'bold', size: 16, italic: false })"
      )
      expect(style_attr).to start_with(' style={{ ')
      expect(style_attr).to end_with(' }}')
    end

    it 'drops Tailwind font-bold class so the resolved style is the single source of truth' do
      converter = make_label(
        'text'       => 'Hello',
        'fontFamily' => 'Helvetica',
        'font'       => 'bold'
      )
      classes = converter.send(:build_class_name)
      expect(classes).not_to include('font-bold')
    end

    it 'drops Tailwind text-base class so the resolved style is the single source of truth' do
      converter = make_label(
        'text'       => 'Hello',
        'fontFamily' => 'Helvetica',
        'fontSize'   => 16
      )
      classes = converter.send(:build_class_name)
      expect(classes).not_to include('text-base')
      expect(classes).not_to include('text-[16px]')
    end

    it 'still emits a fontWeight inline style for explicit fontWeight bindings' do
      converter = make_label(
        'text'       => 'Hello',
        'fontFamily' => 'Helvetica',
        'fontWeight' => '@{viewModel.weight}'
      )
      converter.send(:build_class_name)
      style_attr = converter.send(:build_style_attr)
      expect(style_attr).to include('fontWeight: data.weight')
    end

    it 'forwards explicit fontWeight (over polymorphic font) to FontSpec.weight when both are static' do
      converter = make_label(
        'text'       => 'Hello',
        'fontFamily' => 'Helvetica',
        'font'       => 'medium',
        'fontWeight' => 'bold'
      )
      converter.send(:build_class_name)
      style_attr = converter.send(:build_style_attr)
      expect(style_attr).to include("weight: 'bold'")
      expect(style_attr).not_to include("weight: 'medium'")
    end

    it 'omits the size field when fontSize is a binding (provider only sees static specs)' do
      converter = make_label(
        'text'       => 'Hello',
        'fontFamily' => 'Helvetica',
        'fontSize'   => '@{viewModel.size}'
      )
      converter.send(:build_class_name)
      style_attr = converter.send(:build_style_attr)
      expect(style_attr).not_to match(/size:/)
      # The binding still flows into the inline style as a regular fontSize entry.
      expect(style_attr).to include('fontSize: data.size')
    end
  end

  describe '#format_dynamic_style_pair' do
    it 'renders SPREAD-prefixed keys as a bare ...<value>' do
      converter = make_label('text' => 'Hi')
      result = converter.send(
        :format_dynamic_style_pair,
        '__SPREAD__font',
        '...Configuration.Font.resolve({ family: \'X\', italic: false })'
      )
      expect(result).to eq("...Configuration.Font.resolve({ family: 'X', italic: false })")
    end

    it 'renders ordinary keys as `key: value` (with -- prefixed keys quoted)' do
      converter = make_label('text' => 'Hi')
      expect(converter.send(:format_dynamic_style_pair, 'color', "'red'"))
        .to eq("color: 'red'")
      expect(converter.send(:format_dynamic_style_pair, '--accent', "'#FF0000'"))
        .to eq("'--accent': '#FF0000'")
    end
  end
end
