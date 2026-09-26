# frozen_string_literal: true

require 'core/type_converter'

# Characterization of TypeConverter formatting/parsing paths not covered by
# type_converter_spec — these fix current behavior ahead of the cross-toolchain
# validator consolidation (W3-2). A failure means emitted Swift changed.
RSpec.describe SjuiTools::Core::TypeConverter do
  describe '.parse_parameter_list' do
    it 'returns empty string for nil or empty input' do
      expect(described_class.parse_parameter_list(nil)).to eq('')
      expect(described_class.parse_parameter_list('')).to eq('')
    end

    it 'converts each parameter through to_swift_type' do
      expect(described_class.parse_parameter_list('int, string')).to eq('Int, String')
    end
  end

  describe '.to_swift_type with grouped function types' do
    it 'unwraps grouping parentheses around a function type' do
      expect(described_class.to_swift_type('((Int) -> Void)')).to eq('((Int) -> Void)?')
    end
  end

  describe '.get_first_parameter_type' do
    it 'extracts the first parameter of a function type' do
      expect(described_class.get_first_parameter_type('(String) -> Void')).to eq('String')
    end
  end

  describe '.get_event_type' do
    it 'returns the raw mapping value when the event entry is not per-mode' do
      expect(described_class.get_event_type({ 'type' => 'Button' }, 'onclick', 'swiftui')).to be_nil
    end
  end

  describe '.convert_visibility_default_value' do
    it 'quotes the raw value for SwiftUI (String-typed visibility)' do
      expect(described_class.convert_visibility_default_value('visible', 'swiftui')).to eq('"visible"')
    end
  end
end
