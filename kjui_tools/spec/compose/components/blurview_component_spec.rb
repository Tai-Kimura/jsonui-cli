# frozen_string_literal: true

require 'compose/components/blurview_component'
require 'compose/helpers/modifier_builder'

RSpec.describe KjuiTools::Compose::Components::BlurviewComponent do
  let(:required_imports) { Set.new }

  describe '.generate' do
    it 'generates blur view component' do
      json_data = { 'type' => 'BlurView' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).not_to be_nil
    end

    it 'generates blur view with radius' do
      json_data = { 'type' => 'BlurView', 'blurRadius' => 10 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result.to_s).to match(/blur|10/i)
    end
  end
end
