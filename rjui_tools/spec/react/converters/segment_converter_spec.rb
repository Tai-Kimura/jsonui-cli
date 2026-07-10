# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/segment_converter'

RSpec.describe RjuiTools::React::Converters::SegmentConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'basic segment control' do
      it 'generates segmented control buttons' do
        converter = create_converter({ 'class' => 'Segment', 'items' => ['Tab 1', 'Tab 2', 'Tab 3'] })
        result = converter.convert
        expect(result).to include('<div')
        expect(result).to include('Tab 1')
        expect(result).to include('Tab 2')
        expect(result).to include('Tab 3')
        expect(result).to include('flex')
      end
    end

    context 'with selectedIndex binding' do
      it 'uses binding for selection state' do
        converter = create_converter({ 'class' => 'Segment', 'items' => ['A', 'B'], 'selectedIndex' => '@{activeTab}' })
        result = converter.convert
        expect(result).to include('activeTab === 0')
        expect(result).to include('activeTab === 1')
      end
    end

    context 'with onValueChange handler' do
      it 'uses handler for onClick' do
        converter = create_converter({ 'class' => 'Segment', 'items' => ['A', 'B'], 'onValueChange' => '@{handleTabChange}' })
        result = converter.convert
        expect(result).to include('onClick={() => data.handleTabChange?.(0)}')
        expect(result).to include('onClick={() => data.handleTabChange?.(1)}')
      end
    end

    context 'with custom fontSize' do
      it 'applies font size to buttons' do
        converter = create_converter({ 'class' => 'Segment', 'items' => ['A'], 'fontSize' => 16 })
        result = converter.convert
        expect(result).to include('text-base')
      end
    end

    context 'with backgroundColor' do
      it 'applies background color' do
        converter = create_converter({ 'class' => 'Segment', 'items' => ['A'], 'backgroundColor' => '#EEEEEE' })
        result = converter.convert
        expect(result).to include('bg-[#EEEEEE]')
      end
    end

    context 'with enabled=false' do
      it 'adds disabled state' do
        converter = create_converter({ 'class' => 'Segment', 'items' => ['A', 'B'], 'enabled' => false })
        result = converter.convert
        expect(result).to include('opacity-50')
        expect(result).to include('disabled')
      end
    end

    context 'with testId' do
      it 'generates data-testid attribute' do
        converter = create_converter({ 'class' => 'Segment', 'items' => ['A'], 'testId' => 'tab-control' })
        result = converter.convert
        expect(result).to include('data-testid="tab-control"')
      end
    end

    context 'with visibility binding' do
      it 'wraps with conditional rendering' do
        converter = create_converter({ 'class' => 'Segment', 'items' => ['A'], 'visibility' => '@{showTabs}' })
        result = converter.convert
        expect(result).to include('{data.showTabs !== "gone" &&')
      end
    end
  end
end
