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

    # effectStyle is expressed as a translucent scrim + .blur(), mirroring
    # DynamicBlurViewComponent (parity family Blur/effectStyle__dark d=17:
    # the codegen path drew nothing at all — blur over empty content).
    it 'renders the Dark effectStyle as a black scrim under the blur' do
      json_data = { 'type' => 'Blur', 'effectStyle' => 'Dark' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('.background(Color.Black.copy(alpha = 0.4f))')
      expect(result[:code]).to include('.blur(10.dp)')
    end

    it 'renders the ExtraLight effectStyle as a bright scrim' do
      json_data = { 'type' => 'Blur', 'effectStyle' => 'ExtraLight' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('.background(Color.White.copy(alpha = 0.6f))')
    end

    it 'does not derive the blur radius from the effectStyle' do
      json_data = { 'type' => 'Blur', 'effectStyle' => 'Dark' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('.blur(10.dp)')
      expect(result[:code]).not_to include('.blur(14.dp)')
    end

    it 'lets a declared background win over the effectStyle scrim' do
      json_data = { 'type' => 'Blur', 'effectStyle' => 'Dark', 'background' => '#FF0000' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).not_to include('Color.Black.copy')
    end
  end
end
