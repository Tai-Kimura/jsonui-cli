#!/usr/bin/env ruby

require_relative '../../spec_helper'
require_relative '../../../lib/react/converters/base_converter'
require_relative '../../../lib/react/converters/button_converter'
require_relative '../../../lib/react/converters/slider_converter'
require_relative '../../../lib/react/converters/tab_view_converter'
require_relative '../../../lib/react/converters/view_converter'

# Stage A (renderer SSoT): converters take the canonical-only attribute
# lookup path when the layout carried the `$jui` L1 marker
# (config['_layout_normalized'] set by ReactGenerator#generate), and keep
# the legacy alias-fallback path for raw (L0) layouts.
RSpec.describe 'L1-normalized layout consumption' do
  let(:l0_config) { {} }
  let(:l1_config) { { '_layout_normalized' => true } }

  describe RjuiTools::React::Converters::BaseConverter do
    def classes_for(json, config)
      RjuiTools::React::Converters::ViewConverter.new(json, config).convert
    end

    it 'reads the alpha alias on L0 layouts' do
      jsx = classes_for({ 'type' => 'View', 'alpha' => 0.5 }, l0_config)
      expect(jsx).to include('opacity-50')
    end

    it 'prefers canonical opacity over the alias' do
      jsx = classes_for({ 'type' => 'View', 'opacity' => 0.3, 'alpha' => 0.5 }, l0_config)
      expect(jsx).to include('opacity-30')
      expect(jsx).not_to include('opacity-50')
    end

    it 'ignores the alias on L1 layouts (canonical-only path)' do
      jsx = classes_for({ 'type' => 'View', 'alpha' => 0.5 }, l1_config)
      expect(jsx).not_to include('opacity-50')
    end

    it 'reads canonical opacity on L1 layouts' do
      jsx = classes_for({ 'type' => 'View', 'opacity' => 0.5 }, l1_config)
      expect(jsx).to include('opacity-50')
    end
  end

  describe RjuiTools::React::Converters::ButtonConverter do
    it 'maps the highlightBackground alias to hover/active classes on L0' do
      jsx = described_class.new(
        { 'type' => 'Button', 'text' => 'Tap', 'highlightBackground' => '#FF0000' }, l0_config
      ).convert
      expect(jsx).to include('hover:bg-[#FF0000]')
      expect(jsx).to include('active:bg-[#FF0000]')
    end

    it 'ignores the highlightBackground alias on L1 (canonical tapBackground only)' do
      jsx = described_class.new(
        { 'type' => 'Button', 'text' => 'Tap', 'highlightBackground' => '#FF0000' }, l1_config
      ).convert
      expect(jsx).not_to include('hover:bg-[#FF0000]')
      expect(jsx).to include('hover:opacity-80')
    end

    it 'maps the hilightColor alias on L0 and ignores it on L1' do
      l0 = described_class.new(
        { 'type' => 'Button', 'text' => 'Tap', 'hilightColor' => '#00FF00' }, l0_config
      ).convert
      l1 = described_class.new(
        { 'type' => 'Button', 'text' => 'Tap', 'hilightColor' => '#00FF00' }, l1_config
      ).convert
      expect(l0).to include('hover:text-[#00FF00]')
      expect(l1).not_to include('hover:text-[#00FF00]')
    end
  end

  describe RjuiTools::React::Converters::SliderConverter do
    it 'reads canonical minimum/maximum' do
      jsx = described_class.new(
        { 'type' => 'Slider', 'minimum' => 5, 'maximum' => 50 }, l0_config
      ).convert
      expect(jsx).to include('min={5} max={50}')
    end

    it 'falls back to minimumValue/maximumValue aliases on L0' do
      jsx = described_class.new(
        { 'type' => 'Slider', 'minimumValue' => 5, 'maximumValue' => 50 }, l0_config
      ).convert
      expect(jsx).to include('min={5} max={50}')
    end

    it 'falls back to minValue/maxValue aliases on L0' do
      jsx = described_class.new(
        { 'type' => 'Slider', 'minValue' => 5, 'maxValue' => 50 }, l0_config
      ).convert
      expect(jsx).to include('min={5} max={50}')
    end

    it 'ignores alias spellings on L1' do
      jsx = described_class.new(
        { 'type' => 'Slider', 'minimumValue' => 5, 'maximumValue' => 50 }, l1_config
      ).convert
      expect(jsx).to include('min={0} max={100}')
    end

    it 'accepts the onValueChanged alias on L0 only' do
      json = { 'type' => 'Slider', 'onValueChanged' => '@{onSlide}' }
      l0 = described_class.new(json, l0_config).convert
      l1 = described_class.new(json, l1_config).convert
      expect(l0).to include('data.onSlide?.(Number(e.target.value))')
      expect(l1).not_to include('data.onSlide')
    end
  end

  describe RjuiTools::React::Converters::TabViewConverter do
    let(:json) do
      {
        'type' => 'TabView',
        'tabs' => [{ 'title' => 'One' }, { 'title' => 'Two' }],
        'selectedTabIndex' => '@{tabIndex}',
        'onPageChanged' => '@{onTab}'
      }
    end

    it 'resolves selectedTabIndex / onPageChanged aliases on L0' do
      jsx = described_class.new(json, l0_config).convert
      expect(jsx).to include('data.tabIndex')
      expect(jsx).to include('data.onTab')
    end

    it 'ignores alias spellings on L1' do
      jsx = described_class.new(json, l1_config).convert
      expect(jsx).not_to include('data.tabIndex')
      expect(jsx).not_to include('data.onTab')
    end

    it 'resolves canonical selectedIndex / onValueChange on both paths' do
      canonical = json.merge(
        'selectedIndex' => '@{tabIndex}', 'onValueChange' => '@{onTab}'
      )
      [l0_config, l1_config].each do |config|
        jsx = described_class.new(canonical, config).convert
        expect(jsx).to include('data.tabIndex')
        expect(jsx).to include('data.onTab')
      end
    end
  end
end
