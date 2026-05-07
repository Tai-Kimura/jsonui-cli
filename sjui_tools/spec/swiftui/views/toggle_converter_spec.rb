# frozen_string_literal: true

require 'swiftui/views/toggle_converter'

RSpec.describe SjuiTools::SwiftUI::Views::ToggleConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'with basic toggle' do
      let(:component) do
        {
          'type' => 'Toggle',
          'isOn' => '@{isEnabled}'
        }
      end

      it 'generates Toggle view' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Toggle(')
      end

      it 'uses binding for isOn' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('isOn:')
        expect(code).to include('data.isEnabled')
      end
    end

    context 'with text/label' do
      let(:component) do
        {
          'type' => 'Toggle',
          'isOn' => '@{notifications}',
          'text' => 'Enable Notifications'
        }
      end

      it 'includes text in Toggle' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Text("Enable Notifications")')
      end
    end

    context 'with label alias' do
      let(:component) do
        {
          'type' => 'Toggle',
          'isOn' => '@{notifications}',
          'label' => 'Enable Notifications'
        }
      end

      it 'uses label as text' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Text("Enable Notifications")')
      end
    end

    context 'with toggleStyle switch' do
      let(:component) do
        {
          'type' => 'Toggle',
          'isOn' => '@{isOn}',
          'toggleStyle' => 'switch'
        }
      end

      it 'adds SwitchToggleStyle' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.toggleStyle(SwitchToggleStyle())')
      end
    end

    context 'with toggleStyle button' do
      let(:component) do
        {
          'type' => 'Toggle',
          'isOn' => '@{isOn}',
          'toggleStyle' => 'button'
        }
      end

      it 'adds ButtonToggleStyle' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.toggleStyle(ButtonToggleStyle())')
      end
    end

    context 'with checked binding' do
      let(:component) do
        {
          'type' => 'Toggle',
          'checked' => '@{isChecked}'
        }
      end

      it 'uses checked as state binding' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Toggle(isOn:')
      end
    end

    context 'with labelAttributes' do
      let(:component) do
        {
          'type' => 'Toggle',
          'isOn' => '@{isOn}',
          'text' => 'Label',
          'labelAttributes' => {
            'fontColor' => '#333333',
            'fontSize' => 16
          }
        }
      end

      it 'applies font modifiers to Text' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.foregroundColor(')
      end
    end

    context 'with fontColor' do
      let(:component) do
        {
          'type' => 'Toggle',
          'isOn' => '@{isOn}',
          'text' => 'Label',
          'fontColor' => '#333333'
        }
      end

      it 'adds foregroundColor modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.foregroundColor(')
      end
    end

    context 'with no binding (uses state variable)' do
      let(:component) do
        {
          'type' => 'Toggle',
          'id' => 'myToggle'
        }
      end

      it 'creates state variable' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('isOn:')
      end

      it 'adds state variable to list' do
        converter = described_class.new(component)
        converter.convert

        expect(converter.state_variables).not_to be_empty
      end
    end

    context 'with background and cornerRadius' do
      let(:component) do
        {
          'type' => 'Toggle',
          'isOn' => '@{isOn}',
          'background' => '#F5F5F5',
          'cornerRadius' => 8
        }
      end

      it 'applies modifiers via apply_modifiers' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.background(')
        expect(code).to include('.cornerRadius(8)')
      end
    end
  end

  describe 'event handler invocation' do
    before do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {}
    end

    it 'generates onValueChange handler with onChange modifier' do
      component = {
        'type' => 'Toggle',
        'id' => 'myToggle',
        'isOn' => '@{isEnabled}',
        'onValueChange' => '@{onToggleChange}'
      }

      converter = described_class.new(component)
      code = converter.convert

      expect(code).to include('.onChange(of: data.isEnabled)')
      expect(code).to include('data.onToggleChange?()')
    end

    it 'generates invoke(viewId, value) when handler type is (String, Bool) -> Void' do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
        'onToggleChange' => { 'name' => 'onToggleChange', 'class' => '((String, Bool) -> Void)?' }
      }

      component = {
        'type' => 'Toggle',
        'id' => 'myToggle',
        'isOn' => '@{isEnabled}',
        'onValueChange' => '@{onToggleChange}'
      }

      converter = described_class.new(component)
      code = converter.convert

      expect(code).to include('data.onToggleChange?("myToggle", newValue)')
    end

    it 'generates invoke() when handler type is () -> Void' do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
        'onToggleChange' => { 'name' => 'onToggleChange', 'class' => '(() -> Void)?' }
      }

      component = {
        'type' => 'Toggle',
        'id' => 'myToggle',
        'isOn' => '@{isEnabled}',
        'onValueChange' => '@{onToggleChange}'
      }

      converter = described_class.new(component)
      code = converter.convert

      expect(code).to include('.onChange(of: data.isEnabled)')
      expect(code).to include('data.onToggleChange?()')
      expect(code).not_to include('onToggleChange?("myToggle"')
    end

    it 'treats onToggle as alias of onValueChange (Bool callback)' do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
        'onAiSearchToggle' => { 'name' => 'onAiSearchToggle', 'class' => '((Bool) -> Void)?' }
      }

      component = {
        'type' => 'Switch',
        'id' => 'settings_ai_search_switch',
        'isOn' => '@{aiSearchEnabled}',
        'onToggle' => '@{onAiSearchToggle}'
      }

      converter = described_class.new(component)
      code = converter.convert

      expect(code).to include('.onChange(of: data.aiSearchEnabled)')
      expect(code).to include('data.onAiSearchToggle?(newValue)')
    end

    it 'prefers onValueChange when both onValueChange and onToggle are set' do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
        'primary'   => { 'name' => 'primary',   'class' => '((Bool) -> Void)?' },
        'secondary' => { 'name' => 'secondary', 'class' => '((Bool) -> Void)?' }
      }

      component = {
        'type' => 'Switch',
        'id' => 'myToggle',
        'isOn' => '@{flag}',
        'onValueChange' => '@{primary}',
        'onToggle' => '@{secondary}'
      }

      converter = described_class.new(component)
      code = converter.convert

      expect(code).to include('data.primary?(newValue)')
      expect(code).not_to include('data.secondary?(')
    end
  end
end
