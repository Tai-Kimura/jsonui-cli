# frozen_string_literal: true

require 'xml/helpers/mappers/dimension_mapper'

RSpec.describe XmlGenerator::Mappers::DimensionMapper do
  let(:mapper) { described_class.new }

  describe '#map_dimension' do
    it 'returns wrap_content for nil' do
      expect(mapper.map_dimension(nil)).to eq('wrap_content')
    end

    it 'returns wrap_content for empty string' do
      expect(mapper.map_dimension('')).to eq('wrap_content')
    end

    it 'maps matchParent' do
      expect(mapper.map_dimension('matchParent')).to eq('match_parent')
    end

    it 'maps match_parent' do
      expect(mapper.map_dimension('match_parent')).to eq('match_parent')
    end

    it 'maps wrapContent' do
      expect(mapper.map_dimension('wrapContent')).to eq('wrap_content')
    end

    it 'maps wrap_content' do
      expect(mapper.map_dimension('wrap_content')).to eq('wrap_content')
    end

    it 'maps integer to dp' do
      expect(mapper.map_dimension(16)).to eq('16dp')
    end

    it 'maps float to dp as integer' do
      expect(mapper.map_dimension(16.5)).to eq('16dp')
    end

    it 'maps string integer to dp' do
      expect(mapper.map_dimension('100')).to eq('100dp')
    end

    it 'maps string float to dp' do
      expect(mapper.map_dimension('10.5')).to eq('10dp')
    end

    it 'passes through existing dp values' do
      expect(mapper.map_dimension('24dp')).to eq('24dp')
    end

    it 'maps percentage to 0dp' do
      expect(mapper.map_dimension('50%')).to eq('0dp')
    end

    it 'returns string for unknown values' do
      expect(mapper.map_dimension('unknown')).to eq('unknown')
    end
  end

  describe '#convert_dimension' do
    it 'converts integer to dp' do
      expect(mapper.convert_dimension(16)).to eq('16dp')
    end

    it 'converts float to dp' do
      expect(mapper.convert_dimension(16.5)).to eq('16dp')
    end

    it 'converts string integer to dp' do
      expect(mapper.convert_dimension('24')).to eq('24dp')
    end

    it 'passes through non-numeric strings' do
      expect(mapper.convert_dimension('match_parent')).to eq('match_parent')
    end

    it 'handles array by using first value' do
      expect(mapper.convert_dimension([10, 20, 30, 40])).to eq('10dp')
    end

    it 'handles empty array' do
      expect(mapper.convert_dimension([])).to eq('0dp')
    end

    it 'converts other types to string' do
      expect(mapper.convert_dimension(true)).to eq('true')
    end
  end
end
