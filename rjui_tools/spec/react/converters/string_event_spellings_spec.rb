# frozen_string_literal: true

require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require 'react/converters/segment_converter'
require 'react/converters/text_field_converter'
require 'react/converters/text_view_converter'

# Event attributes the SSoT declares "string" take the handler as '@{name}'
# or as the bare name; both name the data's closure. Two of them wrote one
# spelling as TypeScript that does not compile (measured 2026-10-03 with the
# event x declared-form conformance probes):
#   - Segment `valueChange: "@{h}"` → `data.@{h}?.(0)`
#     (rjui-segment-valuechange-binding-writes-the-braces);
#   - TextField / TextView `onTextChange: "h"` → `h?.(e.target.value)`, a
#     name nothing declares (bare-event-handler-is-dropped-without-a-warning).
RSpec.describe 'rjui: both spellings of a string-declared event handler' do
  def data_decl
    <<~TS
      declare const data: { onPick?: (value: number) => void; onType?: (value: string) => void };
      // React's own element types give `e` its type; the support ambient
      // declares every intrinsic element as `any`, so these two are spelled out.
      declare namespace JSX {
        interface IntrinsicElements {
          input: { onChange?: (e: { target: { value: string } }) => void };
          textarea: { onChange?: (e: { target: { value: string } }) => void };
        }
      }
      declare const JsonUISeeded: <T>(props: { seed: T; children: (value: T, set: (value: T) => void) => JSX.Element }) => JSX.Element;
    TS
  end

  def segment(value)
    RjuiTools::React::Converters::SegmentConverter.new(
      { 'type' => 'Segment', 'id' => 'seg', 'items' => %w[A B], 'valueChange' => value }, { 'use_tailwind' => true }
    ).convert
  end

  def on_change(klass, value)
    klass.new({ 'type' => 'TextField', 'id' => 'field', 'onTextChange' => value }, { 'use_tailwind' => true })
         .send(:build_on_change)
  end

  it 'Segment valueChange: the binding and the bare name call the same closure' do
    expect(segment('@{onPick}')).to include('data.onPick?.(0)')
    expect(segment('onPick')).to include('data.onPick?.(0)')
    expect(segment('@{onPick}')).not_to include('@{')
  end

  it 'Segment valueChange: both spellings type-check', :aggregate_failures do
    %w[@{onPick} onPick].each do |value|
      expect(TypeScriptCompiler.component(segment(value))).to compile_as_typescript.with_ambient(data_decl)
    end
  end

  {
    RjuiTools::React::Converters::TextFieldConverter => 'input',
    RjuiTools::React::Converters::TextViewConverter => 'textarea'
  }.each do |klass, tag|
    it "#{klass.name.split('::').last} onTextChange: the bare name calls the data's closure, and both type-check",
       :aggregate_failures do
      expect(on_change(klass, 'onType')).to eq(' onChange={(e) => data.onType?.(e.target.value)}')
      %w[@{onType} onType].each do |value|
        expect(TypeScriptCompiler.component("<#{tag}#{on_change(klass, value)} />")).to compile_as_typescript.with_ambient(data_decl)
      end
    end
  end

  it 'control: an onTextChange that is not a name is still written as given' do
    expect(on_change(RjuiTools::React::Converters::TextFieldConverter, 'props.onType'))
      .to eq(' onChange={(e) => props.onType?.(e.target.value)}')
  end
end
