# frozen_string_literal: true

require 'compose/helpers/responsive_helper'

# ResponsiveHelper is now detection-only: the extracted-wrapper generators it
# once carried were dead code (all live responsive emission is the inline
# if/else path in ComposeBuilder — see compose_builder_spec.rb for coverage
# of the emitted conditions).
RSpec.describe KjuiTools::Compose::Helpers::ResponsiveHelper do
  describe '.responsive?' do
    it 'returns true when the component has a responsive block' do
      expect(described_class.responsive?({ 'type' => 'View', 'responsive' => { 'regular' => {} } })).to be true
    end

    it 'returns false when the component has no responsive block' do
      expect(described_class.responsive?({ 'type' => 'View' })).to be false
    end

    it 'treats an empty responsive block as present (presence check only)' do
      expect(described_class.responsive?({ 'type' => 'View', 'responsive' => {} })).to be true
    end
  end
end
