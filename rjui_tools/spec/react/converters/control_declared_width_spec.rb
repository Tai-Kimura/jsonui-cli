# frozen_string_literal: true

require 'spec_helper'
require 'react/converters/slider_converter'
require 'react/converters/progress_converter'
require 'react/converters/segment_converter'

# Slider / Progress / Segment draw at their declared width. Each converter
# used to add `w-full` after the declared width class, and the stylesheet
# order made it win: a width-200 control drew at the root's full width on web
# (frame-parity inventory 2026-10-05, 35 rows; ticket
# rjui-slider-progress-segment-ignore-the-declared-width-and-fill-the-row).
# common.width is `number | matchParent | wrapContent` and required.
RSpec.describe 'a control draws at its declared width' do
  let(:config) { { 'use_tailwind' => true } }

  {
    'Slider' => RjuiTools::React::Converters::SliderConverter,
    'Progress' => RjuiTools::React::Converters::ProgressConverter,
    'Segment' => RjuiTools::React::Converters::SegmentConverter
  }.each do |type, klass|
    def classes_of(out)
      out.scan(/className="([^"]*)"/).flatten.flat_map(&:split)
    end

    it "#{type} with a declared width carries that width and no w-full" do
      node = { 'type' => type, 'id' => 't', 'width' => 200, 'height' => 'wrapContent' }
      node['items'] = %w[a b] if type == 'Segment'
      classes = classes_of(klass.new(node, config).convert_node(2))
      expect(classes).not_to include('w-full')
      expect(classes.grep(/\Aw-\[/)).not_to be_empty
    end

    it "#{type} with no width declared still fills (the fallback)" do
      node = { 'type' => type, 'id' => 't', 'height' => 'wrapContent' }
      node['items'] = %w[a b] if type == 'Segment'
      expect(classes_of(klass.new(node, config).convert_node(2))).to include('w-full')
    end

    it "#{type} with a declared width still type-checks", :typescript_compile do
      node = { 'type' => type, 'id' => 't', 'width' => 200, 'height' => 'wrapContent' }
      node['items'] = %w[a b] if type == 'Segment'
      ambient = <<~TS
        declare const JsonUISeeded: <T>(props: { seed: T; children: (value: T, set: (value: T) => void) => JSX.Element }) => JSX.Element;
      TS
      expect(TypeScriptCompiler.component(klass.new(node, config).convert_node(2)))
        .to compile_as_typescript.with_ambient(ambient)
    end
  end
end
