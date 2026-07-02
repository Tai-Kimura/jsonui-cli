# frozen_string_literal: true

require 'compose/components/button_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'

RSpec.describe KjuiTools::Compose::Components::ButtonComponent do
  let(:required_imports) { Set.new }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
    # Clear data definitions before each test
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  describe '.generate' do
    it 'generates basic Button component' do
      json_data = { 'type' => 'Button', 'text' => 'Click Me' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Button(')
      expect(result).to include('Click Me')
    end

    it 'generates Button with onClick handler' do
      json_data = { 'type' => 'Button', 'text' => 'Submit', 'onclick' => 'handleSubmit' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('onClick = { data.handleSubmit?.invoke() }')
    end

    it 'generates Button with empty onClick when no handler' do
      json_data = { 'type' => 'Button', 'text' => 'Test' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('onClick = { }')
    end

    it 'generates Button with cornerRadius' do
      json_data = { 'type' => 'Button', 'text' => 'Test', 'cornerRadius' => 8 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('shape = RoundedCornerShape(8.dp)')
      expect(required_imports).to include(:shape)
    end

    it 'generates Button with margins' do
      json_data = { 'type' => 'Button', 'text' => 'Test', 'margins' => [10, 20, 30, 40] }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.padding(')
    end

    it 'generates Button with width' do
      json_data = { 'type' => 'Button', 'text' => 'Test', 'width' => 200 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.width(200.dp)')
    end

    it 'generates Button with height' do
      json_data = { 'type' => 'Button', 'text' => 'Test', 'height' => 50 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.height(50.dp)')
    end

    it 'generates Button with single padding value' do
      json_data = { 'type' => 'Button', 'text' => 'Test', 'padding' => 16 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('contentPadding = PaddingValues(16.dp)')
      expect(required_imports).to include(:button_padding)
    end

    it 'generates Button with paddings array of 1' do
      json_data = { 'type' => 'Button', 'text' => 'Test', 'paddings' => [16] }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('contentPadding = PaddingValues(16.dp)')
    end

    it 'generates Button with paddings array of 2' do
      json_data = { 'type' => 'Button', 'text' => 'Test', 'paddings' => [10, 20] }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('vertical = 10.dp')
      expect(result).to include('horizontal = 20.dp')
    end

    it 'generates Button with paddings array of 3' do
      json_data = { 'type' => 'Button', 'text' => 'Test', 'paddings' => [10, 20, 30] }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('top = 10.dp')
      expect(result).to include('horizontal = 20.dp')
      expect(result).to include('bottom = 30.dp')
    end

    it 'generates Button with paddings array of 4' do
      json_data = { 'type' => 'Button', 'text' => 'Test', 'paddings' => [10, 20, 30, 40] }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('top = 10.dp')
      expect(result).to include('end = 20.dp')
      expect(result).to include('bottom = 30.dp')
      expect(result).to include('start = 40.dp')
    end

    it 'generates Button with individual padding attributes' do
      json_data = { 'type' => 'Button', 'text' => 'Test', 'paddingTop' => 10, 'paddingBottom' => 20 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('contentPadding')
    end

    it 'generates Button with paddingHorizontal and paddingVertical' do
      json_data = { 'type' => 'Button', 'text' => 'Test', 'paddingHorizontal' => 16, 'paddingVertical' => 8 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('horizontal = 16.dp')
      expect(result).to include('vertical = 8.dp')
    end

    it 'generates Button with background color' do
      json_data = { 'type' => 'Button', 'text' => 'Test', 'background' => '#007AFF' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('colors = ButtonDefaults.buttonColors')
      expect(result).to include('containerColor')
      expect(required_imports).to include(:button_colors)
    end

    it 'generates Button with disabledBackground' do
      json_data = { 'type' => 'Button', 'text' => 'Test', 'disabledBackground' => '#CCCCCC' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('disabledContainerColor')
    end

    it 'generates Button with disabledFontColor' do
      json_data = { 'type' => 'Button', 'text' => 'Test', 'disabledFontColor' => '#888888' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('disabledContentColor')
    end

    it 'generates Button with hilightColor comment' do
      json_data = { 'type' => 'Button', 'text' => 'Test', 'hilightColor' => '#FF0000' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('// hilightColor')
    end

    it 'generates Button with enabled false' do
      json_data = { 'type' => 'Button', 'text' => 'Test', 'enabled' => false }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('enabled = false')
    end

    it 'generates Button with enabled true' do
      json_data = { 'type' => 'Button', 'text' => 'Test', 'enabled' => true }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('enabled = true')
    end

    it 'generates Button with enabled data binding' do
      json_data = { 'type' => 'Button', 'text' => 'Test', 'enabled' => '@{isActive}' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('enabled = data.isActive')
    end

    it 'generates Button with fontSize routed through Configuration.Font.resolve(FontSpec(...))' do
      json_data = { 'type' => 'Button', 'text' => 'Test', 'fontSize' => 18 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Configuration.Font.resolve(FontSpec(')
      expect(result).to include('size = 18.sp')
      expect(result).to match(/fontSize = resolved_button\d+\.size \?: TextUnit\.Unspecified/)
    end

    it 'generates Button with fontColor' do
      json_data = { 'type' => 'Button', 'text' => 'Test', 'fontColor' => '#FFFFFF' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('contentColor =')
    end

    it 'generates Text content inside button' do
      json_data = { 'type' => 'Button', 'text' => 'Submit' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include(') {')
      expect(result).to include('Text(')
    end

    it 'uses default text when none provided' do
      json_data = { 'type' => 'Button' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Button')
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

    it 'adds indentation for level 2' do
      result = described_class.send(:indent, 'text', 2)
      expect(result).to eq('        text')
    end
  end

  describe 'event handler invocation' do
    it 'generates invoke() without arguments when handler type is () -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onClick' => { 'name' => 'onClick', 'class' => '(() -> Unit)?' }
      }

      json_data = {
        'type' => 'Button',
        'id' => 'submitButton',
        'text' => 'Submit',
        'onClick' => '@{onClick}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onClick?.invoke()')
      expect(result).not_to include('invoke("submitButton"')
    end

    it 'generates invoke(viewId) when handler type is (Event) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onClick' => { 'name' => 'onClick', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'Button',
        'id' => 'submitButton',
        'text' => 'Submit',
        'onClick' => '@{onClick}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      # For click events without value, only viewId should be passed
      expect(result).to include('data.onClick?.invoke("submitButton")')
      expect(result).not_to include('invoke("submitButton",')
    end

    it 'generates invoke(viewId) when handler type is (String) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onClick' => { 'name' => 'onClick', 'class' => '((String) -> Unit)?' }
      }

      json_data = {
        'type' => 'Button',
        'id' => 'cancelButton',
        'text' => 'Cancel',
        'onClick' => '@{onClick}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onClick?.invoke("cancelButton")')
    end

    it 'uses default button id when no id specified' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onClick' => { 'name' => 'onClick', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'Button',
        'text' => 'Click',
        'onClick' => '@{onClick}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onClick?.invoke("button")')
    end

    it 'generates error comment for camelCase onClick without binding format' do
      json_data = {
        'type' => 'Button',
        'text' => 'Click',
        'onClick' => 'handleClick'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('ERROR')
      expect(result).to include('camelCase events require binding format')
    end
  end

  describe 'onLongPress (inner-clickable trap)' do
    # Button has its own inner clickable that consumes the down event in the
    # Main pass, so plain detectTapGestures on the outer modifier is starved.
    # The emit must watch the Initial pass (mirrors dynamic
    # ModifierBuilder.applyLongPressable) instead of combinedClickable.
    it 'emits an Initial-pass pointerInput long-press detector on the Button modifier' do
      json_data = {
        'type' => 'Button',
        'id' => 'submit_button',
        'text' => 'Submit',
        'onClick' => '@{onSubmit}',
        'onLongPress' => '@{onSubmitLongPress}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      # Native onClick stays on the Button parameter
      expect(result).to include('onClick = { data.onSubmit?.invoke() }')
      # Long press rides the modifier chain with Initial-pass detection
      expect(result).to include('.pointerInput(data) {')
      expect(result).to include('awaitFirstDown(requireUnconsumed = false, pass = PointerEventPass.Initial)')
      expect(result).to include('withTimeout(viewConfiguration.longPressTimeoutMillis)')
      expect(result).to include('data.onSubmitLongPress?.invoke()')
      expect(result).to include('it.consume()')
      expect(required_imports).to include(:long_press_gesture)
    end

    it 'emits the long-press detector even without onClick' do
      json_data = {
        'type' => 'Button',
        'text' => 'Hold',
        'onLongPress' => '@{onHold}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('onClick = { }')
      expect(result).to include('.pointerInput(data) {')
      expect(result).to include('data.onHold?.invoke()')
    end

    it 'does not emit pointerInput without onLongPress' do
      json_data = { 'type' => 'Button', 'text' => 'Plain', 'onClick' => '@{onTap}' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).not_to include('.pointerInput')
    end
  end
end
