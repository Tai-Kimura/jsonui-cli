# frozen_string_literal: true

require 'xml/helpers/binding_parser'

RSpec.describe XmlGenerator::BindingParser do
  let(:parser) { described_class.new }

  describe '#parse' do
    it 'parses simple binding expression' do
      result = parser.parse('@{userName}')
      expect(result).to include('data.userName')
    end

    it 'parses property access binding' do
      result = parser.parse('@{user.name}')
      expect(result).to include('data.user.name')
    end

    it 'parses method call binding' do
      result = parser.parse('@{getUserName()}')
      expect(result).to include('viewModel.getUserName()')
    end

    it 'handles viewModel prefix in method call' do
      result = parser.parse('@{viewModel.onSubmit()}')
      expect(result).to include('viewModel.onSubmit()')
    end

    it 'parses conditional expression' do
      result = parser.parse('@{isVisible ? View.VISIBLE : View.GONE}')
      expect(result).to include('data.isVisible')
    end

    it 'parses string template' do
      result = parser.parse('@{`Hello ${userName}`}')
      expect(result).to include('data.userName')
    end

    it 'returns non-binding text unchanged' do
      result = parser.parse('plain text')
      expect(result).to eq('plain text')
    end
  end

  describe '#get_bindings' do
    it 'returns unique bindings' do
      parser.parse('@{userName}')
      parser.parse('@{userName}')
      parser.parse('@{email}')
      expect(parser.get_bindings.length).to eq(2)
    end
  end

  describe '#has_bindings?' do
    it 'returns false initially' do
      expect(parser.has_bindings?).to be false
    end

    it 'returns true after parsing binding' do
      parser.parse('@{userName}')
      expect(parser.has_bindings?).to be true
    end
  end
end

RSpec.describe XmlGenerator::DataBindingManager do
  let(:manager) { described_class.new }

  describe '#add_variable' do
    it 'adds a variable' do
      manager.add_variable('userName', 'String')
      variables = manager.instance_variable_get(:@variables)
      expect(variables).to include({ name: 'userName', type: 'String' })
    end
  end

  describe '#add_import' do
    it 'adds an import' do
      manager.add_import('android.view.View')
      imports = manager.instance_variable_get(:@imports)
      expect(imports).to include('android.view.View')
    end
  end

  describe '#add_converter' do
    it 'adds a converter' do
      manager.add_converter('DateConverter')
      converters = manager.instance_variable_get(:@converters)
      expect(converters).to include('DateConverter')
    end
  end
end
