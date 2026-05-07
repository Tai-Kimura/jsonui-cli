# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/helpers/lucide_icon_helper'

RSpec.describe RjuiTools::React::Helpers::LucideIconHelper do
  describe '.map_to_lucide' do
    it 'returns canonical name for known SF Symbol identifiers' do
      expect(described_class.map_to_lucide('house')).to eq('Home')
      expect(described_class.map_to_lucide('person')).to eq('User')
      expect(described_class.map_to_lucide('gearshape')).to eq('Settings')
    end

    it 'returns canonical name when given the Lucide name directly' do
      expect(described_class.map_to_lucide('Circle')).to eq('Circle')
      expect(described_class.map_to_lucide('Settings')).to eq('Settings')
    end

    it 'strips SF Symbol modifier suffixes like .fill' do
      expect(described_class.map_to_lucide('heart.fill')).to eq('Heart')
    end

    it 'falls back to PascalCase conversion for kebab-case identifiers' do
      expect(described_class.map_to_lucide('arrow-right')).to eq('ArrowRight')
    end

    it 'falls back to PascalCase conversion for snake_case identifiers' do
      expect(described_class.map_to_lucide('arrow_right')).to eq('ArrowRight')
    end

    it 'returns nil for nil or empty input' do
      expect(described_class.map_to_lucide(nil)).to be_nil
      expect(described_class.map_to_lucide('')).to be_nil
    end
  end
end
