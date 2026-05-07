# frozen_string_literal: true

require 'swiftui/converter_factory'

RSpec.describe SjuiTools::SwiftUI::ConverterFactory, 'responsive support' do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  let(:factory) { described_class.new }

  describe '#responsive_functions' do
    it 'starts empty' do
      expect(factory.responsive_functions).to eq([])
    end
  end

  describe '#responsive_counter' do
    it 'starts at 0' do
      expect(factory.responsive_counter).to eq(0)
    end
  end

  describe '#next_responsive_name' do
    it 'returns responsive0 first' do
      expect(factory.next_responsive_name).to eq('responsive0')
    end

    it 'increments the counter' do
      factory.next_responsive_name
      expect(factory.responsive_counter).to eq(1)
      expect(factory.next_responsive_name).to eq('responsive1')
    end
  end

  describe '#register_responsive_function' do
    it 'adds function code to the list' do
      factory.register_responsive_function('func code')
      expect(factory.responsive_functions).to eq(['func code'])
    end

    it 'accumulates multiple functions' do
      factory.register_responsive_function('func1')
      factory.register_responsive_function('func2')
      expect(factory.responsive_functions.length).to eq(2)
    end
  end

  describe '#reset_responsive' do
    it 'clears functions and resets counter' do
      factory.next_responsive_name
      factory.register_responsive_function('code')

      factory.reset_responsive

      expect(factory.responsive_functions).to eq([])
      expect(factory.responsive_counter).to eq(0)
    end
  end
end
