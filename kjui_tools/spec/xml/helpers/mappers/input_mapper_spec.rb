# frozen_string_literal: true

require 'xml/helpers/mappers/input_mapper'
require 'xml/helpers/resource_resolver'

RSpec.describe XmlGenerator::Mappers::InputMapper do
  let(:mapper) { described_class.new }

  describe '#map_input_attributes' do
    context 'input type attributes' do
      it 'maps inputType text' do
        result = mapper.map_input_attributes('inputType', 'text')
        expect(result[:name]).to eq('inputType')
        expect(result[:value]).to eq('text')
      end

      it 'maps inputType number' do
        result = mapper.map_input_attributes('inputType', 'number')
        expect(result[:value]).to eq('number')
      end

      it 'maps inputType phone' do
        result = mapper.map_input_attributes('inputType', 'phone')
        expect(result[:value]).to eq('phone')
      end

      it 'maps inputType email to textEmailAddress' do
        result = mapper.map_input_attributes('inputType', 'email')
        expect(result[:value]).to eq('textEmailAddress')
      end

      it 'maps inputType password to textPassword' do
        result = mapper.map_input_attributes('inputType', 'password')
        expect(result[:value]).to eq('textPassword')
      end

      it 'maps inputType multiline to textMultiLine' do
        result = mapper.map_input_attributes('inputType', 'multiline')
        expect(result[:value]).to eq('textMultiLine')
      end
    end

    context 'text input attributes' do
      it 'maps placeholder to hint' do
        result = mapper.map_input_attributes('placeholder', 'Enter text')
        expect(result[:name]).to eq('hint')
        expect(result[:value]).to eq('Enter text')
      end

      it 'maps editable' do
        result = mapper.map_input_attributes('editable', true)
        expect(result[:name]).to eq('editable')
        expect(result[:value]).to eq('true')
      end

      it 'maps singleLine' do
        result = mapper.map_input_attributes('singleLine', true)
        expect(result[:name]).to eq('singleLine')
      end

      it 'maps maxLength' do
        result = mapper.map_input_attributes('maxLength', 100)
        expect(result[:name]).to eq('maxLength')
        expect(result[:value]).to eq('100')
      end
    end

    context 'checkbox/switch attributes' do
      it 'maps checked boolean' do
        result = mapper.map_input_attributes('checked', true)
        expect(result[:name]).to eq('checked')
        expect(result[:value]).to eq('true')
      end

      it 'maps isChecked' do
        result = mapper.map_input_attributes('isChecked', false)
        expect(result[:name]).to eq('checked')
        expect(result[:value]).to eq('false')
      end

      it 'preserves checked data binding' do
        result = mapper.map_input_attributes('checked', '@{data.isEnabled}')
        expect(result[:value]).to eq('@{data.isEnabled}')
      end
    end

    context 'selectbox/spinner attributes' do
      it 'maps selectedItem' do
        result = mapper.map_input_attributes('selectedItem', 'Option 1')
        expect(result[:namespace]).to eq('app')
        expect(result[:name]).to eq('selectedValue')
      end

      it 'maps entries array' do
        result = mapper.map_input_attributes('entries', ['A', 'B', 'C'])
        expect(result[:name]).to eq('items')
        expect(result[:value]).to eq('A|B|C')
      end

      it 'maps items array' do
        result = mapper.map_input_attributes('items', ['X', 'Y'])
        expect(result[:value]).to eq('X|Y')
      end

      it 'maps hintColor' do
        result = mapper.map_input_attributes('hintColor', '#999999')
        expect(result[:name]).to eq('hintColor')
      end

      it 'maps prompt to placeholder' do
        result = mapper.map_input_attributes('prompt', 'Select an option')
        expect(result[:name]).to eq('placeholder')
      end
    end

    context 'date picker attributes' do
      it 'maps datePickerMode' do
        result = mapper.map_input_attributes('datePickerMode', 'date')
        expect(result[:name]).to eq('datePickerMode')
      end

      it 'maps dateFormat' do
        result = mapper.map_input_attributes('dateFormat', 'yyyy-MM-dd')
        expect(result[:name]).to eq('dateFormat')
      end

      it 'maps minDate' do
        result = mapper.map_input_attributes('minDate', '2020-01-01')
        expect(result[:name]).to eq('minDate')
      end

      it 'maps maxDate' do
        result = mapper.map_input_attributes('maxDate', '2030-12-31')
        expect(result[:name]).to eq('maxDate')
      end
    end

    context 'progress/slider attributes' do
      it 'maps progress' do
        result = mapper.map_input_attributes('progress', 50)
        expect(result[:name]).to eq('progress')
        expect(result[:value]).to eq('50')
      end

      it 'maps max' do
        result = mapper.map_input_attributes('max', 100)
        expect(result[:name]).to eq('max')
        expect(result[:value]).to eq('100')
      end

      it 'maps min' do
        result = mapper.map_input_attributes('min', 0)
        expect(result[:name]).to eq('min')
      end

      it 'maps value to progress' do
        result = mapper.map_input_attributes('value', 75)
        expect(result[:name]).to eq('progress')
      end

      it 'preserves value data binding' do
        result = mapper.map_input_attributes('value', '@{data.sliderValue}')
        expect(result[:value]).to eq('@{data.sliderValue}')
      end

      it 'returns nil for onValueChange' do
        result = mapper.map_input_attributes('onValueChange', 'handleChange')
        expect(result).to be_nil
      end
    end

    context 'event attributes' do
      it 'maps onClick' do
        result = mapper.map_input_attributes('onClick', 'handleClick')
        expect(result[:name]).to eq('onClick')
        expect(result[:value]).to eq('handleClick')
      end

      it 'returns nil for onTextChanged' do
        result = mapper.map_input_attributes('onTextChanged', 'handleChange')
        expect(result).to be_nil
      end
    end

    context 'unknown attribute' do
      it 'returns nil for unknown attribute' do
        result = mapper.map_input_attributes('unknown', 'value')
        expect(result).to be_nil
      end
    end
  end
end
