#!/usr/bin/env ruby

require_relative '../spec_helper'
require_relative '../../lib/core/normalization'

RSpec.describe RjuiTools::Core::Normalization do
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
end
