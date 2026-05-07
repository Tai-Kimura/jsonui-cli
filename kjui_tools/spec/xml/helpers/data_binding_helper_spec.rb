# frozen_string_literal: true

require 'xml/helpers/data_binding_helper'

RSpec.describe XmlGenerator::DataBindingHelper do
  describe '.process_data_binding' do
    it 'returns nil for nil input' do
      expect(described_class.process_data_binding(nil)).to be_nil
    end

    it 'returns value as-is for non-binding strings' do
      expect(described_class.process_data_binding('Hello')).to eq('Hello')
    end

    it 'returns value as-is for non-string values' do
      expect(described_class.process_data_binding(123)).to eq(123)
      expect(described_class.process_data_binding(true)).to eq(true)
    end

    it 'adds data. prefix for simple variable bindings' do
      result = described_class.process_data_binding('@{userName}')
      expect(result).to eq('@{data.userName}')
    end

    it 'adds data. prefix for single word variables' do
      result = described_class.process_data_binding('@{title}')
      expect(result).to eq('@{data.title}')
    end

    it 'adds viewModel. prefix for method calls' do
      result = described_class.process_data_binding('@{handleClick()}')
      expect(result).to eq('@{viewModel.handleClick()}')
    end

    it 'adds viewModel. prefix for method calls with parameters' do
      result = described_class.process_data_binding('@{showDialog(true)}')
      expect(result).to eq('@{viewModel.showDialog(true)}')
    end

    it 'keeps value as-is if already has viewModel prefix' do
      result = described_class.process_data_binding('@{viewModel.onClick()}')
      expect(result).to eq('@{viewModel.onClick()}')
    end

    it 'keeps complex expressions as-is' do
      result = described_class.process_data_binding('@{data.user.name}')
      expect(result).to eq('@{data.user.name}')
    end

    it 'handles expressions with dots' do
      result = described_class.process_data_binding('@{user.profile.name}')
      expect(result).to eq('@{user.profile.name}')
    end
  end
end
