# frozen_string_literal: true

require 'compose/components/gradientview_component'
require 'compose/helpers/modifier_builder'

RSpec.describe KjuiTools::Compose::Components::GradientviewComponent do
  let(:required_imports) { Set.new }

  describe '.generate' do
    it 'generates gradient view component' do
      json_data = { 'type' => 'GradientView' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).not_to be_nil
    end

    it 'generates gradient with colors' do
      json_data = { 'type' => 'GradientView', 'colors' => ['#FF0000', '#0000FF'] }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result.to_s).to match(/gradient|Brush/i)
    end

    it 'generates gradient with direction' do
      json_data = { 'type' => 'GradientView', 'direction' => 'horizontal', 'colors' => ['#FF0000', '#0000FF'] }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).not_to be_nil
    end
  end
end
