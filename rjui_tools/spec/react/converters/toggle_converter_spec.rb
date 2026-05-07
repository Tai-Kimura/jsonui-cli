# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/toggle_converter'

RSpec.describe RjuiTools::React::Converters::ToggleConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'basic checkbox' do
      it 'generates checkbox input' do
        converter = create_converter({ 'class' => 'CheckBox' })
        result = converter.convert
        expect(result).to include('<input')
        expect(result).to include('type="checkbox"')
      end
    end

    context 'with label text' do
      it 'generates label with checkbox and text' do
        converter = create_converter({ 'class' => 'CheckBox', 'text' => 'Accept terms' })
        result = converter.convert
        expect(result).to include('<label')
        expect(result).to include('Accept terms')
        expect(result).to include('flex items-center gap-2')
      end
    end

    context 'with isOn binding' do
      it 'generates checked binding' do
        converter = create_converter({ 'class' => 'CheckBox', 'isOn' => '@{isChecked}' })
        result = converter.convert
        expect(result).to include('checked={data.isChecked}')
      end
    end

    context 'with static checked value' do
      it 'generates defaultChecked' do
        converter = create_converter({ 'class' => 'CheckBox', 'checked' => true })
        result = converter.convert
        expect(result).to include('defaultChecked')
      end
    end

    context 'with onValueChange handler' do
      it 'generates onChange with optional chaining and checked value' do
        converter = create_converter({ 'class' => 'CheckBox', 'onValueChange' => '@{handleChange}' })
        result = converter.convert
        expect(result).to include('onChange={(e) => data.handleChange?.(e.target.checked)}')
      end
    end

    context 'with isOn binding but no onValueChange (auto-generated)' do
      it 'auto-generates onChange handler from isOn binding' do
        converter = create_converter({ 'class' => 'CheckBox', 'isOn' => '@{isEnabled}' })
        result = converter.convert
        expect(result).to include('checked={data.isEnabled}')
        expect(result).to include('onChange={(e) => data.onIsEnabledChange?.(e.target.checked)}')
      end
    end

    context 'with enabled=false' do
      it 'adds disabled attribute and styling' do
        converter = create_converter({ 'class' => 'CheckBox', 'enabled' => false })
        result = converter.convert
        expect(result).to include('disabled')
        expect(result).to include('opacity-50')
        expect(result).to include('cursor-not-allowed')
      end
    end

    context 'with enabled binding' do
      it 'generates dynamic disabled attribute' do
        converter = create_converter({ 'class' => 'CheckBox', 'enabled' => '@{isEnabled}' })
        result = converter.convert
        expect(result).to include('disabled={!data.isEnabled}')
      end
    end

    context 'with tintColor' do
      it 'adds accent color style' do
        converter = create_converter({ 'class' => 'CheckBox', 'tintColor' => '#FF5500' })
        result = converter.convert
        expect(result).to include("accentColor: '#FF5500'")
      end
    end

    context 'with testId' do
      it 'generates data-testid attribute' do
        converter = create_converter({ 'class' => 'CheckBox', 'testId' => 'terms-checkbox' })
        result = converter.convert
        expect(result).to include('data-testid="terms-checkbox"')
      end
    end

    context 'with tag' do
      it 'generates data-tag attribute' do
        converter = create_converter({ 'class' => 'CheckBox', 'tag' => 'checkbox-1' })
        result = converter.convert
        expect(result).to include('data-tag="checkbox-1"')
      end
    end

    context 'with visibility binding' do
      it 'wraps with conditional rendering' do
        converter = create_converter({ 'class' => 'CheckBox', 'visibility' => '@{showCheckbox}' })
        result = converter.convert
        expect(result).to include('{data.showCheckbox !== "gone" &&')
      end
    end
  end
end
