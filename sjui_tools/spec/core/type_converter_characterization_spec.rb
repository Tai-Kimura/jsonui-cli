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

  describe '.format_value' do
    it 'formats nil as the nil literal regardless of type' do
      expect(described_class.format_value(nil, 'String')).to eq('nil')
    end

    it 'quotes strings' do
      expect(described_class.format_value('hi', 'String')).to eq('"hi"')
    end

    it 'coerces Int / Double / Float / Bool' do
      expect(described_class.format_value('42', 'Int')).to eq('42')
      expect(described_class.format_value('1.5', 'Double')).to eq('1.5')
      expect(described_class.format_value('2.5', 'Float')).to eq('2.5')
      expect(described_class.format_value(true, 'Bool')).to eq('true')
    end

    it 'formats hex colors through UIColor.colorWithHexString' do
      expect(described_class.format_value('#FF0000', 'Color'))
        .to eq('Color(uiColor: UIColor.colorWithHexString("#FF0000") ?? .clear)')
    end

    it 'falls back to to_s for unknown Swift types' do
      expect(described_class.format_value(9, 'CustomType')).to eq('9')
    end
  end

  describe '.format_string_value' do
    it 'keeps already double-quoted strings' do
      expect(described_class.send(:format_string_value, '"x"')).to eq('"x"')
    end

    it 'converts single-quoted strings to double quotes' do
      expect(described_class.send(:format_string_value, "'y'")).to eq('"y"')
    end

    it 'escapes embedded quotes (backslashes in plain strings pass through)' do
      expect(described_class.send(:format_string_value, 'a"b')).to eq('"a\\"b"')
    end
  end

  describe '.escape_string' do
    it 'escapes double quotes; the backslash gsub is a no-op today' do
      # `.gsub('\\', '\\\\')` replaces a backslash with a backslash — in a
      # gsub replacement string '\\\\' collapses to one literal backslash.
      # Recorded as-is: today's contract escapes quotes only.
      expect(described_class.send(:escape_string, 'a\\b"c')).to eq('a\\b\\"c')
    end
  end

  describe '.format_color_value' do
    it 'passes non-hex values through unchanged' do
      expect(described_class.send(:format_color_value, 'primary')).to eq('primary')
    end
  end

  describe '.convert_visibility_default_value' do
    it 'quotes the raw value for SwiftUI (String-typed visibility)' do
      expect(described_class.convert_visibility_default_value('visible', 'swiftui')).to eq('"visible"')
    end
  end
end
