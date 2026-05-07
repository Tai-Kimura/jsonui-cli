# frozen_string_literal: true

require 'core/attribute_validator'
require 'fileutils'
require 'json'

RSpec.describe SjuiTools::Core::AttributeValidator do
  describe '#initialize' do
    it 'creates validator with default mode :all' do
      validator = described_class.new
      expect(validator.mode).to eq(:all)
    end

    it 'creates validator with specified mode' do
      validator = described_class.new(:swiftui)
      expect(validator.mode).to eq(:swiftui)
    end

    it 'loads attribute definitions' do
      validator = described_class.new
      expect(validator.definitions).to be_a(Hash)
      expect(validator.definitions).to have_key('common')
      expect(validator.definitions).to have_key('Label')
    end
  end

  describe '#validate' do
    subject(:validator) { described_class.new(mode) }
    let(:mode) { :all }

    context 'with valid Label component' do
      let(:component) do
        {
          'type' => 'Label',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => 'Hello World',
          'fontSize' => 16,
          'fontColor' => '#000000'
        }
      end

      it 'returns no warnings' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with unknown attribute' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => 'Hello',
          'unknownAttribute' => 'value'
        }
      end

      it 'returns warning for unknown attribute' do
        validator.validate(component)
        expect(validator.warnings.any? { |w| w.include?("Unknown attribute 'unknownAttribute' for component type 'Label'") }).to be true
      end
    end

    context 'with wrong type' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => 'Hello',
          'fontSize' => 'not a number'
        }
      end

      it 'returns warning for type mismatch' do
        validator.validate(component)
        expect(validator.warnings.first).to include('fontSize')
        expect(validator.warnings.first).to include('number')
      end
    end

    context 'with invalid enum value' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => 'Hello',
          'textAlign' => 'invalid'
        }
      end

      it 'returns warning for invalid enum value' do
        validator.validate(component)
        expect(validator.warnings.first).to include('textAlign')
        expect(validator.warnings.first).to include('invalid')
      end
    end

    context 'with value out of range' do
      let(:component) do
        {
          'type' => 'View',
          'alpha' => 1.5
        }
      end

      it 'returns warning for value greater than max' do
        validator.validate(component)
        expect(validator.warnings.first).to include('alpha')
        expect(validator.warnings.first).to include('greater than maximum')
      end
    end

    # RTL-aware attributes validation
    context 'with RTL-aware padding attributes' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'paddingStart' => 16,
          'paddingEnd' => 24
        }
      end

      it 'returns no warnings for valid paddingStart and paddingEnd' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with RTL-aware margin attributes' do
      let(:component) do
        {
          'type' => 'Label',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => 'Test',
          'startMargin' => 12,
          'endMargin' => 18
        }
      end

      it 'returns no warnings for valid startMargin and endMargin' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with all RTL-aware attributes' do
      let(:component) do
        {
          'type' => 'Button',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => 'Action',
          'paddingStart' => 8,
          'paddingEnd' => 12,
          'startMargin' => 16,
          'endMargin' => 20
        }
      end

      it 'returns no warnings when all RTL attributes are valid' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with invalid paddingStart type' do
      let(:component) do
        {
          'type' => 'View',
          'paddingStart' => 'not a number'
        }
      end

      it 'returns warning for type mismatch' do
        validator.validate(component)
        expect(validator.warnings.first).to include('paddingStart')
        expect(validator.warnings.first).to include('number')
      end
    end

    context 'with invalid endMargin type' do
      let(:component) do
        {
          'type' => 'View',
          'endMargin' => 'invalid'
        }
      end

      it 'returns warning for type mismatch' do
        validator.validate(component)
        expect(validator.warnings.first).to include('endMargin')
        expect(validator.warnings.first).to include('number')
      end
    end

    # NEW TESTS: Enum array validation
    context 'with gravity as array of valid enum values' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'gravity' => ['centerVertical']
        }
      end

      it 'returns no warnings for valid enum array' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with gravity as array of multiple valid enum values' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'gravity' => ['centerVertical', 'left']
        }
      end

      it 'returns no warnings for valid multiple enum values' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with gravity as array with invalid enum values' do
      let(:component) do
        {
          'type' => 'View',
          'gravity' => ['invalid']
        }
      end

      it 'returns warning for invalid enum value in array' do
        validator.validate(component)
        expect(validator.warnings.first).to include('gravity')
        expect(validator.warnings.first).to include('invalid')
        expect(validator.warnings.first).to include('Valid values')
      end
    end

    context 'with gravity as array with mixed valid and invalid values' do
      let(:component) do
        {
          'type' => 'View',
          'gravity' => ['centerVertical', 'invalidValue']
        }
      end

      it 'returns warning only for invalid values' do
        validator.validate(component)
        expect(validator.warnings.first).to include('gravity')
        expect(validator.warnings.first).to include('invalidValue')
        # The warning message also includes valid values list which contains centerVertical
        # but the actual invalid value in the warning is only 'invalidValue'
      end
    end

    # NEW TESTS: Binding with enum
    context 'with visibility as binding expression' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'visibility' => '@{isVisible}'
        }
      end

      it 'returns no warnings for binding in enum attribute' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with visibility as valid enum value' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'visibility' => 'visible'
        }
      end

      it 'returns no warnings for valid enum value' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with visibility as invalid enum value' do
      let(:component) do
        {
          'type' => 'View',
          'visibility' => 'invalid'
        }
      end

      it 'returns warning for invalid enum value' do
        validator.validate(component)
        expect(validator.warnings.first).to include('visibility')
        expect(validator.warnings.first).to include('invalid')
      end
    end

    # NEW TESTS: Enum in type definition (width/height)
    context 'with width as matchParent string' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 'wrapContent'
        }
      end

      it 'returns no warnings for valid enum string in type definition' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with width as wrapContent string' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 'wrapContent'
        }
      end

      it 'returns no warnings for valid enum string' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with width as number' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 100,
          'height' => 'wrapContent'
        }
      end

      it 'returns no warnings for number width' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with width as binding' do
      let(:component) do
        {
          'type' => 'View',
          'width' => '@{dynamicWidth}',
          'height' => 'wrapContent'
        }
      end

      it 'returns no warnings for binding width' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with width as invalid string (not in enum)' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'invalid',
          'height' => 'wrapContent'
        }
      end

      it 'returns warning for invalid enum string' do
        validator.validate(component)
        # The warning is for type mismatch since 'invalid' doesn't match any type including enum
        expect(validator.warnings.first).to include('width')
        expect(validator.warnings.first).to match(/expects.*got string/)
      end
    end

    context 'with height as matchParent string' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 'matchParent'
        }
      end

      it 'returns no warnings for valid enum string' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with height as invalid string' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 'invalid'
        }
      end

      it 'returns warning for invalid enum string' do
        validator.validate(component)
        # The warning is for type mismatch since 'invalid' doesn't match any type including enum
        expect(validator.warnings.first).to include('height')
        expect(validator.warnings.first).to match(/expects.*got string/)
      end
    end

    # NEW TESTS: textAlign with binding
    context 'with textAlign as binding' do
      let(:component) do
        {
          'type' => 'Label',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => 'Test',
          'textAlign' => '@{alignment}'
        }
      end

      it 'returns no warnings for binding in enum attribute' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with textAlign as valid enum value' do
      let(:component) do
        {
          'type' => 'Label',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => 'Test',
          'textAlign' => 'Center'
        }
      end

      it 'returns no warnings for valid enum value' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end
  end

  describe 'nested object validation' do
    subject(:validator) { described_class.new }

    context 'with valid shadow object' do
      let(:component) do
        {
          'type' => 'Label',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => 'Hello',
          'shadow' => {
            'color' => '#000000',
            'offsetX' => 2,
            'offsetY' => 2,
            'radius' => 4
          }
        }
      end

      it 'returns no warnings' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with invalid shadow property type' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => 'Hello',
          'shadow' => {
            'color' => '#000000',
            'offsetX' => 'not a number'
          }
        }
      end

      it 'returns warning with path' do
        validator.validate(component)
        expect(validator.warnings.first).to include('shadow.offsetX')
      end
    end

    context 'with unknown shadow property' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => 'Hello',
          'shadow' => {
            'color' => '#000000',
            'unknownProp' => 'value'
          }
        }
      end

      it 'returns warning for unknown nested property' do
        validator.validate(component)
        expect(validator.warnings.first).to include('shadow.unknownProp')
      end
    end
  end

  describe 'partialAttributes array validation' do
    subject(:validator) { described_class.new }

    context 'with valid partialAttributes' do
      let(:component) do
        {
          'type' => 'Label',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => 'Hello World',
          'partialAttributes' => [
            {
              'font' => 'bold',
              'fontSize' => 18,
              'range' => [0, 5]
            }
          ]
        }
      end

      it 'returns no warnings' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with nested underline in partialAttributes' do
      let(:component) do
        {
          'type' => 'Label',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => 'Hello World',
          'partialAttributes' => [
            {
              'underline' => {
                'lineStyle' => 'Single',
                'color' => '#FF0000'
              },
              'range' => [0, 5]
            }
          ]
        }
      end

      it 'returns no warnings for valid nested object' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end
  end

  describe 'mode-based validation' do
    context 'with UIKit mode' do
      subject(:validator) { described_class.new(:uikit) }

      it 'allows UIKit-only attributes' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'gradient' => ['#FF0000', '#0000FF']
        }
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end

      it 'allows common attributes' do
        component = {
          'type' => 'Label',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => 'Hello',
          'fontSize' => 16
        }
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end

      it 'allows RTL-aware attributes in UIKit mode' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'paddingStart' => 16,
          'paddingEnd' => 24,
          'startMargin' => 12,
          'endMargin' => 18
        }
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with SwiftUI mode' do
      subject(:validator) { described_class.new(:swiftui) }

      it 'logs info for UIKit-only gradient attribute' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'gradient' => ['#FF0000', '#0000FF']
        }
        validator.validate(component)
        expect(validator.infos.any? { |i| i.include?('gradient') }).to be true
        expect(validator.infos.any? { |i| i.include?('Uikit') }).to be true
      end

      it 'logs info for UIKit-only applyLiquidGlass attribute' do
        component = {
          'type' => 'TextField',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'text' => 'test',
          'applyLiquidGlass' => true
        }
        validator.validate(component)
        expect(validator.infos.any? { |i| i.include?('applyLiquidGlass') }).to be true
      end

      it 'logs info for UIKit-only caretAttributes' do
        component = {
          'type' => 'SelectBox',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'items' => %w[A B],
          'caretAttributes' => { 'src' => 'caret' }
        }
        validator.validate(component)
        expect(validator.infos.any? { |i| i.include?('caretAttributes') }).to be true
      end

      it 'logs info for UIKit-only min/max padding' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'minTopPadding' => 10,
          'maxBottomMargin' => 20
        }
        validator.validate(component)
        expect(validator.infos.count { |i| i.include?('Uikit') }).to be >= 2
      end

      it 'allows common attributes' do
        component = {
          'type' => 'Label',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => 'Hello',
          'fontSize' => 16
        }
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end

      it 'allows RTL-aware attributes in SwiftUI mode' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'paddingStart' => 16,
          'paddingEnd' => 24,
          'startMargin' => 12,
          'endMargin' => 18
        }
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with :all mode' do
      subject(:validator) { described_class.new(:all) }

      it 'allows all attributes without mode warnings' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'gradient' => ['#FF0000', '#0000FF'],
          'fontSize' => 16
        }
        validator.validate(component)
        # Should not have mode-related warnings
        mode_warnings = validator.warnings.select { |w| w.include?('only supported in') }
        expect(mode_warnings).to be_empty
      end

      it 'allows RTL-aware attributes in all mode' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'paddingStart' => 16,
          'paddingEnd' => 24,
          'startMargin' => 12,
          'endMargin' => 18
        }
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end
  end

  describe '#has_warnings?' do
    subject(:validator) { described_class.new }

    it 'returns false when no warnings' do
      validator.validate({ 'type' => 'Label', 'width' => 'wrapContent', 'height' => 'wrapContent', 'text' => 'Hello' })
      expect(validator.has_warnings?).to be false
    end

    it 'returns true when warnings exist' do
      validator.validate({ 'type' => 'Label', 'width' => 'wrapContent', 'height' => 'wrapContent', 'unknownAttr' => 'value' })
      expect(validator.has_warnings?).to be true
    end
  end

  describe 'RTL attributes presence in definitions' do
    subject(:validator) { described_class.new }

    it 'has paddingStart defined in common attributes' do
      common_attrs = validator.definitions['common']
      expect(common_attrs).to have_key('paddingStart')
      expect(common_attrs['paddingStart']['type']).to eq(["number", "binding"])
      expect(common_attrs['paddingStart']['description']).to include('RTL')
    end

    it 'has paddingEnd defined in common attributes' do
      common_attrs = validator.definitions['common']
      expect(common_attrs).to have_key('paddingEnd')
      expect(common_attrs['paddingEnd']['type']).to eq(["number", "binding"])
      expect(common_attrs['paddingEnd']['description']).to include('RTL')
    end

    it 'has startMargin defined in common attributes' do
      common_attrs = validator.definitions['common']
      expect(common_attrs).to have_key('startMargin')
      expect(common_attrs['startMargin']['type']).to eq(["number", "binding"])
      expect(common_attrs['startMargin']['description']).to include('RTL')
    end

    it 'has endMargin defined in common attributes' do
      common_attrs = validator.definitions['common']
      expect(common_attrs).to have_key('endMargin')
      expect(common_attrs['endMargin']['type']).to eq(["number", "binding"])
      expect(common_attrs['endMargin']['description']).to include('RTL')
    end
  end

  # NEW: Tests for TextField focus/blur event handlers
  describe 'TextField focus/blur event handlers' do
    subject(:validator) { described_class.new }

    context 'with onFocus event handler' do
      let(:component) do
        {
          'type' => 'TextField',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'text' => '@{inputText}',
          'onFocus' => 'handleFocus'
        }
      end

      it 'returns no warnings for valid onFocus' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with onBlur event handler' do
      let(:component) do
        {
          'type' => 'TextField',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'text' => '@{inputText}',
          'onBlur' => 'handleBlur'
        }
      end

      it 'returns no warnings for valid onBlur' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with onBeginEditing event handler' do
      let(:component) do
        {
          'type' => 'TextField',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'text' => '@{inputText}',
          'onBeginEditing' => 'handleBeginEditing'
        }
      end

      it 'returns no warnings for valid onBeginEditing' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with onEndEditing event handler' do
      let(:component) do
        {
          'type' => 'TextField',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'text' => '@{inputText}',
          'onEndEditing' => 'handleEndEditing'
        }
      end

      it 'returns no warnings for valid onEndEditing' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with all focus/blur event handlers' do
      let(:component) do
        {
          'type' => 'TextField',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'text' => '@{inputText}',
          'hint' => 'Enter text',
          'onFocus' => 'handleFocus',
          'onBlur' => 'handleBlur',
          'onBeginEditing' => 'handleBeginEditing',
          'onEndEditing' => 'handleEndEditing'
        }
      end

      it 'returns no warnings for all event handlers' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    it 'has onFocus defined in TextField attributes' do
      text_field_attrs = validator.definitions['TextField']
      expect(text_field_attrs).to have_key('onFocus')
      expect(text_field_attrs['onFocus']['type']).to eq('string')
    end

    it 'has onBlur defined in TextField attributes' do
      text_field_attrs = validator.definitions['TextField']
      expect(text_field_attrs).to have_key('onBlur')
      expect(text_field_attrs['onBlur']['type']).to eq('string')
    end

    it 'has onBeginEditing defined in TextField attributes' do
      text_field_attrs = validator.definitions['TextField']
      expect(text_field_attrs).to have_key('onBeginEditing')
      expect(text_field_attrs['onBeginEditing']['type']).to eq('string')
    end

    it 'has onEndEditing defined in TextField attributes' do
      text_field_attrs = validator.definitions['TextField']
      expect(text_field_attrs).to have_key('onEndEditing')
      expect(text_field_attrs['onEndEditing']['type']).to eq('string')
    end
  end

  # NEW: Tests for Switch/Toggle new attributes
  describe 'Switch/Toggle new attributes' do
    subject(:validator) { described_class.new }

    context 'with onTintColor attribute' do
      let(:component) do
        {
          'type' => 'Switch',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'isOn' => '@{isEnabled}',
          'onTintColor' => '#00FF00'
        }
      end

      it 'returns no warnings for valid onTintColor' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with bind attribute' do
      let(:component) do
        {
          'type' => 'Switch',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'bind' => '@{isToggled}'
        }
      end

      it 'returns no warnings for valid bind' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with enabled attribute' do
      let(:component) do
        {
          'type' => 'Switch',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'isOn' => true,
          'enabled' => '@{canToggle}'
        }
      end

      it 'returns no warnings for valid enabled binding' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with all Switch attributes' do
      let(:component) do
        {
          'type' => 'Switch',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'isOn' => '@{isOn}',
          'bind' => '@{switchState}',
          'enabled' => true,
          'onTintColor' => '#00FF00',
          'offTintColor' => '#CCCCCC',
          'thumbTintColor' => '#FFFFFF',
          'onValueChange' => '@{handleChange}'
        }
      end

      it 'returns no warnings for all Switch attributes' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with Toggle alias' do
      let(:component) do
        {
          'type' => 'Toggle',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'isOn' => '@{isOn}',
          'bind' => '@{toggleState}',
          'enabled' => true,
          'onTintColor' => '#00FF00'
        }
      end

      it 'returns no warnings for Toggle with new attributes' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    it 'has onTintColor defined in Switch attributes' do
      switch_attrs = validator.definitions['Switch']
      expect(switch_attrs).to have_key('onTintColor')
      expect(switch_attrs['onTintColor']['type']).to eq('string')
    end

    it 'has bind defined in Switch attributes' do
      switch_attrs = validator.definitions['Switch']
      expect(switch_attrs).to have_key('bind')
      expect(switch_attrs['bind']['type']).to eq('binding')
    end

    it 'has enabled defined in Switch attributes' do
      switch_attrs = validator.definitions['Switch']
      expect(switch_attrs).to have_key('enabled')
      expect(switch_attrs['enabled']['type']).to eq(['boolean', 'binding'])
    end

    it 'has onTintColor defined in Toggle attributes' do
      toggle_attrs = validator.definitions['Toggle']
      expect(toggle_attrs).to have_key('onTintColor')
      expect(toggle_attrs['onTintColor']['type']).to eq('string')
    end
  end

  # NEW: Tests for CheckBox/Check new attributes
  describe 'CheckBox/Check new attributes' do
    subject(:validator) { described_class.new }

    context 'with bind attribute on CheckBox' do
      let(:component) do
        {
          'type' => 'CheckBox',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'bind' => '@{isChecked}'
        }
      end

      it 'returns no warnings for valid bind' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with enabled attribute on CheckBox' do
      let(:component) do
        {
          'type' => 'CheckBox',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'isOn' => true,
          'enabled' => '@{canCheck}'
        }
      end

      it 'returns no warnings for valid enabled binding' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with onValueChange on CheckBox' do
      let(:component) do
        {
          'type' => 'CheckBox',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'isOn' => '@{isChecked}',
          'onValueChange' => '@{handleCheckChange}'
        }
      end

      it 'returns no warnings for valid onValueChange' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with all CheckBox attributes' do
      let(:component) do
        {
          'type' => 'CheckBox',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'label' => 'Accept terms',
          'isOn' => '@{isAccepted}',
          'bind' => '@{checkState}',
          'enabled' => true,
          'icon' => 'checkbox_off',
          'onSrc' => 'checkbox_on',
          'onValueChange' => '@{handleChange}'
        }
      end

      it 'returns no warnings for all CheckBox attributes' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with Check alias' do
      let(:component) do
        {
          'type' => 'Check',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'checked' => '@{isChecked}',
          'bind' => '@{checkState}',
          'enabled' => true,
          'icon' => 'check_off',
          'selectedIcon' => 'check_on',
          'onValueChange' => '@{handleChange}'
        }
      end

      it 'returns no warnings for Check with new attributes' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    it 'has bind defined in CheckBox attributes' do
      checkbox_attrs = validator.definitions['CheckBox']
      expect(checkbox_attrs).to have_key('bind')
      expect(checkbox_attrs['bind']['type']).to eq('binding')
    end

    it 'has enabled defined in CheckBox attributes' do
      checkbox_attrs = validator.definitions['CheckBox']
      expect(checkbox_attrs).to have_key('enabled')
      expect(checkbox_attrs['enabled']['type']).to eq(['boolean', 'binding'])
    end

    it 'has onValueChange defined in CheckBox attributes' do
      checkbox_attrs = validator.definitions['CheckBox']
      expect(checkbox_attrs).to have_key('onValueChange')
      expect(checkbox_attrs['onValueChange']['type']).to eq('binding')
    end

    it 'has bind defined in Check attributes' do
      check_attrs = validator.definitions['Check']
      expect(check_attrs).to have_key('bind')
      expect(check_attrs['bind']['type']).to eq('binding')
    end

    it 'has selectedIcon defined in Check attributes' do
      check_attrs = validator.definitions['Check']
      expect(check_attrs).to have_key('selectedIcon')
      expect(check_attrs['selectedIcon']['type']).to eq('string')
    end
  end

  # NEW: Tests for EditText/Input alias components
  describe 'EditText/Input alias components' do
    subject(:validator) { described_class.new }

    context 'with EditText component' do
      let(:component) do
        {
          'type' => 'EditText',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'text' => '@{inputText}',
          'hint' => 'Enter text',
          'hintColor' => '#999999'
        }
      end

      it 'warns that hintColor is deprecated on SwiftUI' do
        validator.validate(component)
        expect(validator.warnings).to contain_exactly(
          a_string_matching(/hintColor.*deprecated/)
        )
      end
    end

    context 'with EditText placeholder attribute' do
      let(:component) do
        {
          'type' => 'EditText',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'text' => '@{email}',
          'placeholder' => 'Enter email'
        }
      end

      it 'returns no warnings for EditText with placeholder' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with Input component' do
      let(:component) do
        {
          'type' => 'Input',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'text' => '@{inputText}',
          'hint' => 'Enter text',
          'placeholder' => 'Type here'
        }
      end

      it 'returns no warnings for valid Input' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    it 'has EditText defined in definitions' do
      expect(validator.definitions).to have_key('EditText')
      expect(validator.definitions['EditText']['_alias_of']).to eq('TextField')
    end

    it 'has Input defined in definitions' do
      expect(validator.definitions).to have_key('Input')
      expect(validator.definitions['Input']['_alias_of']).to eq('TextField')
    end

    it 'has text attribute in EditText' do
      edit_text_attrs = validator.definitions['EditText']
      expect(edit_text_attrs).to have_key('text')
      expect(edit_text_attrs['text']['type']).to eq(['string', 'binding'])
    end

    it 'has hint attribute in EditText' do
      edit_text_attrs = validator.definitions['EditText']
      expect(edit_text_attrs).to have_key('hint')
      expect(edit_text_attrs['hint']['type']).to eq('string')
    end

    it 'has placeholder attribute in EditText' do
      edit_text_attrs = validator.definitions['EditText']
      expect(edit_text_attrs).to have_key('placeholder')
      expect(edit_text_attrs['placeholder']['type']).to eq('string')
    end

    it 'has text attribute in Input' do
      input_attrs = validator.definitions['Input']
      expect(input_attrs).to have_key('text')
      expect(input_attrs['text']['type']).to eq(['string', 'binding'])
    end

    it 'has hint attribute in Input' do
      input_attrs = validator.definitions['Input']
      expect(input_attrs).to have_key('hint')
      expect(input_attrs['hint']['type']).to eq('string')
    end
  end

  # NEW: Tests for invalid binding syntax
  describe 'Invalid binding syntax validation' do
    subject(:validator) { described_class.new }

    context 'with valid binding syntax' do
      let(:component) do
        {
          'type' => 'Label',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => '@{userName}'
        }
      end

      it 'returns no warnings for valid binding' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with invalid binding syntax - missing closing brace' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => '@{userName'
        }
      end

      it 'returns warning for invalid binding syntax' do
        validator.validate(component)
        expect(validator.warnings.any? { |w| w.include?("Attribute 'text' in 'Label' has invalid binding syntax") }).to be true
      end
    end

    context 'with invalid binding syntax - extra characters after closing brace' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => '@{userName}extra'
        }
      end

      it 'returns warning for invalid binding syntax' do
        validator.validate(component)
        expect(validator.warnings.any? { |w| w.include?("Attribute 'text' in 'Label' has invalid binding syntax") }).to be true
      end
    end

    context 'with regular string value' do
      let(:component) do
        {
          'type' => 'Label',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => 'Hello World'
        }
      end

      it 'returns no warnings for regular string' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with string containing @{ but not at start' do
      let(:component) do
        {
          'type' => 'Label',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => 'Email: @{email}'
        }
      end

      it 'returns no warnings for string with @{ in middle' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with binding attribute type and invalid syntax' do
      let(:component) do
        {
          'type' => 'TextField',
          'text' => '@{inputValue'
        }
      end

      it 'returns warning for invalid binding syntax' do
        validator.validate(component)
        expect(validator.warnings.any? { |w| w.include?("Attribute 'text' in 'TextField' has invalid binding syntax") }).to be true
      end
    end

    context 'with nested object property having invalid binding syntax' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => 'Hello',
          'shadow' => {
            'color' => '@{shadowColor'
          }
        }
      end

      it 'returns warning for invalid binding syntax in nested property' do
        validator.validate(component)
        expect(validator.warnings.any? { |w| w.include?("Attribute 'shadow.color' in 'Label' has invalid binding syntax") }).to be true
      end
    end
  end

  # NEW: Tests for lifecycle event attributes (SwiftUI/Compose only)
  describe 'Lifecycle event attributes' do
    subject(:validator) { described_class.new(:swiftui) }

    context 'with onAppear event handler' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'onAppear' => 'handleAppear'
        }
      end

      it 'returns no warnings for valid onAppear' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with onDisappear event handler' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'onDisappear' => 'handleDisappear'
        }
      end

      it 'returns no warnings for valid onDisappear' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    context 'with both lifecycle handlers' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'onAppear' => 'handleAppear',
          'onDisappear' => 'handleDisappear'
        }
      end

      it 'returns no warnings for both lifecycle handlers' do
        validator.validate(component)
        expect(validator.warnings).to be_empty
      end
    end

    it 'has onAppear defined in common attributes' do
      common_attrs = validator.definitions['common']
      expect(common_attrs).to have_key('onAppear')
      expect(common_attrs['onAppear']['type']).to eq('string')
      # onAppear is supported in SwiftUI and Compose; currently tagged with the
      # shared 'compose' mode in attribute_definitions.json.
      expect(common_attrs['onAppear']['mode']).to eq('compose')
    end

    it 'has onDisappear defined in common attributes' do
      common_attrs = validator.definitions['common']
      expect(common_attrs).to have_key('onDisappear')
      expect(common_attrs['onDisappear']['type']).to eq('string')
      expect(common_attrs['onDisappear']['mode']).to eq('compose')
    end
  end

  # NEW: Tests for weight dimension conflict
  describe '#check_weight_dimension_conflict' do
    subject(:validator) { described_class.new }

    context 'with horizontal parent orientation' do
      it 'warns when component has both weight and width' do
        component = {
          'type' => 'View',
          'width' => 100,
          'height' => 'wrapContent',
          'weight' => 1
        }
        warnings = validator.validate(component, nil, 'horizontal')
        expect(warnings.any? { |w| w.include?("'weight' and 'width'") && w.include?('horizontal') }).to be true
      end

      it 'does not warn when component has weight and height (cross direction)' do
        component = {
          'type' => 'View',
          'height' => 100,
          'weight' => 1
        }
        warnings = validator.validate(component, nil, 'horizontal')
        expect(warnings.none? { |w| w.include?("'weight' and 'height'") }).to be true
      end
    end

    context 'with vertical parent orientation' do
      it 'warns when component has both weight and height' do
        component = {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 100,
          'weight' => 1
        }
        warnings = validator.validate(component, nil, 'vertical')
        expect(warnings.any? { |w| w.include?("'weight' and 'height'") && w.include?('vertical') }).to be true
      end

      it 'does not warn when component has weight and width (cross direction)' do
        component = {
          'type' => 'View',
          'width' => 100,
          'weight' => 1
        }
        warnings = validator.validate(component, nil, 'vertical')
        expect(warnings.none? { |w| w.include?("'weight' and 'width'") }).to be true
      end
    end

    context 'with nil parent orientation (include file root)' do
      it 'does not warn because parent orientation is unknown' do
        component = {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'weight' => 1
        }
        # nil means include file root - parent orientation unknown, skip warning
        warnings = validator.validate(component, nil, nil)
        expect(warnings.none? { |w| w.include?('weight') }).to be true
      end
    end

    context 'without weight' do
      it 'does not warn' do
        component = {
          'type' => 'View',
          'width' => 100,
          'height' => 100
        }
        warnings = validator.validate(component, nil, 'horizontal')
        expect(warnings.none? { |w| w.include?('weight') }).to be true
      end
    end

    context 'with widthWeight (UIKit mode)' do
      it 'does not require width when widthWeight is set' do
        component = {
          'type' => 'View',
          'height' => 'matchParent',
          'widthWeight' => 4.0
        }
        warnings = validator.validate(component, nil, 'horizontal')
        expect(warnings.none? { |w| w.include?("'width'") && w.include?('missing') }).to be true
      end
    end

    context 'with heightWeight (UIKit mode)' do
      it 'does not require height when heightWeight is set' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'heightWeight' => 2.0
        }
        warnings = validator.validate(component, nil, 'vertical')
        expect(warnings.none? { |w| w.include?("'height'") && w.include?('missing') }).to be true
      end
    end
  end

  # NEW: Tests for style merging
  describe 'Style merging validation' do
    let(:styles_dir) { File.join(Dir.pwd, 'spec', 'fixtures', 'styles') }

    before(:all) do
      # Create test styles directory and files
      @styles_dir = File.join(Dir.pwd, 'spec', 'fixtures', 'styles')
      FileUtils.mkdir_p(@styles_dir)

      # Create a test style file
      File.write(File.join(@styles_dir, 'TestStyle.json'), JSON.pretty_generate({
        'width' => 'matchParent',
        'height' => 100,
        'cornerRadius' => 8,
        'background' => '#FFFFFF'
      }))

      # Create a style with nested properties
      File.write(File.join(@styles_dir, 'ShadowStyle.json'), JSON.pretty_generate({
        'width' => 'wrapContent',
        'height' => 'wrapContent',
        'shadow' => {
          'color' => '#000000',
          'offsetX' => 2,
          'offsetY' => 2,
          'radius' => 4
        }
      }))
    end

    after(:all) do
      FileUtils.rm_rf(File.join(Dir.pwd, 'spec', 'fixtures', 'styles'))
    end

    context 'with style reference' do
      subject(:validator) { described_class.new(:all, @styles_dir) }

      it 'merges style attributes into component' do
        component = {
          'type' => 'View',
          'style' => 'TestStyle'
        }
        warnings = validator.validate(component)
        # Should not warn about missing width/height because they come from style
        expect(warnings.none? { |w| w.include?("'width'") && w.include?('missing') }).to be true
        expect(warnings.none? { |w| w.include?("'height'") && w.include?('missing') }).to be true
      end

      it 'allows component attributes to override style attributes' do
        component = {
          'type' => 'View',
          'style' => 'TestStyle',
          'cornerRadius' => 16
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'validates merged style attributes' do
        component = {
          'type' => 'View',
          'style' => 'ShadowStyle'
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'ignores non-existent style' do
        component = {
          'type' => 'View',
          'style' => 'NonExistentStyle'
        }
        warnings = validator.validate(component)
        # Should warn about missing required attributes since style doesn't exist
        expect(warnings.any? { |w| w.include?('missing') }).to be true
      end
    end

    context 'without styles_dir' do
      subject(:validator) { described_class.new }

      it 'works without style merging when no styles_dir configured' do
        component = {
          'type' => 'View',
          'style' => 'TestStyle',
          'width' => 'matchParent',
          'height' => 'wrapContent'
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end
  end
end
