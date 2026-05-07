# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/switch_converter'

RSpec.describe RjuiTools::React::Converters::SwitchConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'basic switch' do
      it 'generates iOS-style toggle switch' do
        converter = create_converter({ 'class' => 'Switch' })
        result = converter.convert
        expect(result).to include('w-[51px]')
        expect(result).to include('h-[31px]')
        expect(result).to include('peer-checked:translate-x-[20px]')
      end
    end

    context 'with label text' do
      it 'generates label with switch and text' do
        converter = create_converter({ 'class' => 'Switch', 'text' => 'Enable notifications' })
        result = converter.convert
        expect(result).to include('<label')
        expect(result).to include('Enable notifications')
        expect(result).to include('flex items-center gap-3')
      end
    end

    context 'with isOn binding' do
      it 'generates checked binding' do
        converter = create_converter({ 'class' => 'Switch', 'isOn' => '@{isEnabled}' })
        result = converter.convert
        expect(result).to include('checked={data.isEnabled}')
      end
    end

    context 'with static value true' do
      it 'generates defaultChecked' do
        converter = create_converter({ 'class' => 'Switch', 'value' => true })
        result = converter.convert
        expect(result).to include('defaultChecked')
      end
    end

    context 'with onValueChange handler' do
      it 'generates onChange with optional chaining and checked value' do
        converter = create_converter({ 'class' => 'Switch', 'onValueChange' => '@{toggleSwitch}' })
        result = converter.convert
        expect(result).to include('onChange={(e) => data.toggleSwitch?.(e.target.checked)}')
      end
    end

    context 'with isOn binding but no onValueChange (auto-generated)' do
      it 'auto-generates onChange handler from isOn binding' do
        converter = create_converter({ 'class' => 'Switch', 'isOn' => '@{switchEnabled}' })
        result = converter.convert
        expect(result).to include('checked={data.switchEnabled}')
        expect(result).to include('onChange={(e) => data.onSwitchEnabledChange?.(e.target.checked)}')
      end
    end

    context 'with custom tintColor' do
      it 'uses custom on color' do
        converter = create_converter({ 'class' => 'Switch', 'tintColor' => '#007AFF' })
        result = converter.convert
        expect(result).to include('peer-checked:bg-[#007AFF]')
      end
    end

    context 'with thumbTintColor' do
      it 'uses custom thumb color' do
        converter = create_converter({ 'class' => 'Switch', 'thumbTintColor' => '#EEEEEE' })
        result = converter.convert
        expect(result).to include('bg-[#EEEEEE]')
      end
    end

    context 'with offTintColor' do
      it 'uses custom off color' do
        converter = create_converter({ 'class' => 'Switch', 'offTintColor' => '#CCCCCC' })
        result = converter.convert
        expect(result).to include('bg-[#CCCCCC]')
      end
    end

    context 'with enabled=false' do
      it 'adds disabled attribute and styling' do
        converter = create_converter({ 'class' => 'Switch', 'enabled' => false })
        result = converter.convert
        expect(result).to include('disabled')
        expect(result).to include('opacity-50')
        expect(result).to include('cursor-not-allowed')
      end
    end

    context 'with enabled binding' do
      it 'generates dynamic disabled attribute' do
        converter = create_converter({ 'class' => 'Switch', 'enabled' => '@{canToggle}' })
        result = converter.convert
        expect(result).to include('disabled={!data.canToggle}')
      end
    end

    context 'with testId' do
      it 'generates data-testid attribute' do
        converter = create_converter({ 'class' => 'Switch', 'testId' => 'notification-switch' })
        result = converter.convert
        expect(result).to include('data-testid="notification-switch"')
      end
    end

    context 'with tag' do
      it 'generates data-tag attribute' do
        converter = create_converter({ 'class' => 'Switch', 'tag' => 'switch-1' })
        result = converter.convert
        expect(result).to include('data-tag="switch-1"')
      end
    end

    context 'with visibility binding' do
      it 'wraps with conditional rendering' do
        converter = create_converter({ 'class' => 'Switch', 'visibility' => '@{showSwitch}' })
        result = converter.convert
        expect(result).to include('{data.showSwitch !== "gone" &&')
      end
    end
  end
end
