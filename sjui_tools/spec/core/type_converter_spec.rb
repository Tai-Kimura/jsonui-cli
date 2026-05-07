# frozen_string_literal: true

require 'core/type_converter'

RSpec.describe SjuiTools::Core::TypeConverter do
  describe '.to_swift_type' do
    context 'with common types' do
      it 'converts String types' do
        expect(described_class.to_swift_type('String')).to eq('String')
        expect(described_class.to_swift_type('string')).to eq('String')
      end

      it 'converts Int types' do
        expect(described_class.to_swift_type('Int')).to eq('Int')
        expect(described_class.to_swift_type('int')).to eq('Int')
        expect(described_class.to_swift_type('Integer')).to eq('Int')
        expect(described_class.to_swift_type('integer')).to eq('Int')
      end

      it 'converts Double types' do
        expect(described_class.to_swift_type('Double')).to eq('Double')
        expect(described_class.to_swift_type('double')).to eq('Double')
      end

      it 'converts Float types' do
        expect(described_class.to_swift_type('Float')).to eq('Float')
        expect(described_class.to_swift_type('float')).to eq('Float')
      end

      it 'converts Bool types' do
        expect(described_class.to_swift_type('Bool')).to eq('Bool')
        expect(described_class.to_swift_type('bool')).to eq('Bool')
        expect(described_class.to_swift_type('Boolean')).to eq('Bool')
        expect(described_class.to_swift_type('boolean')).to eq('Bool')
      end

      it 'converts CGFloat type' do
        expect(described_class.to_swift_type('CGFloat')).to eq('CGFloat')
      end

      it 'converts EdgeInsets type' do
        expect(described_class.to_swift_type('EdgeInsets')).to eq('EdgeInsets')
      end
    end

    context 'with mode-specific types' do
      it 'converts Color to Color for swiftui mode' do
        expect(described_class.to_swift_type('Color', 'swiftui')).to eq('Color')
        expect(described_class.to_swift_type('color', 'swiftui')).to eq('Color')
      end

      it 'converts Color to UIColor for uikit mode' do
        expect(described_class.to_swift_type('Color', 'uikit')).to eq('UIColor')
        expect(described_class.to_swift_type('color', 'uikit')).to eq('UIColor')
      end

      it 'defaults to swiftui when no mode specified for Color' do
        expect(described_class.to_swift_type('Color')).to eq('Color')
      end

      # SwiftUI mode stores visibility as a String (for VisibilityWrapper)
      # while UIKit mode uses the SJUIView.Visibility enum.
      it 'converts Visibility to String for swiftui mode' do
        expect(described_class.to_swift_type('Visibility', 'swiftui')).to eq('String')
        expect(described_class.to_swift_type('visibility', 'swiftui')).to eq('String')
      end

      it 'converts Visibility to SJUIView.Visibility for uikit mode' do
        expect(described_class.to_swift_type('Visibility', 'uikit')).to eq('SJUIView.Visibility')
        expect(described_class.to_swift_type('visibility', 'uikit')).to eq('SJUIView.Visibility')
      end
    end

    context 'with unknown types' do
      it 'returns the type as-is' do
        expect(described_class.to_swift_type('CustomType')).to eq('CustomType')
        expect(described_class.to_swift_type('MyViewModel')).to eq('MyViewModel')
      end
    end

    context 'with Array syntax' do
      it 'converts Array(ElementType) to [ElementType]' do
        expect(described_class.to_swift_type('Array(String)')).to eq('[String]')
        expect(described_class.to_swift_type('Array(Int)')).to eq('[Int]')
        expect(described_class.to_swift_type('Array(ItemData)')).to eq('[ItemData]')
      end

      it 'converts nested element types' do
        expect(described_class.to_swift_type('Array(Boolean)')).to eq('[Bool]')
      end
    end

    context 'with Dictionary syntax' do
      it 'converts Dictionary(KeyType, ValueType) to [KeyType: ValueType]' do
        expect(described_class.to_swift_type('Dictionary(String, Any)')).to eq('[String: Any]')
        expect(described_class.to_swift_type('Dictionary(String, Int)')).to eq('[String: Int]')
      end

      it 'converts nested key/value types' do
        expect(described_class.to_swift_type('Dictionary(String, Boolean)')).to eq('[String: Bool]')
      end
    end

    context 'with Kotlin callback syntax conversion' do
      it 'converts () -> Unit to (() -> Void)? (optional)' do
        expect(described_class.to_swift_type('() -> Unit')).to eq('(() -> Void)?')
      end

      it 'converts (ParamType) -> Unit to ((ParamType) -> Void)? (optional)' do
        expect(described_class.to_swift_type('(String) -> Unit')).to eq('((String) -> Void)?')
        expect(described_class.to_swift_type('(ItemData) -> Unit')).to eq('((ItemData) -> Void)?')
      end

      it 'converts (Param1, Param2) -> Unit to ((Param1, Param2) -> Void)? (optional)' do
        expect(described_class.to_swift_type('(Int, String) -> Unit')).to eq('((Int, String) -> Void)?')
      end

      it 'converts optional callback (() -> Unit)? to (() -> Void)?' do
        expect(described_class.to_swift_type('(() -> Unit)?')).to eq('(() -> Void)?')
      end

      it 'converts optional callback with params ((ParamType) -> Unit)? to ((ParamType) -> Void)?' do
        expect(described_class.to_swift_type('((String) -> Unit)?')).to eq('((String) -> Void)?')
      end

      it 'converts parameter types in callbacks' do
        expect(described_class.to_swift_type('(Boolean) -> Unit')).to eq('((Bool) -> Void)?')
      end
    end

    context 'with Swift simple callback syntax (no outer parens)' do
      it 'converts () -> Void to (() -> Void)? (optional)' do
        expect(described_class.to_swift_type('() -> Void')).to eq('(() -> Void)?')
      end

      it 'converts (ParamType) -> Void to ((ParamType) -> Void)? (optional)' do
        expect(described_class.to_swift_type('(String) -> Void')).to eq('((String) -> Void)?')
      end
    end

    context 'with complex function types' do
      it 'converts ((Image) -> Color) with mode-specific type mapping' do
        result = described_class.to_swift_type('((Image) -> Color)', 'swiftui')
        expect(result).to eq('((String) -> Color)?')
      end

      it 'converts ((String, Int) -> Bool)?' do
        result = described_class.to_swift_type('((String, Int) -> Bool)?')
        expect(result).to eq('((String, Int) -> Bool)?')
      end

      it 'converts function with nested function parameter' do
        result = described_class.to_swift_type('((Int) -> String, Bool) -> Void')
        expect(result).to include('-> Void)?')
      end
    end

    context 'with optional parameter types in functions' do
      it 'converts (String?) -> Int' do
        result = described_class.to_swift_type('(String?) -> Int')
        expect(result).to eq('((String?) -> Int)?')
      end
    end

    context 'with Kotlin type mappings' do
      it 'converts Unit to Void' do
        expect(described_class.to_swift_type('Unit')).to eq('Void')
        expect(described_class.to_swift_type('unit')).to eq('Void')
      end
    end

    context 'with nil or empty types' do
      it 'returns nil for nil input' do
        expect(described_class.to_swift_type(nil)).to be_nil
      end

      it 'returns empty string for empty input' do
        expect(described_class.to_swift_type('')).to eq('')
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
      it 'extracts swift value' do
        value = { 'swift' => 'Int', 'kotlin' => 'Int', 'react' => 'number' }
        expect(described_class.extract_platform_value(value)).to eq('Int')
      end

      it 'returns original hash if no swift key' do
        value = { 'kotlin' => 'Int', 'react' => 'number' }
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

      it 'extracts swiftui value when mode is swiftui' do
        expect(described_class.extract_platform_value(value, 'swiftui')).to eq('Color')
      end

      it 'extracts uikit value when mode is uikit' do
        expect(described_class.extract_platform_value(value, 'uikit')).to eq('UIColor')
      end

      it 'falls back to first available mode if specified mode not found' do
        value_missing_mode = {
          'swift' => { 'swiftui' => 'Color' }
        }
        expect(described_class.extract_platform_value(value_missing_mode, 'uikit')).to eq('Color')
      end
    end
  end

  describe '.normalize_data_property' do
    context 'with simple class' do
      it 'normalizes String class' do
        prop = { 'name' => 'title', 'class' => 'String', 'defaultValue' => 'Hello' }
        result = described_class.normalize_data_property(prop, 'swiftui')

        expect(result['name']).to eq('title')
        expect(result['class']).to eq('String')
        expect(result['defaultValue']).to eq('Hello')
      end

      it 'converts Bool to Bool' do
        prop = { 'name' => 'isEnabled', 'class' => 'Boolean', 'defaultValue' => true }
        result = described_class.normalize_data_property(prop, 'swiftui')

        expect(result['class']).to eq('Bool')
      end
    end

    context 'with mode-specific class' do
      it 'converts Color to Color for swiftui' do
        prop = { 'name' => 'bgColor', 'class' => 'Color', 'defaultValue' => '.blue' }
        result = described_class.normalize_data_property(prop, 'swiftui')

        expect(result['class']).to eq('Color')
      end

      it 'converts Color to UIColor for uikit' do
        prop = { 'name' => 'bgColor', 'class' => 'Color', 'defaultValue' => '.blue' }
        result = described_class.normalize_data_property(prop, 'uikit')

        expect(result['class']).to eq('UIColor')
      end
    end

    context 'with platform-specific hash values' do
      it 'extracts class and defaultValue for swift/swiftui' do
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

        result = described_class.normalize_data_property(prop, 'swiftui')
        expect(result['class']).to eq('Color')
        expect(result['defaultValue']).to eq('Color.blue')
      end

      it 'extracts class and defaultValue for swift/uikit' do
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

        result = described_class.normalize_data_property(prop, 'uikit')
        expect(result['class']).to eq('UIColor')
        expect(result['defaultValue']).to eq('UIColor.blue')
      end
    end

    context 'with unknown types' do
      it 'preserves unknown types as-is' do
        prop = { 'name' => 'dataSource', 'class' => 'CollectionDataSource' }
        result = described_class.normalize_data_property(prop, 'swiftui')

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

      result = described_class.normalize_data_properties(props, 'uikit')

      expect(result[0]['class']).to eq('String')
      expect(result[1]['class']).to eq('Int')
      expect(result[2]['class']).to eq('UIColor')
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
      expect(described_class.primitive?('Bool')).to be true
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
    it 'returns correct defaults for Swift types' do
      expect(described_class.default_value('String')).to eq('""')
      expect(described_class.default_value('Int')).to eq('0')
      expect(described_class.default_value('Double')).to eq('0.0')
      expect(described_class.default_value('Bool')).to eq('false')
      expect(described_class.default_value('Color')).to eq('.clear')
      expect(described_class.default_value('UIColor')).to eq('.clear')
      expect(described_class.default_value('CollectionDataSource')).to eq('CollectionDataSource()')
      expect(described_class.default_value('Visibility')).to eq('.visible')
      expect(described_class.default_value('SJUIView.Visibility')).to eq('.visible')
    end

    it 'returns nil for unknown types' do
      expect(described_class.default_value('CustomType')).to eq('nil')
    end
  end

  describe '.convert_default_value' do
    context 'with Visibility type' do
      it 'converts visible to .visible' do
        expect(described_class.convert_default_value('visible', 'Visibility')).to eq('.visible')
      end

      it 'converts gone to .gone' do
        expect(described_class.convert_default_value('gone', 'Visibility')).to eq('.gone')
      end

      it 'converts invisible to .invisible' do
        expect(described_class.convert_default_value('invisible', 'Visibility')).to eq('.invisible')
      end

      it 'handles case-insensitive values' do
        expect(described_class.convert_default_value('VISIBLE', 'Visibility')).to eq('.visible')
        expect(described_class.convert_default_value('Gone', 'Visibility')).to eq('.gone')
      end

      it 'preserves already formatted values' do
        expect(described_class.convert_default_value('.visible', 'Visibility')).to eq('.visible')
      end
    end
  end

  describe 'CollectionDataSource type' do
    it 'converts to CollectionDataSource for swiftui mode' do
      expect(described_class.to_swift_type('CollectionDataSource', 'swiftui')).to eq('CollectionDataSource')
    end

    it 'converts to UIKitCollectionDataSource for uikit mode' do
      expect(described_class.to_swift_type('CollectionDataSource', 'uikit')).to eq('UIKitCollectionDataSource')
    end

    it 'defaults to swiftui when no mode specified' do
      expect(described_class.to_swift_type('CollectionDataSource')).to eq('CollectionDataSource')
    end

    it 'has correct default value for CollectionDataSource' do
      expect(described_class.default_value('CollectionDataSource')).to eq('CollectionDataSource()')
    end

    it 'has correct default value for UIKitCollectionDataSource' do
      expect(described_class.default_value('UIKitCollectionDataSource')).to eq('UIKitCollectionDataSource()')
    end

    it 'is in MODE_TYPE_MAPPING (not primitive)' do
      expect(described_class.primitive?('CollectionDataSource')).to be false
    end
  end

  describe '.convert_default_value' do
    # Set up mock colors data to avoid warnings during tests
    before do
      described_class.colors_data = {
        'white' => '#FFFFFF',
        'medium_gray' => '#666666',
        'medium_blue' => '#6200EE',
        'deep_gray' => '#1A1410'
      }
    end

    after do
      described_class.clear_colors_cache
    end

    context 'with Color type' do
      it 'converts hex color using UIColor.colorWithHexString for swiftui' do
        result = described_class.convert_default_value('#FF0000', 'Color', 'swiftui')
        expect(result).to eq('Color(uiColor: UIColor.colorWithHexString("#FF0000") ?? .clear)')
      end

      it 'converts hex color using UIColor.colorWithHexString for uikit' do
        result = described_class.convert_default_value('#FF0000', 'Color', 'uikit')
        expect(result).to eq('UIColor.colorWithHexString("#FF0000") ?? .clear')
      end

      it 'converts color name to ColorManager accessor for swiftui' do
        result = described_class.convert_default_value('medium_gray', 'Color', 'swiftui')
        expect(result).to eq('ColorManager.swiftui.mediumGray ?? .clear')
      end

      it 'converts color name to ColorManager accessor for uikit' do
        result = described_class.convert_default_value('medium_gray', 'Color', 'uikit')
        expect(result).to eq('ColorManager.uikit.mediumGray ?? .clear')
      end

      it 'converts simple color name without underscore' do
        result = described_class.convert_default_value('white', 'Color', 'swiftui')
        expect(result).to eq('ColorManager.swiftui.white ?? .clear')
      end

      it 'preserves already formatted color values' do
        result = described_class.convert_default_value('.blue', 'Color', 'swiftui')
        expect(result).to eq('.blue')

        result = described_class.convert_default_value('Color.red', 'Color', 'swiftui')
        expect(result).to eq('Color.red')

        result = described_class.convert_default_value('UIColor.blue', 'Color', 'uikit')
        expect(result).to eq('UIColor.blue')
      end

      it 'handles optional Color type' do
        result = described_class.convert_default_value('#00FF00', 'Color?', 'swiftui')
        expect(result).to eq('Color(uiColor: UIColor.colorWithHexString("#00FF00") ?? .clear)')
      end
    end

    context 'with Image type' do
      it 'converts image name to quoted string for swiftui' do
        result = described_class.convert_default_value('icon_home', 'Image', 'swiftui')
        expect(result).to eq('"icon_home"')
      end

      it 'converts image name to UIImage(named:) for uikit' do
        result = described_class.convert_default_value('icon_home', 'Image', 'uikit')
        expect(result).to eq('UIImage(named: "icon_home")')
      end

      it 'preserves already formatted image values' do
        result = described_class.convert_default_value('"my_image"', 'Image', 'swiftui')
        expect(result).to eq('"my_image"')

        result = described_class.convert_default_value('UIImage(named: "test")', 'Image', 'uikit')
        expect(result).to eq('UIImage(named: "test")')
      end
    end

    context 'with other types' do
      it 'returns value unchanged for String type' do
        result = described_class.convert_default_value('hello', 'String', 'swiftui')
        expect(result).to eq('hello')
      end

      it 'returns value unchanged for Int type' do
        result = described_class.convert_default_value('42', 'Int', 'swiftui')
        expect(result).to eq('42')
      end

      it 'returns value unchanged for nil raw_class' do
        result = described_class.convert_default_value('test', nil, 'swiftui')
        expect(result).to eq('test')
      end
    end
  end

  describe '.snake_to_camel' do
    it 'converts snake_case to camelCase' do
      expect(described_class.snake_to_camel('medium_gray')).to eq('mediumGray')
      expect(described_class.snake_to_camel('deep_blue_2')).to eq('deepBlue2')
      expect(described_class.snake_to_camel('light_pink')).to eq('lightPink')
    end

    it 'returns unchanged for simple names without underscore' do
      expect(described_class.snake_to_camel('white')).to eq('white')
      expect(described_class.snake_to_camel('black')).to eq('black')
    end

    it 'handles non-string input' do
      expect(described_class.snake_to_camel(123)).to eq(123)
      expect(described_class.snake_to_camel(nil)).to be_nil
    end
  end

  describe 'color validation' do
    before do
      described_class.clear_colors_cache
    end

    after do
      described_class.clear_colors_cache
    end

    describe '.load_colors_json' do
      it 'loads colors from specified path' do
        # Create a temporary colors.json file
        require 'tempfile'
        require 'json'

        temp_file = Tempfile.new(['colors', '.json'])
        temp_file.write(JSON.generate({ 'test_color' => '#FF0000', 'another_color' => '#00FF00' }))
        temp_file.close

        result = described_class.load_colors_json(temp_file.path)
        expect(result).to eq({ 'test_color' => '#FF0000', 'another_color' => '#00FF00' })

        temp_file.unlink
      end

      it 'returns empty hash for non-existent file' do
        result = described_class.load_colors_json('/non/existent/path.json')
        expect(result).to eq({})
      end
    end

    describe '.color_exists?' do
      before do
        # Set up mock colors data
        described_class.colors_data = { 'white' => '#FFFFFF', 'medium_gray' => '#666666' }
      end

      it 'returns true for existing color' do
        expect(described_class.color_exists?('white')).to be true
        expect(described_class.color_exists?('medium_gray')).to be true
      end

      it 'returns false for non-existing color' do
        expect(described_class.color_exists?('nonexistent')).to be false
      end
    end

    describe '.convert_color_default_value with validation' do
      before do
        described_class.colors_data = { 'white' => '#FFFFFF', 'medium_gray' => '#666666' }
      end

      it 'does not warn for existing color' do
        expect { described_class.convert_color_default_value('white', 'swiftui') }
          .not_to output.to_stderr
      end

      it 'warns for non-existing color' do
        expect { described_class.convert_color_default_value('nonexistent_color', 'swiftui') }
          .to output(/Warning: Color 'nonexistent_color' is not defined in colors.json/).to_stderr
      end

      it 'still generates correct code even for non-existing color' do
        result = nil
        expect {
          result = described_class.convert_color_default_value('nonexistent_color', 'swiftui')
        }.to output.to_stderr

        expect(result).to eq('ColorManager.swiftui.nonexistentColor ?? .clear')
      end
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
      expect(described_class.get_type_mapping('Bool')).to eq('Bool')
    end

    it 'returns mode-specific type for Color' do
      expect(described_class.get_type_mapping('Color', 'swiftui')).to eq('Color')
      expect(described_class.get_type_mapping('Color', 'uikit')).to eq('UIColor')
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
      it 'returns UITapGestureRecognizer for uikit mode' do
        result = described_class.get_event_type('Button', 'onClick', 'uikit')
        expect(result).to eq('UITapGestureRecognizer')
      end

      it 'returns [String, Void] tuple for swiftui mode' do
        result = described_class.get_event_type('Button', 'onClick', 'swiftui')
        expect(result).to eq(['String', 'Void'])
      end
    end

    context 'with Switch onValueChange' do
      it 'returns UISwitch for uikit mode' do
        result = described_class.get_event_type('Switch', 'onValueChange', 'uikit')
        expect(result).to eq('UISwitch')
      end

      it 'returns [String, Bool] tuple for swiftui mode' do
        result = described_class.get_event_type('Switch', 'onValueChange', 'swiftui')
        expect(result).to eq(['String', 'Bool'])
      end
    end

    context 'with Toggle onValueChange' do
      it 'returns [String, Bool] tuple for swiftui mode' do
        result = described_class.get_event_type('Toggle', 'onValueChange', 'swiftui')
        expect(result).to eq(['String', 'Bool'])
      end
    end

    context 'with Slider onValueChange' do
      it 'returns [String, Float] tuple for swiftui mode' do
        result = described_class.get_event_type('Slider', 'onValueChange', 'swiftui')
        expect(result).to eq(['String', 'Float'])
      end
    end

    context 'with TextField onTextChange' do
      it 'returns [String, String] tuple for swiftui mode' do
        result = described_class.get_event_type('TextField', 'onTextChange', 'swiftui')
        expect(result).to eq(['String', 'String'])
      end
    end

    context 'with SelectBox onValueChange' do
      it 'returns [String, String] tuple for swiftui mode' do
        result = described_class.get_event_type('SelectBox', 'onValueChange', 'swiftui')
        expect(result).to eq(['String', 'String'])
      end
    end

    context 'with CheckBox onValueChange' do
      it 'returns [String, Bool] tuple for swiftui mode' do
        result = described_class.get_event_type('CheckBox', 'onValueChange', 'swiftui')
        expect(result).to eq(['String', 'Bool'])
      end
    end

    context 'with Segment onValueChange' do
      it 'returns [String, Int] tuple for swiftui mode' do
        result = described_class.get_event_type('Segment', 'onValueChange', 'swiftui')
        expect(result).to eq(['String', 'Int'])
      end
    end

    it 'returns nil for unknown component' do
      result = described_class.get_event_type('UnknownComponent', 'onClick', 'swiftui')
      expect(result).to be_nil
    end

    it 'returns nil for unknown attribute' do
      result = described_class.get_event_type('Button', 'unknownEvent', 'swiftui')
      expect(result).to be_nil
    end
  end

  describe '.get_default_value' do
    before(:each) do
      described_class.clear_type_mapping_cache
    end

    it 'returns default value for known Swift types from type_mapping.json' do
      expect(described_class.get_default_value('String')).to eq('""')
      expect(described_class.get_default_value('Int')).to eq('0')
      expect(described_class.get_default_value('Bool')).to eq('false')
      expect(described_class.get_default_value('Float')).to eq('0.0')
      expect(described_class.get_default_value('Color')).to eq('.clear')
    end

    it 'returns nil for unknown types' do
      expect(described_class.get_default_value('UnknownType')).to eq('nil')
    end
  end

  describe '.extract_function_parameter_types' do
    it 'extracts single parameter type' do
      expect(described_class.extract_function_parameter_types('((Boolean) -> Void)?')).to eq(['Boolean'])
    end

    it 'extracts multiple parameter types' do
      expect(described_class.extract_function_parameter_types('((Int, String) -> Void)?')).to eq(['Int', 'String'])
    end

    it 'returns empty array for no parameters' do
      expect(described_class.extract_function_parameter_types('(() -> Void)?')).to eq([])
    end

    it 'returns nil for non-function types' do
      expect(described_class.extract_function_parameter_types('String')).to be_nil
    end

    it 'handles Event type parameter' do
      expect(described_class.extract_function_parameter_types('((Event) -> Void)?')).to eq(['Event'])
    end
  end

  describe '.event_handler_mode' do
    it 'returns :value for value types' do
      expect(described_class.event_handler_mode('((Boolean) -> Void)?')).to eq(:value)
      expect(described_class.event_handler_mode('((String) -> Void)?')).to eq(:value)
      expect(described_class.event_handler_mode('((Int) -> Void)?')).to eq(:value)
    end

    it 'returns :event for Event type' do
      expect(described_class.event_handler_mode('((Event) -> Void)?')).to eq(:event)
    end

    it 'returns :none for no parameters' do
      expect(described_class.event_handler_mode('(() -> Void)?')).to eq(:none)
    end
  end

  describe '.expects_value?' do
    it 'returns true for value types' do
      expect(described_class.expects_value?('((Boolean) -> Void)?')).to be true
      expect(described_class.expects_value?('((String) -> Void)?')).to be true
    end

    it 'returns false for Event type' do
      expect(described_class.expects_value?('((Event) -> Void)?')).to be false
    end
  end

  describe '.expects_event?' do
    it 'returns true for Event type' do
      expect(described_class.expects_event?('((Event) -> Void)?')).to be true
    end

    it 'returns false for value types' do
      expect(described_class.expects_event?('((Boolean) -> Void)?')).to be false
    end
  end

  describe '.normalize_data_property with Color/Image defaultValue conversion' do
    # Set up mock colors data to avoid warnings during tests
    before do
      described_class.colors_data = {
        'white' => '#FFFFFF',
        'medium_gray' => '#666666',
        'medium_blue' => '#6200EE',
        'deep_gray' => '#1A1410'
      }
    end

    after do
      described_class.clear_colors_cache
    end

    context 'with Color type and hex defaultValue' do
      it 'converts hex using UIColor.colorWithHexString for swiftui' do
        prop = { 'name' => 'bgColor', 'class' => 'Color', 'defaultValue' => '#FF5733' }
        result = described_class.normalize_data_property(prop, 'swiftui')

        expect(result['class']).to eq('Color')
        expect(result['defaultValue']).to eq('Color(uiColor: UIColor.colorWithHexString("#FF5733") ?? .clear)')
      end

      it 'converts hex using UIColor.colorWithHexString for uikit' do
        prop = { 'name' => 'bgColor', 'class' => 'Color', 'defaultValue' => '#FF5733' }
        result = described_class.normalize_data_property(prop, 'uikit')

        expect(result['class']).to eq('UIColor')
        expect(result['defaultValue']).to eq('UIColor.colorWithHexString("#FF5733") ?? .clear')
      end
    end

    context 'with Color type and color name defaultValue' do
      it 'converts color name to ColorManager accessor for swiftui' do
        prop = { 'name' => 'textColor', 'class' => 'Color', 'defaultValue' => 'medium_blue' }
        result = described_class.normalize_data_property(prop, 'swiftui')

        expect(result['class']).to eq('Color')
        expect(result['defaultValue']).to eq('ColorManager.swiftui.mediumBlue ?? .clear')
      end

      it 'converts color name to ColorManager accessor for uikit' do
        prop = { 'name' => 'textColor', 'class' => 'Color', 'defaultValue' => 'deep_gray' }
        result = described_class.normalize_data_property(prop, 'uikit')

        expect(result['class']).to eq('UIColor')
        expect(result['defaultValue']).to eq('ColorManager.uikit.deepGray ?? .clear')
      end
    end

    context 'with Image type' do
      it 'converts image name to quoted string for swiftui' do
        prop = { 'name' => 'icon', 'class' => 'Image', 'defaultValue' => 'star_icon' }
        result = described_class.normalize_data_property(prop, 'swiftui')

        expect(result['class']).to eq('String')
        expect(result['defaultValue']).to eq('"star_icon"')
      end

      it 'converts image name to UIImage(named:) for uikit' do
        prop = { 'name' => 'icon', 'class' => 'Image', 'defaultValue' => 'star_icon' }
        result = described_class.normalize_data_property(prop, 'uikit')

        expect(result['class']).to eq('UIImage')
        expect(result['defaultValue']).to eq('UIImage(named: "star_icon")')
      end
    end
  end
end
