# frozen_string_literal: true

require 'swiftui/views/safeareaview_converter'

RSpec.describe SjuiTools::SwiftUI::Views::SafeAreaViewConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#should_ignore_safe_area?' do
    let(:component) { { 'type' => 'SafeAreaView' } }

    it 'returns false' do
      converter = described_class.new(component)
      expect(converter.send(:should_ignore_safe_area?)).to be false
    end
  end

  describe '#apply_safe_area_modifier?' do
    let(:component) { { 'type' => 'SafeAreaView' } }

    it 'returns false' do
      converter = described_class.new(component)
      expect(converter.send(:apply_safe_area_modifier?)).to be false
    end
  end
end
