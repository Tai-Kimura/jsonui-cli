# frozen_string_literal: true

require 'core/responsive_resolver'

RSpec.describe JsonUIShared::ResponsiveResolver do
  describe '.responsive?' do
    it 'returns true when component has responsive hash' do
      component = { 'responsive' => { 'regular' => {} } }
      expect(described_class.responsive?(component)).to be true
    end

    it 'returns false when component has no responsive' do
      component = { 'type' => 'View' }
      expect(described_class.responsive?(component)).to be false
    end

    it 'returns false when responsive is not a hash' do
      component = { 'responsive' => 'invalid' }
      expect(described_class.responsive?(component)).to be false
    end

    it 'returns false for nil' do
      expect(described_class.responsive?(nil)).to be false
    end

    it 'returns false for non-hash' do
      expect(described_class.responsive?('string')).to be false
    end
  end

  describe '.size_classes' do
    it 'returns valid size class keys' do
      component = {
        'responsive' => {
          'regular' => {},
          'landscape' => {},
          'invalid_key' => {}
        }
      }
      result = described_class.size_classes(component)
      expect(result).to contain_exactly('regular', 'landscape')
    end

    it 'returns empty array for non-responsive component' do
      expect(described_class.size_classes({ 'type' => 'View' })).to eq([])
    end
  end

  describe '.overridden_keys' do
    it 'returns all overridden attribute keys' do
      component = {
        'responsive' => {
          'regular' => { 'orientation' => 'horizontal', 'spacing' => 24 },
          'landscape' => { 'spacing' => 16 }
        }
      }
      keys = described_class.overridden_keys(component)
      expect(keys).to include('orientation', 'spacing')
      expect(keys.size).to eq(2)
    end

    it 'returns empty set for non-responsive component' do
      expect(described_class.overridden_keys({ 'type' => 'View' })).to be_empty
    end
  end

  describe '.resolve' do
    let(:component) do
      {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 8,
        'responsive' => {
          'regular' => { 'orientation' => 'horizontal', 'spacing' => 24 }
        }
      }
    end

    it 'merges overrides for the given size class' do
      result = described_class.resolve(component, 'regular')
      expect(result['orientation']).to eq('horizontal')
      expect(result['spacing']).to eq(24)
      expect(result['type']).to eq('View')
    end

    it 'removes responsive key from result' do
      result = described_class.resolve(component, 'regular')
      expect(result).not_to have_key('responsive')
    end

    it 'returns component unchanged for unknown size class' do
      result = described_class.resolve(component, 'nonexistent')
      expect(result['orientation']).to eq('vertical')
    end

    it 'does not override type, child, or data keys' do
      component_with_override = component.merge(
        'responsive' => { 'regular' => { 'type' => 'Other', 'child' => [], 'spacing' => 24 } }
      )
      result = described_class.resolve(component_with_override, 'regular')
      expect(result['type']).to eq('View')
      expect(result['spacing']).to eq(24)
    end
  end

  describe '.build_branches' do
    let(:component) do
      {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 8,
        'responsive' => {
          'regular' => { 'orientation' => 'horizontal', 'spacing' => 24 },
          'landscape' => { 'spacing' => 16 },
          'regular-landscape' => { 'orientation' => 'horizontal', 'spacing' => 32 }
        }
      }
    end

    it 'returns branches in priority order' do
      branches = described_class.build_branches(component)
      size_classes = branches.map { |b| b[:size_class] }

      # Compound first, then single, then default (nil)
      expect(size_classes).to eq(['regular-landscape', 'landscape', 'regular', nil])
    end

    it 'includes default branch at the end' do
      branches = described_class.build_branches(component)
      default_branch = branches.last
      expect(default_branch[:size_class]).to be_nil
      expect(default_branch[:attrs]['orientation']).to eq('vertical')
      expect(default_branch[:attrs]['spacing']).to eq(8)
    end

    it 'merges attributes correctly per branch' do
      branches = described_class.build_branches(component)
      regular_landscape = branches.find { |b| b[:size_class] == 'regular-landscape' }
      expect(regular_landscape[:attrs]['orientation']).to eq('horizontal')
      expect(regular_landscape[:attrs]['spacing']).to eq(32)
    end

    it 'returns single default branch for non-responsive component' do
      simple = { 'type' => 'View', 'orientation' => 'vertical' }
      branches = described_class.build_branches(simple)
      expect(branches.length).to eq(1)
      expect(branches.first[:size_class]).to be_nil
    end
  end

  describe '.parse_size_class' do
    it 'parses regular' do
      result = described_class.parse_size_class('regular')
      expect(result).to eq({ width: 'regular', landscape: false })
    end

    it 'parses landscape' do
      result = described_class.parse_size_class('landscape')
      expect(result).to eq({ width: nil, landscape: true })
    end

    it 'parses regular-landscape' do
      result = described_class.parse_size_class('regular-landscape')
      expect(result).to eq({ width: 'regular', landscape: true })
    end

    it 'parses compact-landscape' do
      result = described_class.parse_size_class('compact-landscape')
      expect(result).to eq({ width: 'compact', landscape: true })
    end

    it 'parses nil' do
      result = described_class.parse_size_class(nil)
      expect(result).to eq({ width: nil, landscape: false })
    end
  end
end
