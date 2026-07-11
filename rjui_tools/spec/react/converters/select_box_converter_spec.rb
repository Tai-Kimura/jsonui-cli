# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/select_box_converter'

RSpec.describe RjuiTools::React::Converters::SelectBoxConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'basic select with string items' do
      it 'generates select with options' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['Option 1', 'Option 2', 'Option 3'] })
        result = converter.convert
        expect(result).to include('<select')
        expect(result).to include('<option value="Option 1">Option 1</option>')
        expect(result).to include('<option value="Option 2">Option 2</option>')
        expect(result).to include('<option value="Option 3">Option 3</option>')
      end
    end

    context 'with hash items' do
      it 'generates options with value and text' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => [{ 'value' => '1', 'text' => 'First' }, { 'value' => '2', 'text' => 'Second' }] })
        result = converter.convert
        expect(result).to include('<option value="1">First</option>')
        expect(result).to include('<option value="2">Second</option>')
      end
    end

    context 'with items binding' do
      it 'generates dynamic options mapping' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => '@{options}' })
        result = converter.convert
        expect(result).to include('{data.options?.map((item) =>')
        expect(result).to include('{item.text || item.label}')
      end

      # Regression: rjui-selectbox-dynamic-items-assumes-object-shape —
      # canonical items are a plain string array ([String], matching
      # SwiftJsonUI SelectBoxView), so the option row must branch on the
      # element shape instead of assuming {value, text} objects.
      it 'supports canonical string-array items via a typeof branch' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => '@{sortOptions}' })
        result = converter.convert
        expect(result).to include("typeof item === 'object' && item !== null")
        expect(result).to include('<option key={String(item)} value={String(item)}>{String(item)}</option>')
        expect(result).to include('<option key={item.value || item.id} value={item.value || item.id}>{item.text || item.label}</option>')
      end
    end

    context 'with placeholder/hint/prompt' do
      it 'adds a selectable placeholder option (no disabled/hidden so picking clears value)' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A', 'B'], 'placeholder' => 'Select one...' })
        result = converter.convert
        expect(result).to include('<option value="">Select one...</option>')
        expect(result).not_to include('disabled hidden')
      end

      # Spec canonical `prompt` is the primary key, with hint/placeholder as
      # aliases. Match the iOS / Android SelectBox surfaces.
      it 'accepts prompt as the canonical primary key' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A', 'B'], 'prompt' => 'Pick a thing' })
        result = converter.convert
        expect(result).to include('<option value="">Pick a thing</option>')
      end

      it 'prefers prompt over hint and placeholder when multiple are present' do
        converter = create_converter(
          'class' => 'SelectBox',
          'items' => ['A', 'B'],
          'prompt' => 'from prompt',
          'hint' => 'from hint',
          'placeholder' => 'from placeholder'
        )
        result = converter.convert
        expect(result).to include('<option value="">from prompt</option>')
        expect(result).not_to include('from hint')
        expect(result).not_to include('from placeholder')
      end
    end

    context 'with selectedValue binding' do
      it 'generates value binding' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A', 'B'], 'selectedValue' => '@{selected}' })
        result = converter.convert
        expect(result).to include('value={data.selected}')
      end
    end

    context 'with static default value' do
      it 'generates defaultValue' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A', 'B'], 'value' => 'B' })
        result = converter.convert
        expect(result).to include('defaultValue="B"')
      end
    end

    context 'with onChange handler' do
      it 'generates onChange with optional chaining' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A', 'B'], 'onChange' => '@{handleChange}' })
        result = converter.convert
        expect(result).to include('onChange={(e) => data.handleChange?.(e.target.value)}')
      end
    end

    context 'with borderColor' do
      it 'applies border color' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A'], 'borderColor' => '#CCCCCC' })
        result = converter.convert
        expect(result).to include('border-[#CCCCCC]')
      end
    end

    context 'with fontColor' do
      it 'applies font color' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A'], 'fontColor' => '#333333' })
        result = converter.convert
        expect(result).to include('text-[#333333]')
      end
    end

    context 'with enabled=false' do
      it 'adds disabled state' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A'], 'enabled' => false })
        result = converter.convert
        expect(result).to include('disabled')
        expect(result).to include('opacity-50')
        expect(result).to include('cursor-not-allowed')
      end
    end

    context 'with enabled binding (regression: rjui-button-enabled-binding-compares-bool-to-string)' do
      it 'negates the boolean binding instead of comparing to "true"' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A'], 'enabled' => '@{isEditable}' })
        result = converter.convert
        expect(result).to include('disabled={!data.isEditable}')
        expect(result).not_to include('!== "true"')
      end
    end

    context 'with testId' do
      it 'generates data-testid attribute' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A'], 'testId' => 'country-select' })
        result = converter.convert
        expect(result).to include('data-testid="country-select"')
      end
    end

    context 'with visibility binding' do
      it 'wraps with conditional rendering' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A'], 'visibility' => '@{showSelect}' })
        result = converter.convert
        expect(result).to include('{data.showSelect !== "gone" &&')
      end
    end
  end
end
