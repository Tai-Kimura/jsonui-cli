# frozen_string_literal: true

require 'core/type_converter'

RSpec.describe KjuiTools::Core::TypeConverter do
  describe '.to_kotlin_type' do
    context 'with common types' do
      it 'converts String types' do
        expect(described_class.to_kotlin_type('String')).to eq('String')
        expect(described_class.to_kotlin_type('string')).to eq('String')
      end

      it 'converts Int types' do
        expect(described_class.to_kotlin_type('Int')).to eq('Int')
        expect(described_class.to_kotlin_type('int')).to eq('Int')
        expect(described_class.to_kotlin_type('Integer')).to eq('Int')
        expect(described_class.to_kotlin_type('integer')).to eq('Int')
      end

      it 'converts Double types' do
        expect(described_class.to_kotlin_type('Double')).to eq('Double')
        expect(described_class.to_kotlin_type('double')).to eq('Double')
      end

      it 'converts Float types' do
        expect(described_class.to_kotlin_type('Float')).to eq('Float')
        expect(described_class.to_kotlin_type('float')).to eq('Float')
      end

      it 'converts Bool to Boolean' do
        expect(described_class.to_kotlin_type('Bool')).to eq('Boolean')
        expect(described_class.to_kotlin_type('bool')).to eq('Boolean')
        expect(described_class.to_kotlin_type('Boolean')).to eq('Boolean')
        expect(described_class.to_kotlin_type('boolean')).to eq('Boolean')
      end

      it 'converts CGFloat to Float' do
        expect(described_class.to_kotlin_type('CGFloat')).to eq('Float')
      end

      it 'converts Dp and Alignment types' do
        expect(described_class.to_kotlin_type('Dp')).to eq('Dp')
        expect(described_class.to_kotlin_type('Alignment')).to eq('Alignment')
      end
    end

    context 'with mode-specific types' do
      it 'converts Color to Color for compose mode' do
        expect(described_class.to_kotlin_type('Color', 'compose')).to eq('Color')
        expect(described_class.to_kotlin_type('color', 'compose')).to eq('Color')
      end

      it 'converts Color to Int for xml mode' do
        expect(described_class.to_kotlin_type('Color', 'xml')).to eq('Int')
        expect(described_class.to_kotlin_type('color', 'xml')).to eq('Int')
      end

      it 'defaults to compose when no mode specified for Color' do
        expect(described_class.to_kotlin_type('Color')).to eq('Color')
      end
    end

    context 'with unknown types' do
      it 'returns the type as-is' do
        expect(described_class.to_kotlin_type('CustomType')).to eq('CustomType')
        expect(described_class.to_kotlin_type('MyViewModel')).to eq('MyViewModel')
      end
    end

    context 'with Array syntax' do
      it 'converts Array(ElementType) to List<ElementType>' do
        expect(described_class.to_kotlin_type('Array(String)')).to eq('List<String>')
        expect(described_class.to_kotlin_type('Array(Int)')).to eq('List<Int>')
        expect(described_class.to_kotlin_type('Array(ItemData)')).to eq('List<ItemData>')
      end

      it 'converts nested element types' do
        expect(described_class.to_kotlin_type('Array(Bool)')).to eq('List<Boolean>')
      end
    end

    context 'with Dictionary syntax' do
      it 'converts Dictionary(KeyType, ValueType) to Map<KeyType, ValueType>' do
        expect(described_class.to_kotlin_type('Dictionary(String, Any)')).to eq('Map<String, Any>')
        expect(described_class.to_kotlin_type('Dictionary(String, Int)')).to eq('Map<String, Int>')
      end

      it 'converts nested key/value types' do
        expect(described_class.to_kotlin_type('Dictionary(String, Bool)')).to eq('Map<String, Boolean>')
      end
    end

    context 'with Swift callback syntax conversion' do
      # Note: All function types are converted to optional (?) by default for callbacks
      it 'converts (() -> Void) to (() -> Unit)?' do
        expect(described_class.to_kotlin_type('(() -> Void)')).to eq('(() -> Unit)?')
      end

      it 'converts ((ParamType) -> Void) to ((ParamType) -> Unit)?' do
        expect(described_class.to_kotlin_type('((String) -> Void)')).to eq('((String) -> Unit)?')
        expect(described_class.to_kotlin_type('((ItemData) -> Void)')).to eq('((ItemData) -> Unit)?')
      end

      it 'converts ((Param1, Param2) -> Void) to ((Param1, Param2) -> Unit)?' do
        expect(described_class.to_kotlin_type('((Int, String) -> Void)')).to eq('((Int, String) -> Unit)?')
      end

      it 'converts optional callback (() -> Void)? to (() -> Unit)?' do
        expect(described_class.to_kotlin_type('(() -> Void)?')).to eq('(() -> Unit)?')
      end

      it 'converts optional callback with params ((ParamType) -> Void)? to ((ParamType) -> Unit)?' do
        expect(described_class.to_kotlin_type('((String) -> Void)?')).to eq('((String) -> Unit)?')
      end

      it 'converts parameter types in callbacks' do
        expect(described_class.to_kotlin_type('((Bool) -> Void)')).to eq('((Boolean) -> Unit)?')
      end
    end

    context 'with Swift simple callback syntax (no outer parens)' do
      it 'converts () -> Void to (() -> Unit)? (optional)' do
        expect(described_class.to_kotlin_type('() -> Void')).to eq('(() -> Unit)?')
      end

      it 'converts (ParamType) -> Void to ((ParamType) -> Unit)? (optional)' do
        expect(described_class.to_kotlin_type('(String) -> Void')).to eq('((String) -> Unit)?')
      end
    end

    context 'with complex function types' do
      it 'converts ((Image) -> Color) with mode-specific type mapping' do
        result = described_class.to_kotlin_type('((Image) -> Color)', 'compose')
        expect(result).to eq('((Painter) -> Color)?')
      end

      it 'converts ((String, Int) -> Bool)?' do
        result = described_class.to_kotlin_type('((String, Int) -> Bool)?')
        expect(result).to eq('((String, Int) -> Boolean)?')
      end

      it 'converts function with nested function parameter' do
        result = described_class.to_kotlin_type('((Int) -> String, Bool) -> Void')
        expect(result).to include('-> Unit)?')
      end
    end

    context 'with optional parameter types in functions' do
      it 'converts (String?) -> Int' do
        result = described_class.to_kotlin_type('(String?) -> Int')
        expect(result).to eq('((String?) -> Int)?')
      end
    end

    context 'with Swift type mappings' do
      it 'converts Void to Unit' do
        expect(described_class.to_kotlin_type('Void')).to eq('Unit')
        expect(described_class.to_kotlin_type('void')).to eq('Unit')
      end
    end

    context 'with nil or empty types' do
      it 'returns nil for nil input' do
        expect(described_class.to_kotlin_type(nil)).to be_nil
      end

      it 'returns empty string for empty input' do
        expect(described_class.to_kotlin_type('')).to eq('')
      end
    end
  end

  describe '.extract_platform_value' do
    context 'with simple value' do
      it 'returns the value as-is' do
        expect(described_class.extract_platform_value('String')).to eq('String')
        expect(described_class.extract_platform_value(123)).to eq(123)
      end
    end

    context 'with language-only hash' do
      it 'extracts kotlin value' do
        value = { 'swift' => 'Int', 'kotlin' => 'Int', 'react' => 'number' }
        expect(described_class.extract_platform_value(value)).to eq('Int')
      end

      it 'returns original hash if no kotlin key' do
        value = { 'swift' => 'Int', 'react' => 'number' }
        expect(described_class.extract_platform_value(value)).to eq(value)
      end
    end

    context 'with language + mode hash' do
      let(:value) do
        {
          'swift' => { 'swiftui' => 'Color', 'uikit' => 'UIColor' },
          'kotlin' => { 'compose' => 'Color', 'xml' => 'Int' },
          'react' => { 'react' => 'string' }
        }
      end

      it 'extracts compose value when mode is compose' do
        expect(described_class.extract_platform_value(value, 'compose')).to eq('Color')
      end

      it 'extracts xml value when mode is xml' do
        expect(described_class.extract_platform_value(value, 'xml')).to eq('Int')
      end

      it 'falls back to first available mode if specified mode not found' do
        value_missing_mode = {
          'kotlin' => { 'compose' => 'Color' }
        }
        expect(described_class.extract_platform_value(value_missing_mode, 'xml')).to eq('Color')
      end
    end
  end

  describe '.normalize_data_property' do
    context 'with simple class' do
      it 'normalizes String class' do
        prop = { 'name' => 'title', 'class' => 'String', 'defaultValue' => 'Hello' }
        result = described_class.normalize_data_property(prop, 'compose')

        expect(result['name']).to eq('title')
        expect(result['class']).to eq('String')
        expect(result['defaultValue']).to eq('Hello')
      end

      it 'converts Bool to Boolean' do
        prop = { 'name' => 'isEnabled', 'class' => 'Bool', 'defaultValue' => true }
        result = described_class.normalize_data_property(prop, 'compose')

        expect(result['class']).to eq('Boolean')
      end
    end

    context 'with mode-specific class' do
      it 'converts Color to Color for compose' do
        prop = { 'name' => 'bgColor', 'class' => 'Color', 'defaultValue' => 'Color.Blue' }
        result = described_class.normalize_data_property(prop, 'compose')

        expect(result['class']).to eq('Color')
      end

      it 'converts Color to Int for xml' do
        prop = { 'name' => 'bgColor', 'class' => 'Color', 'defaultValue' => '0xFF0000FF' }
        result = described_class.normalize_data_property(prop, 'xml')

        expect(result['class']).to eq('Int')
      end
    end

    context 'with platform-specific hash values' do
      it 'extracts class and defaultValue for kotlin/compose' do
        prop = {
          'name' => 'backgroundColor',
          'class' => {
            'swift' => { 'swiftui' => 'Color', 'uikit' => 'UIColor' },
            'kotlin' => { 'compose' => 'Color', 'xml' => 'Int' }
          },
          'defaultValue' => {
            'swift' => { 'swiftui' => 'Color.blue', 'uikit' => 'UIColor.blue' },
            'kotlin' => { 'compose' => 'Color.Blue', 'xml' => '0xFF0000FF' }
          }
        }

        result = described_class.normalize_data_property(prop, 'compose')
        expect(result['class']).to eq('Color')
        expect(result['defaultValue']).to eq('Color.Blue')
      end

      it 'extracts class and defaultValue for kotlin/xml' do
        prop = {
          'name' => 'backgroundColor',
          'class' => {
            'swift' => { 'swiftui' => 'Color', 'uikit' => 'UIColor' },
            'kotlin' => { 'compose' => 'Color', 'xml' => 'Int' }
          },
          'defaultValue' => {
            'swift' => { 'swiftui' => 'Color.blue', 'uikit' => 'UIColor.blue' },
            'kotlin' => { 'compose' => 'Color.Blue', 'xml' => '0xFF0000FF' }
          }
        }

        result = described_class.normalize_data_property(prop, 'xml')
        expect(result['class']).to eq('Int')
        expect(result['defaultValue']).to eq('0xFF0000FF')
      end
    end

    context 'with unknown types' do
      it 'preserves unknown types as-is' do
        prop = { 'name' => 'dataSource', 'class' => 'CollectionDataSource' }
        result = described_class.normalize_data_property(prop, 'compose')

        expect(result['class']).to eq('CollectionDataSource')
      end
    end
  end

  describe '.normalize_data_properties' do
    it 'normalizes array of properties' do
      props = [
        { 'name' => 'title', 'class' => 'String' },
        { 'name' => 'count', 'class' => 'Int' },
        { 'name' => 'bgColor', 'class' => 'Color' }
      ]

      result = described_class.normalize_data_properties(props, 'xml')

      expect(result[0]['class']).to eq('String')
      expect(result[1]['class']).to eq('Int')
      expect(result[2]['class']).to eq('Int')  # Color -> Int for xml
    end

    it 'returns empty array for nil input' do
      expect(described_class.normalize_data_properties(nil)).to eq([])
    end

    it 'returns empty array for non-array input' do
      expect(described_class.normalize_data_properties('not an array')).to eq([])
    end
  end

  describe '.primitive?' do
    it 'returns true for primitive types' do
      expect(described_class.primitive?('String')).to be true
      expect(described_class.primitive?('Int')).to be true
      expect(described_class.primitive?('Boolean')).to be true
      expect(described_class.primitive?('Double')).to be true
    end

    it 'returns false for non-primitive types' do
      expect(described_class.primitive?('Color')).to be false
      expect(described_class.primitive?('CustomType')).to be false
    end

    it 'returns false for nil or empty' do
      expect(described_class.primitive?(nil)).to be false
      expect(described_class.primitive?('')).to be false
    end
  end

  describe '.default_value' do
    it 'returns correct defaults for Kotlin types' do
      expect(described_class.default_value('String')).to eq('""')
      expect(described_class.default_value('Int')).to eq('0')
      expect(described_class.default_value('Double')).to eq('0.0')
      expect(described_class.default_value('Float')).to eq('0f')
      expect(described_class.default_value('Boolean')).to eq('false')
      expect(described_class.default_value('Color')).to eq('Color.Unspecified')
      expect(described_class.default_value('CollectionDataSource')).to eq('CollectionDataSource()')
    end

    it 'returns null for unknown types' do
      expect(described_class.default_value('CustomType')).to eq('null')
    end
  end

  describe 'CollectionDataSource type' do
    it 'is recognized as a known type' do
      expect(described_class.to_kotlin_type('CollectionDataSource')).to eq('CollectionDataSource')
    end

    it 'has correct default value' do
      expect(described_class.default_value('CollectionDataSource')).to eq('CollectionDataSource()')
    end

    it 'is in TYPE_MAPPING (primitive? returns true)' do
      expect(described_class.primitive?('CollectionDataSource')).to be true
    end
  end

  describe '.load_type_mapping' do
    before(:each) do
      described_class.clear_type_mapping_cache
    end

    it 'loads type_mapping.json' do
      mapping = described_class.load_type_mapping
      expect(mapping).to be_a(Hash)
      expect(mapping).to have_key('types')
      expect(mapping).to have_key('events')
      expect(mapping).to have_key('defaults')
    end

    it 'caches the loaded mapping' do
      first_load = described_class.load_type_mapping
      second_load = described_class.load_type_mapping
      expect(first_load).to equal(second_load)
    end
  end

  describe '.get_type_mapping' do
    before(:each) do
      described_class.clear_type_mapping_cache
    end

    it 'returns mapped type for known types' do
      expect(described_class.get_type_mapping('String')).to eq('String')
      expect(described_class.get_type_mapping('Int')).to eq('Int')
      expect(described_class.get_type_mapping('Bool')).to eq('Boolean')
    end

    it 'returns mode-specific type for Color' do
      expect(described_class.get_type_mapping('Color', 'compose')).to eq('Color')
      expect(described_class.get_type_mapping('Color', 'xml')).to eq('Int')
    end

    it 'returns nil for unknown types' do
      expect(described_class.get_type_mapping('UnknownType')).to be_nil
    end
  end

  describe '.get_event_type' do
    before(:each) do
      described_class.clear_type_mapping_cache
    end

    context 'with Button onClick' do
      it 'returns View for xml mode' do
        result = described_class.get_event_type('Button', 'onClick', 'xml')
        expect(result).to eq('View')
      end

      it 'returns [String, Unit] tuple for compose mode' do
        result = described_class.get_event_type('Button', 'onClick', 'compose')
        expect(result).to eq(['String', 'Unit'])
      end
    end

    context 'with Switch onValueChange' do
      it 'returns CompoundButton for xml mode' do
        result = described_class.get_event_type('Switch', 'onValueChange', 'xml')
        expect(result).to eq('CompoundButton')
      end

      it 'returns [String, Boolean] tuple for compose mode' do
        result = described_class.get_event_type('Switch', 'onValueChange', 'compose')
        expect(result).to eq(['String', 'Boolean'])
      end
    end

    context 'with Toggle onValueChange' do
      it 'returns [String, Boolean] tuple for compose mode' do
        result = described_class.get_event_type('Toggle', 'onValueChange', 'compose')
        expect(result).to eq(['String', 'Boolean'])
      end
    end

    context 'with Slider onValueChange' do
      it 'returns [String, Float] tuple for compose mode' do
        result = described_class.get_event_type('Slider', 'onValueChange', 'compose')
        expect(result).to eq(['String', 'Float'])
      end
    end

    context 'with TextField onTextChange' do
      it 'returns [String, String] tuple for compose mode' do
        result = described_class.get_event_type('TextField', 'onTextChange', 'compose')
        expect(result).to eq(['String', 'String'])
      end
    end

    context 'with SelectBox onValueChange' do
      it 'returns [String, String] tuple for compose mode' do
        result = described_class.get_event_type('SelectBox', 'onValueChange', 'compose')
        expect(result).to eq(['String', 'String'])
      end
    end

    context 'with CheckBox onValueChange' do
      it 'returns [String, Boolean] tuple for compose mode' do
        result = described_class.get_event_type('CheckBox', 'onValueChange', 'compose')
        expect(result).to eq(['String', 'Boolean'])
      end
    end

    context 'with Segment onValueChange' do
      it 'returns [String, Int] tuple for compose mode' do
        result = described_class.get_event_type('Segment', 'onValueChange', 'compose')
        expect(result).to eq(['String', 'Int'])
      end
    end

    it 'returns nil for unknown component' do
      result = described_class.get_event_type('UnknownComponent', 'onClick', 'compose')
      expect(result).to be_nil
    end

    it 'returns nil for unknown attribute' do
      result = described_class.get_event_type('Button', 'unknownEvent', 'compose')
      expect(result).to be_nil
    end
  end

  describe '.get_default_value from type_mapping' do
    before(:each) do
      described_class.clear_type_mapping_cache
    end

    it 'returns default value for known Kotlin types from type_mapping.json' do
      expect(described_class.get_default_value('String')).to eq('""')
      expect(described_class.get_default_value('Int')).to eq('0')
      expect(described_class.get_default_value('Boolean')).to eq('false')
      expect(described_class.get_default_value('Float')).to eq('0f')
      expect(described_class.get_default_value('Color')).to eq('Color.Unspecified')
    end

    it 'returns null for unknown types' do
      expect(described_class.get_default_value('UnknownType')).to eq('null')
    end
  end
end
