# frozen_string_literal: true

require 'compose/components/indicator_component'
require 'compose/helpers/modifier_builder'

RSpec.describe KjuiTools::Compose::Components::IndicatorComponent do
  let(:required_imports) { Set.new }

  describe '.generate' do
    it 'generates indicator component' do
      json_data = { 'type' => 'Indicator' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result.to_s).to match(/Indicator|Progress/)
    end

    it 'generates indicator with progress' do
      json_data = { 'type' => 'Indicator', 'progress' => 0.5 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result.to_s).to match(/ProgressIndicator/)
    end
  end
end
