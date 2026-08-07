# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/radio_converter'

RSpec.describe RjuiTools::React::Converters::RadioConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'basic radio group' do
      it 'generates radio group' do
        converter = create_converter({ 'class' => 'Radio', 'items' => ['Option 1', 'Option 2', 'Option 3'] })
        result = converter.convert
        expect(result).to include('type="radio"')
        expect(result).to include('Option 1')
        expect(result).to include('Option 2')
        expect(result).to include('Option 3')
        expect(result).to include('flex flex-col gap-2')
      end
    end

    context 'single radio button' do
      it 'generates single radio' do
        converter = create_converter({ 'class' => 'Radio', 'text' => 'Select me' })
        result = converter.convert
        expect(result).to include('<label')
        expect(result).to include('type="radio"')
        expect(result).to include('Select me')
      end
    end

    context 'with custom group name' do
      it 'uses custom group name' do
        converter = create_converter({ 'class' => 'Radio', 'items' => ['A', 'B'], 'group' => 'myGroup' })
        result = converter.convert
        expect(result).to include('name="myGroup"')
      end
    end

    context 'with selectedValue binding' do
      it 'uses binding for selection state' do
        converter = create_converter({ 'class' => 'Radio', 'items' => ['A', 'B'], 'selectedValue' => '@{selectedOption}' })
        result = converter.convert
        expect(result).to include('checked={data.selectedOption === "A"}')
        expect(result).to include('checked={data.selectedOption === "B"}')
      end
    end

    context 'with onValueChange handler' do
      it 'uses handler for onChange' do
        converter = create_converter({ 'class' => 'Radio', 'items' => ['A', 'B'], 'onValueChange' => '@{handleSelect}' })
        result = converter.convert
        expect(result).to include('onChange={() => data.handleSelect?.("A")}')
        expect(result).to include('onChange={() => data.handleSelect?.("B")}')
      end
    end

    context 'with label text for group' do
      it 'includes label text' do
        converter = create_converter({ 'class' => 'Radio', 'items' => ['A', 'B'], 'text' => 'Choose one:' })
        result = converter.convert
        expect(result).to include('Choose one:')
        expect(result).to include('font-medium')
      end
    end

    context 'with tintColor' do
      it 'adds accent color style' do
        converter = create_converter({ 'class' => 'Radio', 'items' => ['A'], 'tintColor' => '#FF5500' })
        result = converter.convert
        expect(result).to include("accentColor: '#FF5500'")
      end

      it 'resolves a palette token instead of emitting it as a colour' do
        converter = create_converter({ 'class' => 'Radio', 'items' => ['A'], 'tintColor' => 'primary' })
        result = converter.convert
        expect(result).to include("accentColor: ColorManager.resolveColor('primary')")
        expect(result).not_to include("accentColor: 'primary'")
      end

      it 'resolves the token on the single-radio path too' do
        converter = create_converter({ 'class' => 'Radio', 'id' => 'solo', 'tintColor' => 'primary' })
        result = converter.convert
        expect(result).to include("accentColor: ColorManager.resolveColor('primary')")
      end
    end

    context 'with enabled=false' do
      it 'adds disabled state' do
        converter = create_converter({ 'class' => 'Radio', 'items' => ['A', 'B'], 'enabled' => false })
        result = converter.convert
        expect(result).to include('disabled')
        expect(result).to include('opacity-50')
        expect(result).to include('cursor-not-allowed')
      end
    end

    context 'with testId' do
      it 'generates data-testid attribute' do
        converter = create_converter({ 'class' => 'Radio', 'items' => ['A'], 'testId' => 'option-group' })
        result = converter.convert
        expect(result).to include('data-testid="option-group"')
      end
    end

    context 'with visibility binding' do
      it 'wraps with conditional rendering' do
        converter = create_converter({ 'class' => 'Radio', 'items' => ['A'], 'visibility' => '@{showOptions}' })
        result = converter.convert
        expect(result).to include('{data.showOptions !== "gone" &&')
      end
    end

    # `value` is the option's identity within the group; the node id is only the
    # fallback. Taking the id unconditionally compared selectedValue against the
    # node name, so the radio could never be checked.
    context 'single radio identity' do
      it 'uses the declared value as the input value' do
        converter = create_converter({ 'class' => 'Radio', 'text' => 'Sample',
                                       'id' => 'target', 'value' => 'sample' })
        result = converter.convert

        expect(result).to include('value="sample"')
      end

      # A STATIC selectedValue is folded rather than compared. Both sides
      # would be string LITERALS, and TypeScript narrows each to its own
      # literal type, so `"sample" === "sample"` is TS2367 "no overlap" — an
      # error inside an @generated file no consumer can patch. The converter
      # knows the answer at codegen time, so it emits the answer.
      it 'checks the radio when selectedValue matches its value' do
        converter = create_converter({ 'class' => 'Radio', 'text' => 'Sample',
                                       'id' => 'target', 'value' => 'sample',
                                       'selectedValue' => 'sample' })
        result = converter.convert

        expect(result).to include('checked={true}')
        expect(result).not_to include('===')
      end

      it 'leaves the radio unchecked when a static selectedValue names another option' do
        converter = create_converter({ 'class' => 'Radio', 'text' => 'Sample',
                                       'id' => 'target', 'value' => 'sample',
                                       'selectedValue' => 'other' })
        result = converter.convert

        expect(result).to include('checked={false}')
        expect(result).not_to include('===')
      end

      # The BOUND form still compares: the left side is a runtime value with
      # no literal type for TypeScript to narrow.
      it 'still compares when selectedValue is a binding' do
        converter = create_converter({ 'class' => 'Radio', 'text' => 'Sample',
                                       'id' => 'target', 'value' => 'sample',
                                       'selectedValue' => '@{picked}' })
        result = converter.convert

        expect(result).to include('checked={data.picked === "sample"}')
      end

      it 'falls back to the node id when value is not declared' do
        converter = create_converter({ 'class' => 'Radio', 'text' => 'Sample', 'id' => 'target' })
        result = converter.convert

        expect(result).to include('value="target"')
      end
    end
  end
end
