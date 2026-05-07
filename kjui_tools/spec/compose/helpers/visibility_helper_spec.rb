# frozen_string_literal: true

require 'compose/helpers/visibility_helper'
require 'compose/helpers/modifier_builder'

RSpec.describe KjuiTools::Compose::Helpers::VisibilityHelper do
  let(:required_imports) { Set.new }

  describe '.wrap_with_visibility' do
    it 'returns component unchanged when no visibility attributes' do
      json_data = { 'type' => 'Text' }
      component_code = 'Text("Hello")'
      result = described_class.wrap_with_visibility(json_data, component_code, 0, required_imports)
      expect(result).to eq(component_code)
    end

    it 'wraps with VisibilityWrapper for static visibility' do
      json_data = { 'visibility' => 'invisible' }
      component_code = 'Text("Hello")'
      result = described_class.wrap_with_visibility(json_data, component_code, 0, required_imports)
      expect(result).to include('VisibilityWrapper(')
      expect(result).to include('visibility = "invisible"')
    end

    it 'wraps with VisibilityWrapper for visibility binding' do
      json_data = { 'visibility' => '@{isVisible}' }
      component_code = 'Text("Hello")'
      result = described_class.wrap_with_visibility(json_data, component_code, 0, required_imports)
      expect(result).to include('VisibilityWrapper(')
      expect(result).to include('visibility = data.isVisible')
    end

    it 'wraps with VisibilityWrapper for hidden attribute' do
      json_data = { 'hidden' => true }
      component_code = 'Text("Hello")'
      result = described_class.wrap_with_visibility(json_data, component_code, 0, required_imports)
      expect(result).to include('VisibilityWrapper(')
      expect(result).to include('hidden = true')
    end

    it 'wraps with VisibilityWrapper for hidden binding' do
      json_data = { 'hidden' => '@{isHidden}' }
      component_code = 'Text("Hello")'
      result = described_class.wrap_with_visibility(json_data, component_code, 0, required_imports)
      expect(result).to include('hidden = data.isHidden')
    end

    it 'includes closing bracket' do
      json_data = { 'visibility' => 'visible' }
      component_code = 'Text("Hello")'
      result = described_class.wrap_with_visibility(json_data, component_code, 0, required_imports)
      expect(result).to include('}')
    end
  end

  describe '.should_skip_render?' do
    it 'returns true for static gone visibility' do
      json_data = { 'visibility' => 'gone' }
      expect(described_class.should_skip_render?(json_data)).to be true
    end

    it 'returns true for static hidden' do
      json_data = { 'hidden' => true }
      expect(described_class.should_skip_render?(json_data)).to be true
    end

    it 'returns false for visibility binding' do
      json_data = { 'visibility' => '@{isGone ? "gone" : "visible"}' }
      expect(described_class.should_skip_render?(json_data)).to be false
    end

    it 'returns false for hidden binding' do
      json_data = { 'hidden' => '@{isHidden}' }
      expect(described_class.should_skip_render?(json_data)).to be false
    end

    it 'returns false for visible visibility' do
      json_data = { 'visibility' => 'visible' }
      expect(described_class.should_skip_render?(json_data)).to be false
    end

    it 'returns false for no visibility attributes' do
      json_data = { 'type' => 'Text' }
      expect(described_class.should_skip_render?(json_data)).to be false
    end
  end
end
