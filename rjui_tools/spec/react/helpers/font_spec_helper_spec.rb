# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/helpers/font_spec_helper'

RSpec.describe RjuiTools::React::Helpers::FontSpecHelper do
  describe '.build_resolve_spread' do
    it 'emits a JS spread expression with all four FontSpec fields when family + weight + size are set' do
      result = described_class.build_resolve_spread(
        family: 'Helvetica',
        weight: 'bold',
        size:   16,
        italic: false
      )
      expect(result).to eq(
        "...Configuration.Font.resolve({ family: 'Helvetica', weight: 'bold', size: 16, italic: false })"
      )
    end

    it 'omits absent fields but keeps italic which always has a default' do
      result = described_class.build_resolve_spread(family: 'Inter')
      expect(result).to eq(
        "...Configuration.Font.resolve({ family: 'Inter', italic: false })"
      )
    end

    it 'returns nil when no fields are set (no work to do)' do
      expect(described_class.build_resolve_spread).to be_nil
    end

    it 'preserves italic: true for future-use cases' do
      result = described_class.build_resolve_spread(family: 'Times', italic: true)
      expect(result).to include('italic: true')
    end

    it 'renders numeric weights as bare JS numbers' do
      result = described_class.build_resolve_spread(family: 'Inter', weight: 600)
      expect(result).to include('weight: 600')
    end

    it 'escapes single quotes in family names so the JS literal stays valid' do
      result = described_class.build_resolve_spread(family: "O'Neill")
      expect(result).to include("family: 'O\\'Neill'")
    end
  end

  describe '.map_weight_for_css' do
    it 'maps known weight tokens via the shared mapping JSON' do
      expect(described_class.map_weight_for_css('bold')).to eq('bold')
      expect(described_class.map_weight_for_css('semibold')).to eq('600')
      expect(described_class.map_weight_for_css('medium')).to eq('500')
      expect(described_class.map_weight_for_css('regular')).to eq('normal')
    end

    it 'is case insensitive' do
      expect(described_class.map_weight_for_css('Bold')).to eq('bold')
      expect(described_class.map_weight_for_css('SEMIBOLD')).to eq('600')
    end

    it 'returns the raw string for unknown weights so providers can route them' do
      expect(described_class.map_weight_for_css('nineHundred')).to eq('nineHundred')
    end

    it 'returns nil when given nil' do
      expect(described_class.map_weight_for_css(nil)).to be_nil
    end
  end

  describe '.builtin_weight_mapping (defensive fallback)' do
    it 'provides the full css table so a missing file never degrades output' do
      mapping = described_class.builtin_weight_mapping
      expect(mapping['weights']['medium']['css']).to eq('500')
      expect(mapping['weights']['semibold']['css']).to eq('600')
      expect(mapping['weights']['bold']['css']).to eq('bold')
      expect(mapping['weights']['regular']['css']).to eq('normal')
      expect(mapping['default_on_unknown']).to eq('regular')
    end

    it 'matches map_weight_for_css when the built-in mapping is the active source' do
      # Simulate the no-file path by stubbing the loader onto the built-in table.
      allow(described_class).to receive(:load_weight_mapping)
        .and_return(described_class.builtin_weight_mapping)
      described_class.instance_variable_set(:@weight_mapping, nil)

      expect(described_class.map_weight_for_css('semibold')).to eq('600')
      expect(described_class.map_weight_for_css('bold')).to eq('bold')
    ensure
      described_class.instance_variable_set(:@weight_mapping, nil)
    end
  end

  describe 'SPREAD_KEY_PREFIX' do
    it 'is a non-empty constant the BaseConverter key namespacing relies on' do
      expect(described_class::SPREAD_KEY_PREFIX).to be_a(String)
      expect(described_class::SPREAD_KEY_PREFIX).not_to be_empty
    end
  end
end
