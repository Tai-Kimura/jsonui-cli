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

    # Regression: rjui-segment-items-string-resolution — items go through the
    # same string resolution as Label.text (convert_text_binding), matching sjui's
    # per-item get_text_with_string_manager.
    context 'items string resolution' do
      it 'resolves registered string keys via StringManager' do
        converter = create_converter({ 'class' => 'Segment', 'id' => 'modeSegment', 'items' => %w[mode_daily mode_time_slot] })
        allow(converter).to receive(:convert_string_key)
          .with('mode_daily')
          .and_return('{StringManager.currentLanguage.bookingInputModeDaily}')
        allow(converter).to receive(:convert_string_key)
          .with('mode_time_slot')
          .and_return('{StringManager.currentLanguage.bookingInputModeTimeSlot}')
        result = converter.convert
        expect(result).to include('>{StringManager.currentLanguage.bookingInputModeDaily}</button>')
        expect(result).to include('>{StringManager.currentLanguage.bookingInputModeTimeSlot}</button>')
        expect(result).not_to include('>mode_daily<')
      end

      it 'leaves unregistered literals as plain text' do
        converter = create_converter({ 'class' => 'Segment', 'items' => ['Tab 1', 'Tab 2'] })
        allow(converter).to receive(:convert_string_key).and_return(nil)
        result = converter.convert
        expect(result).to include('>Tab 1</button>')
        expect(result).to include('>Tab 2</button>')
      end

      it 'resolves binding items to data expressions' do
        converter = create_converter({ 'class' => 'Segment', 'items' => ['@{firstLabel}', '@{secondLabel}'] })
        result = converter.convert
        expect(result).to include('>{`${data.firstLabel ?? ""}`}</button>')
        expect(result).to include('>{`${data.secondLabel ?? ""}`}</button>')
      end
    end

    # Regression: rjui-segment-item-ids-selecttab — each button carries the
    # TabView `{id}_tab_{index}` naming contract so the web test driver's
    # selectTab action can target individual segments.
    context 'per-item ids for selectTab' do
      it 'emits {id}_tab_{index} ids on each button' do
        converter = create_converter({ 'class' => 'Segment', 'id' => 'sizeSegment', 'items' => %w[a b c] })
        result = converter.convert
        expect(result).to include('id="sizeSegment_tab_0"')
        expect(result).to include('id="sizeSegment_tab_1"')
        expect(result).to include('id="sizeSegment_tab_2"')
      end

      it 'omits per-item ids when the segment has no id' do
        converter = create_converter({ 'class' => 'Segment', 'items' => %w[a b] })
        result = converter.convert
        expect(result).not_to include('_tab_0"')
      end

      it 'omits per-item ids when the id is a binding' do
        converter = create_converter({ 'class' => 'Segment', 'id' => '@{segmentId}', 'items' => %w[a b] })
        result = converter.convert
        expect(result).not_to include('_tab_')
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

    # fontColor is the UNSELECTED label, selectedFontColor the selected one.
    # A brand-coloured tint used to leave the label at a hardcoded gray with no
    # way to declare otherwise (contract: semantics.segmentLabelColors).
    context 'label colours' do
      let(:base) { { 'class' => 'Segment', 'items' => %w[One Two], 'selectedIndex' => 0 } }

      it 'colours the unselected label from fontColor' do
        result = create_converter(base.merge('fontColor' => 'primary')).convert

        expect(result).to include('text-primary')
        expect(result).not_to include('text-gray-500')
      end

      it 'colours the selected label from selectedFontColor' do
        result = create_converter(base.merge('selectedFontColor' => 'on_primary')).convert

        expect(result).to include('text-on_primary')
      end

      it 'falls back to fontColor for the selected label' do
        result = create_converter(base.merge('fontColor' => 'primary')).convert
        buttons = result.lines.grep(/<button/)

        expect(buttons.size).to eq(2)
        expect(buttons).to all(include('text-primary'))
      end

      it 'keeps the hardcoded defaults when neither is declared' do
        result = create_converter(base).convert

        expect(result).to include('text-gray-500')
        expect(result).to include('text-gray-900')
      end

      it 'paints the selected background from tintColor' do
        result = create_converter(base.merge('tintColor' => 'primary')).convert

        expect(result).to include('bg-primary')
      end
    end
  end
end
