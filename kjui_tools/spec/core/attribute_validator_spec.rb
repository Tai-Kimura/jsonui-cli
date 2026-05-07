# frozen_string_literal: true

require 'core/attribute_validator'
require 'fileutils'
require 'json'

RSpec.describe KjuiTools::Core::AttributeValidator do
  describe '#initialize' do
    it 'loads attribute definitions' do
      validator = described_class.new
      expect(validator.definitions).not_to be_empty
      expect(validator.definitions).to have_key('common')
    end

    it 'defaults to :all mode' do
      validator = described_class.new
      expect(validator.mode).to eq(:all)
    end

    it 'accepts mode parameter' do
      validator = described_class.new(:compose)
      expect(validator.mode).to eq(:compose)
    end

    it 'initializes with empty warnings' do
      validator = described_class.new
      expect(validator.warnings).to be_empty
    end
  end

  describe 'extension definitions loading' do
    # Use Dir.pwd-based path since that's what the validator uses
    let(:extensions_dir) do
      File.join(Dir.pwd, 'kjui_tools', 'lib', 'compose', 'components', 'extensions', 'attribute_definitions')
    end

    before do
      # Create test extension definition
      FileUtils.mkdir_p(extensions_dir)
      @test_definition_file = File.join(extensions_dir, 'TestCustomComponent.json')
      File.write(@test_definition_file, JSON.pretty_generate({
        'TestCustomComponent' => {
          'customTitle' => {
            'type' => 'string',
            'description' => 'Custom title attribute'
          },
          'customCount' => {
            'type' => 'number',
            'description' => 'Custom count attribute'
          }
        }
      }))
    end

    after do
      FileUtils.rm_f(@test_definition_file) if @test_definition_file && File.exist?(@test_definition_file)
    end

    it 'loads extension definitions' do
      validator = described_class.new
      expect(validator.definitions).to have_key('TestCustomComponent')
    end

    it 'merges extension definitions with base definitions' do
      validator = described_class.new
      expect(validator.definitions).to have_key('common')
      expect(validator.definitions).to have_key('TestCustomComponent')
    end

    it 'validates custom component attributes' do
      validator = described_class.new
      component = {
        'type' => 'TestCustomComponent',
        'width' => 'wrapContent',
        'height' => 'wrapContent',
        'customTitle' => 'Test Title',
        'customCount' => 42
      }
      warnings = validator.validate(component)
      expect(warnings).to be_empty
    end

    it 'warns on invalid custom component attribute' do
      validator = described_class.new
      component = {
        'type' => 'TestCustomComponent',
        'customTitle' => 'Test Title',
        'invalidAttr' => 'value'
      }
      warnings = validator.validate(component)
      expect(warnings).to include(/Unknown attribute 'invalidAttr'/)
    end

    it 'validates custom component attribute types' do
      validator = described_class.new
      component = {
        'type' => 'TestCustomComponent',
        'customCount' => 'not a number'
      }
      warnings = validator.validate(component)
      expect(warnings).to include(/expects number, got string/)
    end
  end

  describe '#validate' do
    let(:validator) { described_class.new }

    context 'with valid Text component' do
      let(:component) do
        {
          'type' => 'Text',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => 'Hello World',
          'fontSize' => 14,
          'fontColor' => '#333333'
        }
      end

      it 'returns no warnings' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with unknown attribute' do
      let(:component) do
        {
          'type' => 'Text',
          'text' => 'Hello',
          'unknownAttr' => 'value'
        }
      end

      it 'returns warning for unknown attribute' do
        warnings = validator.validate(component)
        expect(warnings).to include(/Unknown attribute 'unknownAttr'/)
      end
    end

    context 'with wrong type' do
      let(:component) do
        {
          'type' => 'Text',
          'fontSize' => 'large'
        }
      end

      it 'returns warning for type mismatch' do
        warnings = validator.validate(component)
        expect(warnings).to include(/expects number or binding, got string/)
      end
    end

    context 'with invalid enum value' do
      let(:component) do
        {
          'type' => 'Text',
          'textAlign' => 'invalid'
        }
      end

      it 'returns warning for invalid enum' do
        warnings = validator.validate(component)
        expect(warnings).to include(/invalid value 'invalid'/)
      end
    end

    context 'with valid enum value' do
      let(:component) do
        {
          'type' => 'Text',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'textAlign' => 'center'
        }
      end

      it 'returns no warnings' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with alpha out of range' do
      let(:component) do
        {
          'type' => 'View',
          'alpha' => 1.5
        }
      end

      it 'returns warning for value exceeding maximum' do
        warnings = validator.validate(component)
        expect(warnings).to include(/greater than maximum/)
      end
    end

    context 'with negative alpha' do
      let(:component) do
        {
          'type' => 'View',
          'alpha' => -0.5
        }
      end

      it 'returns warning for value below minimum' do
        warnings = validator.validate(component)
        expect(warnings).to include(/less than minimum/)
      end
    end

    context 'with binding expression' do
      let(:component) do
        {
          'type' => 'Text',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => '@{userName}'
        }
      end

      it 'skips validation for binding expressions' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with binding expression in enum attribute' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'visibility' => '@{isVisible}'
        }
      end

      it 'skips enum validation for binding expressions' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with binding in the middle of string' do
      let(:component) do
        {
          'type' => 'View',
          'visibility' => 'invalid @{binding}'
        }
      end

      it 'validates enum and returns warning' do
        warnings = validator.validate(component)
        expect(warnings).to include(/invalid value 'invalid @{binding}'/)
      end
    end

    context 'with valid enum value in visibility' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'visibility' => 'visible'
        }
      end

      it 'returns no warnings' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with invalid enum value in visibility' do
      let(:component) do
        {
          'type' => 'View',
          'visibility' => 'invalid'
        }
      end

      it 'returns warning for invalid enum value' do
        warnings = validator.validate(component)
        expect(warnings).to include(/invalid value 'invalid'/)
        expect(warnings).to include(/Valid values: visible, invisible, gone/)
      end
    end

    context 'with required attribute missing' do
      let(:component) do
        {
          'type' => 'Radio'
        }
      end

      it 'returns warning for missing required attribute' do
        warnings = validator.validate(component)
        expect(warnings).to include(/Required attribute 'group' is missing/)
      end
    end

    # New tests for enum array validation
    context 'with enum array values' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'gravity' => ['centerVertical']
        }
      end

      it 'accepts single valid enum value in array' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with multiple enum array values' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'gravity' => ['centerVertical', 'left']
        }
      end

      it 'accepts multiple valid enum values in array' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with invalid enum array values' do
      let(:component) do
        {
          'type' => 'View',
          'gravity' => ['invalid']
        }
      end

      it 'returns warning for invalid enum values in array' do
        warnings = validator.validate(component)
        expect(warnings).to include(/invalid value\(s\)/)
      end
    end

    context 'with mixed valid and invalid enum array values' do
      let(:component) do
        {
          'type' => 'View',
          'gravity' => ['centerVertical', 'invalid', 'left']
        }
      end

      it 'returns warning for invalid enum values in array' do
        warnings = validator.validate(component)
        expect(warnings).to include(/invalid value\(s\)/)
      end
    end

    # Tests for width/height with enum type definitions
    context 'with matchParent string value for width' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 'wrapContent'
        }
      end

      it 'accepts matchParent string value' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with wrapContent string value for height' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 'wrapContent'
        }
      end

      it 'accepts wrapContent string value' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with invalid string value for width' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'invalid'
        }
      end

      it 'returns warning for invalid enum string value' do
        warnings = validator.validate(component)
        expect(warnings).to include(/expects/)
      end
    end

    context 'with numeric value for width' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 100,
          'height' => 'wrapContent'
        }
      end

      it 'accepts numeric value' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with binding value for width' do
      let(:component) do
        {
          'type' => 'View',
          'width' => '@{dynamicWidth}',
          'height' => 'wrapContent'
        }
      end

      it 'accepts binding value' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end
  end

  describe '#validate with different component types' do
    let(:validator) { described_class.new }

    context 'Button component' do
      let(:component) do
        {
          'type' => 'Button',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => 'Click Me',
          'onclick' => 'handleClick',
          'enabled' => true
        }
      end

      it 'validates button-specific attributes' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'TextField component' do
      let(:component) do
        {
          'type' => 'TextField',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'hint' => 'Enter text',
          'input' => 'email',
          'returnKeyType' => 'Done',
          'secure' => false
        }
      end

      it 'validates textfield-specific attributes' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'warns on invalid input type' do
        component['input'] = 'invalid'
        warnings = validator.validate(component)
        expect(warnings).to include(/invalid value 'invalid'/)
      end
    end

    context 'Image component' do
      let(:component) do
        {
          'type' => 'Image',
          'src' => 'icon_home',
          'contentMode' => 'fit',
          'width' => 24,
          'height' => 24
        }
      end

      it 'validates image-specific attributes' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'Switch component' do
      let(:component) do
        {
          'type' => 'Switch',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'isOn' => true,
          'onTintColor' => '#00FF00',
          'onValueChange' => '@{handleSwitch}'
        }
      end

      it 'validates switch-specific attributes' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'SelectBox component' do
      let(:component) do
        {
          'type' => 'SelectBox',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'items' => ['Option 1', 'Option 2'],
          'hint' => 'Select option',
          'datePickerMode' => 'date'
        }
      end

      it 'validates selectbox-specific attributes' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'Collection component' do
      let(:component) do
        {
          'type' => 'Collection',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'columns' => 2,
          'columnSpacing' => 8,
          'layout' => 'vertical'
        }
      end

      it 'validates collection-specific attributes' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'View container' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'orientation' => 'vertical',
          'spacing' => 8
        }
      end

      it 'validates view-specific attributes' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'ScrollView component' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'orientation' => 'vertical',
          'scrollEnabled' => true
        }
      end

      it 'validates scrollview-specific attributes' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end
  end

  describe '#validate common attributes' do
    let(:validator) { described_class.new }

    context 'size attributes' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 100,
          'height' => 200,
          'minWidth' => 50,
          'maxWidth' => 300
        }
      end

      it 'accepts numeric values' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'accepts matchParent string' do
        component['width'] = 'matchParent'
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'accepts wrapContent string' do
        component['height'] = 'wrapContent'
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'padding attributes' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'padding' => 16,
          'paddingTop' => 8,
          'paddingBottom' => 8
        }
      end

      it 'accepts padding values' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'accepts paddings array' do
        component['paddings'] = [8, 16, 8, 16]
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'margin attributes' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'margins' => [8, 8, 8, 8],
          'topMargin' => 16
        }
      end

      it 'accepts margin values' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'visual attributes' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'background' => '#FFFFFF',
          'cornerRadius' => 8,
          'borderWidth' => 1,
          'borderColor' => '#CCCCCC',
          'shadow' => '#000000|0|2|0.3|4'
        }
      end

      it 'accepts visual attributes' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'constraint layout attributes' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'alignTopOfView' => 'otherId',
          'alignLeftView' => 'otherId',
          'alignCenterVerticalView' => 'parent'
        }
      end

      it 'accepts constraint layout attributes' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end
  end

  describe 'mode compatibility' do
    context 'with xml mode' do
      let(:validator) { described_class.new(:xml) }

      let(:component) do
        {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'aspectWidth' => 16,
          'aspectHeight' => 9
        }
      end

      it 'accepts xml-specific attributes' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with compose mode' do
      let(:validator) { described_class.new(:compose) }

      let(:component) do
        {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'background' => '#FFFFFF'
        }
      end

      it 'accepts common attributes' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end
  end

  describe '#has_warnings?' do
    let(:validator) { described_class.new }

    it 'returns false when no warnings' do
      validator.validate({ 'type' => 'Text', 'width' => 'wrapContent', 'height' => 'wrapContent', 'text' => 'Hello' })
      expect(validator.has_warnings?).to be false
    end

    it 'returns true when warnings exist' do
      validator.validate({ 'type' => 'Text', 'unknownAttr' => 'value' })
      expect(validator.has_warnings?).to be true
    end
  end

  describe 'type mapping' do
    let(:validator) { described_class.new }

    it 'maps Label to Text' do
      component = { 'type' => 'Label', 'width' => 'wrapContent', 'height' => 'wrapContent', 'text' => 'Hello' }
      warnings = validator.validate(component)
      expect(warnings).to be_empty
    end

    it 'maps EditText to TextField' do
      component = { 'type' => 'EditText', 'width' => 'wrapContent', 'height' => 'wrapContent', 'hint' => 'Enter' }
      warnings = validator.validate(component)
      expect(warnings).to be_empty
    end

    it 'maps Toggle to Switch' do
      component = { 'type' => 'Toggle', 'width' => 'wrapContent', 'height' => 'wrapContent', 'isOn' => true }
      warnings = validator.validate(component)
      expect(warnings).to be_empty
    end

    it 'maps RecyclerView to Collection' do
      component = { 'type' => 'RecyclerView', 'width' => 'wrapContent', 'height' => 'wrapContent', 'columns' => 2 }
      warnings = validator.validate(component)
      expect(warnings).to be_empty
    end

    it 'maps Container to View' do
      component = { 'type' => 'Container', 'width' => 'wrapContent', 'height' => 'wrapContent', 'orientation' => 'vertical' }
      warnings = validator.validate(component)
      expect(warnings).to be_empty
    end
  end

  # NEW: Tests for TextField focus/blur event handlers
  describe 'TextField focus/blur event handlers' do
    let(:validator) { described_class.new }

    context 'with onFocus event handler' do
      let(:component) do
        {
          'type' => 'TextField',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => '@{inputText}',
          'onFocus' => 'handleFocus'
        }
      end

      it 'returns no warnings for valid onFocus' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with onBlur event handler' do
      let(:component) do
        {
          'type' => 'TextField',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => '@{inputText}',
          'onBlur' => 'handleBlur'
        }
      end

      it 'returns no warnings for valid onBlur' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with onBeginEditing event handler' do
      let(:component) do
        {
          'type' => 'TextField',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => '@{inputText}',
          'onBeginEditing' => 'handleBeginEditing'
        }
      end

      it 'returns no warnings for valid onBeginEditing' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with onEndEditing event handler' do
      let(:component) do
        {
          'type' => 'TextField',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => '@{inputText}',
          'onEndEditing' => 'handleEndEditing'
        }
      end

      it 'returns no warnings for valid onEndEditing' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with all focus/blur event handlers' do
      let(:component) do
        {
          'type' => 'TextField',
          'width' => 'wrapContent',
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
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    it 'has onFocus defined in TextField attributes' do
      expect(validator.definitions['TextField']).to have_key('onFocus')
      expect(validator.definitions['TextField']['onFocus']['type']).to eq('string')
    end

    it 'has onBlur defined in TextField attributes' do
      expect(validator.definitions['TextField']).to have_key('onBlur')
      expect(validator.definitions['TextField']['onBlur']['type']).to eq('string')
    end

    it 'has onBeginEditing defined in TextField attributes' do
      expect(validator.definitions['TextField']).to have_key('onBeginEditing')
      expect(validator.definitions['TextField']['onBeginEditing']['type']).to eq('string')
    end

    it 'has onEndEditing defined in TextField attributes' do
      expect(validator.definitions['TextField']).to have_key('onEndEditing')
      expect(validator.definitions['TextField']['onEndEditing']['type']).to eq('string')
    end
  end

  # NEW: Tests for Switch/Toggle new attributes
  describe 'Switch/Toggle new attributes' do
    let(:validator) { described_class.new }

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
        warnings = validator.validate(component)
        expect(warnings).to be_empty
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
        warnings = validator.validate(component)
        expect(warnings).to be_empty
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
        warnings = validator.validate(component)
        expect(warnings).to be_empty
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
          'thumbTintColor' => '#FFFFFF',
          'onValueChange' => '@{handleChange}'
        }
      end

      it 'returns no warnings for all Switch attributes' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
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
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    it 'has onTintColor defined in Switch attributes' do
      expect(validator.definitions['Switch']).to have_key('onTintColor')
      expect(validator.definitions['Switch']['onTintColor']['type']).to eq('string')
    end

    it 'has bind defined in Switch attributes' do
      expect(validator.definitions['Switch']).to have_key('bind')
      expect(validator.definitions['Switch']['bind']['type']).to eq('binding')
    end

    it 'has enabled defined in Switch attributes' do
      expect(validator.definitions['Switch']).to have_key('enabled')
      expect(validator.definitions['Switch']['enabled']['type']).to eq(['boolean', 'binding'])
    end

    it 'has onTintColor defined in Toggle attributes' do
      expect(validator.definitions['Toggle']).to have_key('onTintColor')
      expect(validator.definitions['Toggle']['onTintColor']['type']).to eq('string')
    end
  end

  # NEW: Tests for CheckBox/Check new attributes
  describe 'CheckBox/Check new attributes' do
    let(:validator) { described_class.new }

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
        warnings = validator.validate(component)
        expect(warnings).to be_empty
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
        warnings = validator.validate(component)
        expect(warnings).to be_empty
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
        warnings = validator.validate(component)
        expect(warnings).to be_empty
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
        warnings = validator.validate(component)
        expect(warnings).to be_empty
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
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    it 'has bind defined in CheckBox attributes' do
      expect(validator.definitions['CheckBox']).to have_key('bind')
      expect(validator.definitions['CheckBox']['bind']['type']).to eq('binding')
    end

    it 'has enabled defined in CheckBox attributes' do
      expect(validator.definitions['CheckBox']).to have_key('enabled')
      expect(validator.definitions['CheckBox']['enabled']['type']).to eq(['boolean', 'binding'])
    end

    it 'has onValueChange defined in CheckBox attributes' do
      expect(validator.definitions['CheckBox']).to have_key('onValueChange')
      expect(validator.definitions['CheckBox']['onValueChange']['type']).to eq('binding')
    end

    it 'has bind defined in Check attributes' do
      expect(validator.definitions['Check']).to have_key('bind')
      expect(validator.definitions['Check']['bind']['type']).to eq('binding')
    end

    it 'has selectedIcon defined in Check attributes' do
      expect(validator.definitions['Check']).to have_key('selectedIcon')
      expect(validator.definitions['Check']['selectedIcon']['type']).to eq('string')
    end
  end

  # NEW: Tests for EditText/Input alias components
  describe 'EditText/Input alias components' do
    let(:validator) { described_class.new }

    context 'with EditText component' do
      let(:component) do
        {
          'type' => 'EditText',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => '@{inputText}',
          'hint' => 'Enter text',
          'hintColor' => '#999999'
        }
      end

      it 'returns no warnings for valid EditText' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with EditText placeholder attribute' do
      let(:component) do
        {
          'type' => 'EditText',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => '@{email}',
          'placeholder' => 'Enter email'
        }
      end

      it 'returns no warnings for EditText with placeholder' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with Input component' do
      let(:component) do
        {
          'type' => 'Input',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => '@{inputText}',
          'hint' => 'Enter text',
          'placeholder' => 'Type here'
        }
      end

      it 'returns no warnings for valid Input' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
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
      expect(validator.definitions['EditText']).to have_key('text')
      expect(validator.definitions['EditText']['text']['type']).to eq(['string', 'binding'])
    end

    it 'has hint attribute in EditText' do
      expect(validator.definitions['EditText']).to have_key('hint')
      expect(validator.definitions['EditText']['hint']['type']).to eq('string')
    end

    it 'has placeholder attribute in EditText' do
      expect(validator.definitions['EditText']).to have_key('placeholder')
      expect(validator.definitions['EditText']['placeholder']['type']).to eq('string')
    end

    it 'has text attribute in Input' do
      expect(validator.definitions['Input']).to have_key('text')
      expect(validator.definitions['Input']['text']['type']).to eq(['string', 'binding'])
    end

    it 'has hint attribute in Input' do
      expect(validator.definitions['Input']).to have_key('hint')
      expect(validator.definitions['Input']['hint']['type']).to eq('string')
    end
  end

  # NEW: Tests for Swift platform-specific attributes
  describe 'Swift platform-specific attributes' do
    let(:validator) { described_class.new }

    it 'has offTintColor defined in Switch with swift platform marker' do
      switch_attrs = validator.definitions['Switch']
      expect(switch_attrs).to have_key('offTintColor')
      expect(switch_attrs['offTintColor']['platform']).to eq('swift')
      expect(switch_attrs['offTintColor']['mode']).to eq('uikit')
    end

    it 'has aspectWidth defined in common with swift platform marker' do
      common_attrs = validator.definitions['common']
      expect(common_attrs).to have_key('aspectWidth')
      expect(common_attrs['aspectWidth']['platform']).to eq('swift')
      expect(common_attrs['aspectWidth']['mode']).to eq('uikit')
    end

    it 'has maxWidthWeight defined in common with swift platform marker' do
      common_attrs = validator.definitions['common']
      expect(common_attrs).to have_key('maxWidthWeight')
      expect(common_attrs['maxWidthWeight']['platform']).to eq('swift')
      expect(common_attrs['maxWidthWeight']['mode']).to eq('uikit')
    end

    it 'has selected defined in Label with swift platform marker' do
      label_attrs = validator.definitions['Label']
      expect(label_attrs).to have_key('selected')
      expect(label_attrs['selected']['platform']).to eq('swift')
    end

    it 'has highlightSrcName defined in Image with swift platform marker' do
      image_attrs = validator.definitions['Image']
      expect(image_attrs).to have_key('highlightSrcName')
      expect(image_attrs['highlightSrcName']['platform']).to eq('swift')
      expect(image_attrs['highlightSrcName']['mode']).to eq('uikit')
    end

    it 'has cachePolicy defined in NetworkImage with swift platform marker' do
      network_image_attrs = validator.definitions['NetworkImage']
      expect(network_image_attrs).to have_key('cachePolicy')
      expect(network_image_attrs['cachePolicy']['platform']).to eq('swift')
      expect(network_image_attrs['cachePolicy']['mode']).to eq('uikit')
    end
  end

  # NEW: Tests for invalid binding syntax
  describe 'Invalid binding syntax validation' do
    let(:validator) { described_class.new }

    context 'with valid binding syntax' do
      let(:component) do
        {
          'type' => 'Text',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => '@{userName}'
        }
      end

      it 'returns no warnings for valid binding' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with invalid binding syntax - missing closing brace' do
      let(:component) do
        {
          'type' => 'Text',
          'text' => '@{userName'
        }
      end

      it 'returns warning for invalid binding syntax' do
        warnings = validator.validate(component)
        expect(warnings).to include(
          "Attribute 'text' in 'Text' has invalid binding syntax (starts with '@{' but doesn't end with '}')"
        )
      end
    end

    context 'with invalid binding syntax - extra characters after closing brace' do
      let(:component) do
        {
          'type' => 'Text',
          'text' => '@{userName}extra'
        }
      end

      it 'returns warning for invalid binding syntax' do
        warnings = validator.validate(component)
        expect(warnings).to include(
          "Attribute 'text' in 'Text' has invalid binding syntax (starts with '@{' but doesn't end with '}')"
        )
      end
    end

    context 'with regular string value' do
      let(:component) do
        {
          'type' => 'Text',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => 'Hello World'
        }
      end

      it 'returns no warnings for regular string' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with string containing @{ but not at start' do
      let(:component) do
        {
          'type' => 'Text',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'text' => 'Email: @{email}'
        }
      end

      it 'returns no warnings for string with @{ in middle' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
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
        warnings = validator.validate(component)
        expect(warnings).to include(
          "Attribute 'text' in 'TextField' has invalid binding syntax (starts with '@{' but doesn't end with '}')"
        )
      end
    end

    context 'with nested object property having invalid binding syntax' do
      let(:component) do
        {
          'type' => 'Text',
          'text' => 'Hello',
          'shadow' => {
            'color' => '@{shadowColor'
          }
        }
      end

      it 'returns warning for invalid binding syntax in nested property' do
        warnings = validator.validate(component)
        expect(warnings).to include(
          "Attribute 'shadow.color' in 'Text' has invalid binding syntax (starts with '@{' but doesn't end with '}')"
        )
      end
    end
  end

  # NEW: Tests for lifecycle event attributes (SwiftUI/Compose only)
  describe 'Lifecycle event attributes' do
    let(:validator) { described_class.new(:compose) }

    context 'with onAppear event handler' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'onAppear' => 'handleAppear'
        }
      end

      it 'returns no warnings for valid onAppear' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with onDisappear event handler' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'onDisappear' => 'handleDisappear'
        }
      end

      it 'returns no warnings for valid onDisappear' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with both lifecycle handlers' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'onAppear' => 'handleAppear',
          'onDisappear' => 'handleDisappear'
        }
      end

      it 'returns no warnings for both lifecycle handlers' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    it 'has onAppear defined in common attributes' do
      common_attrs = validator.definitions['common']
      expect(common_attrs).to have_key('onAppear')
      expect(common_attrs['onAppear']['type']).to eq('string')
      expect(common_attrs['onAppear']['mode']).to eq('compose')
    end

    it 'has onDisappear defined in common attributes' do
      common_attrs = validator.definitions['common']
      expect(common_attrs).to have_key('onDisappear')
      expect(common_attrs['onDisappear']['type']).to eq('string')
      expect(common_attrs['onDisappear']['mode']).to eq('compose')
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

  describe '#check_weight_dimension_conflict' do
    let(:validator) { described_class.new }

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

    context 'with no parent orientation (ZStack)' do
      it 'warns that weight is not applicable' do
        component = {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'weight' => 1
        }
        warnings = validator.validate(component, nil, nil)
        expect(warnings.any? { |w| w.include?("'weight'") && w.include?('ZStack') }).to be true
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
  end
end
