#!/usr/bin/env ruby

require_relative '../spec_helper'
require_relative '../../lib/core/normalization'

RSpec.describe KjuiTools::Core::Normalization do
  after do
    described_class.layout_canonicalized = false
  end

  describe '.canonicalized?' do
    it 'detects the L1 marker' do
      layout = { '$jui' => { 'normalized' => 'L1', 'schemaVersion' => 1 }, 'type' => 'View' }
      expect(described_class.canonicalized?(layout)).to be true
    end

    it 'detects the L2 marker (includes L1 canonicalization)' do
      layout = { '$jui' => { 'normalized' => 'L2', 'schemaVersion' => 1 }, 'type' => 'View' }
      expect(described_class.canonicalized?(layout)).to be true
    end

    it 'is false without a marker' do
      expect(described_class.canonicalized?({ 'type' => 'View' })).to be false
    end

    it 'is false for a malformed marker' do
      expect(described_class.canonicalized?({ '$jui' => 'L1' })).to be false
      expect(described_class.canonicalized?({ '$jui' => { 'normalized' => 'L9' } })).to be false
    end

    it 'is false for non-hash input' do
      expect(described_class.canonicalized?(nil)).to be false
      expect(described_class.canonicalized?([])).to be false
    end
  end

  describe '.attr_lookup' do
    it 'prefers the canonical spelling' do
      json = { 'minimum' => 1, 'minimumValue' => 2 }
      expect(described_class.attr_lookup(json, 'minimum', 'minimumValue')).to eq(1)
    end

    it 'falls back to alias spellings on the L0 path' do
      json = { 'minimumValue' => 2 }
      expect(described_class.attr_lookup(json, 'minimum', 'minimumValue')).to eq(2)
    end

    it 'does not read alias spellings when the layout is canonicalized' do
      described_class.layout_canonicalized = true
      json = { 'minimumValue' => 2 }
      expect(described_class.attr_lookup(json, 'minimum', 'minimumValue')).to be_nil
    end

    it 'still reads the canonical spelling when the layout is canonicalized' do
      described_class.layout_canonicalized = true
      json = { 'minimum' => 1 }
      expect(described_class.attr_lookup(json, 'minimum', 'minimumValue')).to eq(1)
    end

    it 'preserves false values' do
      json = { 'minimum' => false }
      expect(described_class.attr_lookup(json, 'minimum', 'minimumValue')).to be false
    end
  end
end
