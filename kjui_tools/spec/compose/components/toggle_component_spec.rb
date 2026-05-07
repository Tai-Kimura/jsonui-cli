# frozen_string_literal: true

require 'compose/components/toggle_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'

RSpec.describe KjuiTools::Compose::Components::ToggleComponent do
  let(:required_imports) { Set.new }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
  end

  describe '.generate' do
    it 'generates basic Switch component' do
      json_data = { 'type' => 'Toggle' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Switch(')
      expect(result).to include('checked = false')
    end

    it 'generates Switch with isOn true' do
      json_data = { 'type' => 'Toggle', 'isOn' => true }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('checked = true')
    end

    it 'generates Switch with isOn false' do
      json_data = { 'type' => 'Toggle', 'isOn' => false }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('checked = false')
    end

    it 'generates Switch with data binding' do
      json_data = { 'type' => 'Toggle', 'data' => 'isEnabled' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('checked = data.isEnabled')
      expect(result).to include('onCheckedChange = { newValue -> data.isEnabled = newValue }')
    end

    it 'generates Switch with onclick handler' do
      json_data = { 'type' => 'Toggle', 'onclick' => 'handleToggle' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('handleToggle')
    end

    it 'generates Switch with empty onCheckedChange when no handler' do
      json_data = { 'type' => 'Toggle' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('onCheckedChange = { }')
    end

    it 'generates Switch with tintColor' do
      json_data = { 'type' => 'Toggle', 'tintColor' => '#007AFF' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('colors = SwitchDefaults.colors(')
      expect(result).to include('checkedThumbColor')
      expect(result).to include('checkedTrackColor')
      expect(required_imports).to include(:switch_colors)
    end

    it 'generates Switch with backgroundColor' do
      json_data = { 'type' => 'Toggle', 'backgroundColor' => '#CCCCCC' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('colors = SwitchDefaults.colors(')
      expect(result).to include('uncheckedTrackColor')
    end

    it 'generates Switch with both tintColor and backgroundColor' do
      json_data = {
        'type' => 'Toggle',
        'tintColor' => '#007AFF',
        'backgroundColor' => '#CCCCCC'
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('checkedThumbColor')
      expect(result).to include('checkedTrackColor')
      expect(result).to include('uncheckedTrackColor')
    end

    it 'generates Switch with padding' do
      json_data = { 'type' => 'Toggle', 'padding' => 8 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Switch(')
    end

    it 'generates Switch with margins' do
      json_data = { 'type' => 'Toggle', 'margins' => [4, 8] }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Switch(')
    end

    it 'generates Switch with weight in Row parent' do
      json_data = { 'type' => 'Toggle', 'weight' => 1 }
      result = described_class.generate(json_data, 0, required_imports, 'Row')
      expect(result).to include('Switch(')
    end

    it 'generates Switch with weight in Column parent' do
      json_data = { 'type' => 'Toggle', 'weight' => 1 }
      result = described_class.generate(json_data, 0, required_imports, 'Column')
      expect(result).to include('Switch(')
    end
  end

  describe '.indent' do
    it 'returns text unchanged for level 0' do
      result = described_class.send(:indent, 'text', 0)
      expect(result).to eq('text')
    end

    it 'adds indentation for level 1' do
      result = described_class.send(:indent, 'text', 1)
      expect(result).to eq('    text')
    end

    it 'preserves empty lines' do
      result = described_class.send(:indent, "line1\n\nline2", 1)
      expect(result).to eq("    line1\n\n    line2")
    end
  end
end
