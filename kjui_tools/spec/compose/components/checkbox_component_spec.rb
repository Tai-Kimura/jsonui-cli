# frozen_string_literal: true

require 'compose/components/checkbox_component'
require 'compose/helpers/resource_resolver'

RSpec.describe KjuiTools::Compose::Components::CheckboxComponent do
  let(:required_imports) { Set.new }

  before do
    # Clear data definitions before each test
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  describe '.generate' do
    it 'generates basic Checkbox component' do
      json_data = { 'type' => 'Checkbox' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Checkbox(')
    end

    it 'generates Checkbox with checked state' do
      json_data = { 'type' => 'Checkbox', 'checked' => true }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('checked')
    end

    it 'generates Checkbox with binding' do
      json_data = { 'type' => 'Checkbox', 'checked' => '@{isSelected}' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('checked')
    end

    it 'generates Checkbox with onChange handler' do
      json_data = { 'type' => 'Checkbox', 'onChange' => 'handleCheck' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('onCheckedChange')
    end

    it 'adds checkbox_colors import when checkColor specified' do
      json_data = { 'type' => 'Checkbox', 'checkColor' => '#007AFF' }
      described_class.generate(json_data, 0, required_imports)
      expect(required_imports).to include(:checkbox_colors)
    end
  end

  describe 'event handler invocation' do
    it 'generates invoke() without arguments when handler type is () -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onCheck' => { 'name' => 'onCheck', 'class' => '(() -> Unit)?' }
      }

      json_data = {
        'type' => 'Checkbox',
        'id' => 'myCheckbox',
        'checked' => '@{isSelected}',
        'onValueChange' => '@{onCheck}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onCheck?.invoke()')
      expect(result).not_to include('invoke("myCheckbox"')
    end

    it 'generates invoke(viewId, value) when handler type is (Event) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onCheck' => { 'name' => 'onCheck', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'Checkbox',
        'id' => 'myCheckbox',
        'checked' => '@{isSelected}',
        'onValueChange' => '@{onCheck}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onCheck?.invoke("myCheckbox", it)')
    end

    it 'generates invoke(viewId, value) when handler type is (String, Boolean) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onCheck' => { 'name' => 'onCheck', 'class' => '((String, Boolean) -> Unit)?' }
      }

      json_data = {
        'type' => 'Checkbox',
        'id' => 'termsCheckbox',
        'onValueChange' => '@{onCheck}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onCheck?.invoke("termsCheckbox", it)')
    end

    it 'includes both viewModel.updateData and handler invocation when both binding and handler exist' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onCheck' => { 'name' => 'onCheck', 'class' => '((String, Boolean) -> Unit)?' }
      }

      json_data = {
        'type' => 'Checkbox',
        'id' => 'myCheckbox',
        'checked' => '@{isSelected}',
        'onValueChange' => '@{onCheck}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('viewModel.updateData')
      expect(result).to include('data.onCheck?.invoke("myCheckbox", it)')
    end

    it 'uses default checkbox id when no id specified' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onCheck' => { 'name' => 'onCheck', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'Checkbox',
        'onValueChange' => '@{onCheck}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onCheck?.invoke("checkbox", it)')
    end
  end
  # The custom-icon path called ResourceResolver.process_drawable, which does not
  # exist — any layout naming a checkbox icon crashed codegen with NoMethodError.
  describe 'custom icon path' do
    it 'resolves drawables instead of crashing' do
      expect {
        described_class.generate({ 'type' => 'CheckBox', 'icon' => 'off_img' }, 0, Set.new)
      }.not_to raise_error
    end

    it 'emits painterResource with an id argument' do
      code = described_class.generate(
        { 'type' => 'CheckBox', 'icon' => 'off_img', 'selectedIcon' => 'on_img' }, 0, Set.new
      )
      expect(code).to include('painterResource(id = if (')
      expect(code).to include('R.drawable.on_img')
      expect(code).to include('R.drawable.off_img')
    end

    # R.drawable.check_box does not exist in the app, so the unnamed state has to
    # fall back to the asset the layout did name.
    it 'falls back to the other asset, never to a Material icon name' do
      code = described_class.generate({ 'type' => 'CheckBox', 'icon' => 'off_img' }, 0, Set.new)
      expect(code).not_to include('check_box')
      expect(code.scan('R.drawable.off_img').length).to eq(2)
    end

    it 'sizes and tints the glyph' do
      code = described_class.generate({
        'type' => 'CheckBox', 'icon' => 'off_img', 'iconSize' => 28, 'iconColor' => '#00FF00'
      }, 0, Set.new)
      expect(code).to include('modifier = Modifier.size(28.dp)')
      expect(code).to include('tint = ')
      expect(code).to include('#00FF00')
    end

    it 'keeps fontColor as the tint fallback it has always been' do
      code = described_class.generate({
        'type' => 'CheckBox', 'icon' => 'off_img', 'fontColor' => '#123456'
      }, 0, Set.new)
      expect(code).to include('#123456')
    end
  end

  describe 'Material checkbox appearance' do
    # For a Material Checkbox the "icon" is the tick.
    it 'maps iconColor to checkmarkColor' do
      code = described_class.generate({ 'type' => 'CheckBox', 'iconColor' => '#FF0000' }, 0, Set.new)
      expect(code).to include('CheckboxDefaults.colors(')
      expect(code).to include('checkmarkColor = ')
    end

    # With no custom glyph there is nothing to size but the control itself.
    it 'sizes the control when iconSize is given without an icon' do
      code = described_class.generate({ 'type' => 'CheckBox', 'iconSize' => 32 }, 0, Set.new)
      expect(code).to include('.size(32.dp)')
    end
  end
end
