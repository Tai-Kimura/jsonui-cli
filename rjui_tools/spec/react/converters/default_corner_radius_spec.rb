# frozen_string_literal: true

require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require 'react/react_generator'
require 'react/converters/select_box_converter'
require 'react/converters/text_field_converter'
require 'react/converters/text_view_converter'

# A control the layout writes no cornerRadius on (the requester's ruling 2026-11-15, ticket
# jui-button-default-corner-radius-differs): a SelectBox is 8px (rounded-lg; it was rounded-md,
# 6px), as on iOS and Android; a TextField and a TextView are square. rjui.config's
# defaults.textField.cornerRadius / defaults.textView.cornerRadius are gone: written, they draw
# no corner.
RSpec.describe 'rjui: the corner a control draws with no cornerRadius' do
  let(:config) { { 'use_tailwind' => true } }
  let(:with_defaults) do
    config.merge('defaults' => { 'textField' => { 'cornerRadius' => 12 }, 'textView' => { 'cornerRadius' => 12 } })
  end

  def corner_of(out)
    out.scan(/rounded[\w\-\[\]\.]*|borderRadius[^,}]*/).uniq
  end

  it 'emits TypeScript a compiler reads' do
    %w[SelectBox TextField TextView].each do |type|
      klass = RjuiTools::React::Converters.const_get("#{type}Converter")
      out = klass.new({ 'type' => type, 'id' => 'c', 'items' => %w[a b], 'hint' => 'x' }, with_defaults.dup).convert
      expect(TypeScriptCompiler.component(out)).to compile_as_typescript
    end
  end

  it 'draws a SelectBox at 8px' do
    out = RjuiTools::React::Converters::SelectBoxConverter.new({ 'type' => 'SelectBox', 'id' => 's', 'items' => %w[a b] }, config.dup).convert
    expect(out).to include('rounded-lg')
    expect(out).not_to include('rounded-md')
  end

  it 'draws a TextField square' do
    out = RjuiTools::React::Converters::TextFieldConverter.new({ 'type' => 'TextField', 'id' => 't', 'hint' => 'x' }, config.dup).convert
    expect(corner_of(out)).to eq([])
  end

  it 'draws a TextView square' do
    out = RjuiTools::React::Converters::TextViewConverter.new({ 'type' => 'TextView', 'id' => 't', 'hint' => 'x' }, config.dup).convert
    expect(corner_of(out)).to eq([])
  end

  it 'draws no corner from defaults.textField.cornerRadius' do
    out = RjuiTools::React::Converters::TextFieldConverter.new({ 'type' => 'TextField', 'id' => 't', 'hint' => 'x' }, with_defaults.dup).convert
    expect(corner_of(out)).to eq([])
  end

  # The other defaults still apply; any of them failed the build until 2.5.44.
  it "applies defaults.textField's and defaults.textView's fontColor, the layout's own winning" do
    cfg = config.merge('defaults' => { 'textField' => { 'fontColor' => '#123456' }, 'textView' => { 'fontColor' => '#123456' } })
    field = RjuiTools::React::Converters::TextFieldConverter.new({ 'type' => 'TextField', 'id' => 't', 'hint' => 'x' }, cfg.dup).convert
    view = RjuiTools::React::Converters::TextViewConverter.new({ 'type' => 'TextView', 'id' => 't', 'hint' => 'x' }, cfg.dup).convert
    own = RjuiTools::React::Converters::TextFieldConverter.new({ 'type' => 'TextField', 'id' => 't', 'hint' => 'x', 'fontColor' => '#654321' }, cfg.dup).convert
    expect(field).to include('123456')
    expect(view).to include('123456')
    expect(own).to include('654321')
    expect(own).not_to include('123456')
  end

  it 'draws no corner from defaults.textView.cornerRadius' do
    out = RjuiTools::React::Converters::TextViewConverter.new({ 'type' => 'TextView', 'id' => 't', 'hint' => 'x' }, with_defaults.dup).convert
    expect(corner_of(out)).to eq([])
  end
end
