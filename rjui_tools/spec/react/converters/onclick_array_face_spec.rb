# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/view_converter'
require 'react/converters/image_converter'
require 'react/viewmodel_generator'
require 'react/data_model_generator'

# The SSoT declares common.onclick `string|array`, and the array face used to
# break every reader differently: the JSX emit interpolated Ruby's Array
# inspect (`onClick={data.["a", "b"]}` — TS1003), ImageConverter died with
# NoMethodError (`end_with?` on Array — the same crash kjui carried), and both
# action extractors guarded on `is_a?(String)`, so the handlers the JSX called
# had no generated stub. ios's codegen emitted both selectors all along and is
# the semantics these pins hold: every declared selector is called, in
# declared order.
RSpec.describe 'onclick array face' do
  let(:config) { { 'use_tailwind' => true } }

  def view(attrs)
    RjuiTools::React::Converters::ViewConverter.new(
      { 'type' => 'View', 'id' => 't' }.merge(attrs), config
    ).convert_node(1)
  end

  describe 'JSX emit' do
    it 'calls every selector in declared order' do
      out = view('onclick' => %w[confPush confPop])
      expect(out).to include('onClick={() => { data.confPush?.(); data.confPop?.(); }}')
    end

    it 'leaves the single-string face exactly as it was' do
      expect(view('onclick' => 'confPush')).to include('onClick={data.confPush}')
    end

    it 'still rejects a binding spelling, even inside the array' do
      out = view('onclick' => ['confPush', '@{bad}'])
      expect(out).to include('ERROR: onclick requires selector format')
      expect(out).not_to include('data.confPush')
    end

    it 'emits nothing for an empty array rather than an empty arrow' do
      expect(view('onclick' => [])).not_to include('onClick')
    end

    it 'survives ImageConverter, which used to NoMethodError on the array' do
      out = RjuiTools::React::Converters::ImageConverter.new(
        { 'type' => 'Image', 'src' => 'a.png', 'onclick' => %w[confPush confPop] }, config
      ).convert_node(1)
      expect(out).to include('onClick={() => { data.confPush?.(); data.confPop?.(); }}')
    end
  end

  describe 'action extraction (the stubs the JSX calls)' do
    layout = {
      'type' => 'View',
      'child' => [
        { 'type' => 'View', 'onclick' => %w[confPush confPop] },
        { 'type' => 'View', 'onclick' => 'single' }
      ]
    }

    it 'collects every array element in the ViewModel generator' do
      gen = RjuiTools::React::ViewModelGenerator.allocate
      actions = gen.send(:extract_onclick_actions, layout)
      expect(actions).to include('confPush', 'confPop', 'single')
    end

    it 'collects every array element in the DataModel generator' do
      gen = RjuiTools::React::DataModelGenerator.allocate
      actions = gen.send(:extract_onclick_actions, layout)
      expect(actions).to include('confPush', 'confPop', 'single')
    end
  end
end
