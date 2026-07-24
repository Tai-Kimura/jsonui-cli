# frozen_string_literal: true

require 'spec_helper'
require 'tmpdir'
require_relative '../../lib/core/layout_variant'

RSpec.describe JsonUIShared::LayoutVariant do
  describe '.split' do
    it 'splits a variant stem into base and size class' do
      expect(described_class.split('home@regular')).to eq(%w[home regular])
    end

    it 'returns nil size class for base stems' do
      expect(described_class.split('home')).to eq(['home', nil])
    end

    it 'splits on the last @ for nested (invalid) names' do
      expect(described_class.split('a@b@c')).to eq(%w[a@b c])
    end
  end

  describe '.variant?' do
    it 'detects variants from full paths' do
      expect(described_class.variant?('/x/Layouts/home@regular.json')).to be true
      expect(described_class.variant?('/x/Layouts/home.json')).to be false
    end

    it 'flags unknown suffixes too (exclusion must not depend on the gate)' do
      expect(described_class.variant?('home@tablet.json')).to be true
    end
  end

  describe '.variants_for' do
    it 'finds sibling variant files by valid size class only' do
      Dir.mktmpdir do |dir|
        base = File.join(dir, 'home.json')
        File.write(base, '{}')
        File.write(File.join(dir, 'home@regular.json'), '{}')
        File.write(File.join(dir, 'home@compact.json'), '{}')
        File.write(File.join(dir, 'home@tablet.json'), '{}')

        found = described_class.variants_for(base)
        expect(found.keys).to eq(%w[compact regular])
        expect(found['regular']).to end_with('home@regular.json')
      end
    end
  end
end
