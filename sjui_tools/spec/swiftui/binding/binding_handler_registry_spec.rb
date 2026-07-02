# frozen_string_literal: true

require 'swiftui/binding/binding_handler_registry'

RSpec.describe SjuiTools::SwiftUI::Binding::BindingHandlerRegistry do
  let(:registry) { described_class.new }

  describe '#initialize' do
    it 'registers default handlers' do
      # Text components
      expect(registry.get_handler('Label')).to be_a(SjuiTools::SwiftUI::Binding::LabelBindingHandler)
      expect(registry.get_handler('Text')).to be_a(SjuiTools::SwiftUI::Binding::LabelBindingHandler)

      # Input components
      expect(registry.get_handler('TextField')).to be_a(SjuiTools::SwiftUI::Binding::TextFieldBindingHandler)
      expect(registry.get_handler('SecureField')).to be_a(SjuiTools::SwiftUI::Binding::TextFieldBindingHandler)
      expect(registry.get_handler('TextView')).to be_a(SjuiTools::SwiftUI::Binding::TextFieldBindingHandler)
      # EditText / Input are aliases for TextField (attribute_definitions `_alias_of: TextField`)
      expect(registry.get_handler('EditText')).to be_a(SjuiTools::SwiftUI::Binding::TextFieldBindingHandler)
      expect(registry.get_handler('Input')).to be_a(SjuiTools::SwiftUI::Binding::TextFieldBindingHandler)

      # Button
      expect(registry.get_handler('Button')).to be_a(SjuiTools::SwiftUI::Binding::ButtonBindingHandler)

      # Toggle
      expect(registry.get_handler('Toggle')).to be_a(SjuiTools::SwiftUI::Binding::ToggleBindingHandler)
      expect(registry.get_handler('Switch')).to be_a(SjuiTools::SwiftUI::Binding::ToggleBindingHandler)

      # CheckBox
      expect(registry.get_handler('Check')).to be_a(SjuiTools::SwiftUI::Binding::CheckboxBindingHandler)
      expect(registry.get_handler('CheckBox')).to be_a(SjuiTools::SwiftUI::Binding::CheckboxBindingHandler)

      # Image
      expect(registry.get_handler('Image')).to be_a(SjuiTools::SwiftUI::Binding::ImageBindingHandler)
      expect(registry.get_handler('NetworkImage')).to be_a(SjuiTools::SwiftUI::Binding::ImageBindingHandler)
    end
  end

  describe '#get_handler' do
    context 'with registered component type' do
      it 'returns correct handler for Label' do
        handler = registry.get_handler('Label')
        expect(handler).to be_a(SjuiTools::SwiftUI::Binding::LabelBindingHandler)
      end

      it 'is case-insensitive' do
        handler1 = registry.get_handler('LABEL')
        handler2 = registry.get_handler('label')

        expect(handler1).to be_a(SjuiTools::SwiftUI::Binding::LabelBindingHandler)
        expect(handler2).to be_a(SjuiTools::SwiftUI::Binding::LabelBindingHandler)
      end
    end

    context 'with unregistered component type' do
      it 'returns base ViewBindingHandler' do
        handler = registry.get_handler('UnknownComponent')
        expect(handler).to be_a(SjuiTools::SwiftUI::Binding::ViewBindingHandler)
      end
    end
  end

  describe '#register_handler' do
    let(:custom_handler_class) do
      Class.new(SjuiTools::SwiftUI::Binding::ViewBindingHandler)
    end

    it 'registers custom handler' do
      registry.register_handler('CustomView', custom_handler_class)

      handler = registry.get_handler('CustomView')
      expect(handler).to be_a(custom_handler_class)
    end

    it 'overrides existing handler' do
      registry.register_handler('Label', custom_handler_class)

      handler = registry.get_handler('Label')
      expect(handler).to be_a(custom_handler_class)
    end
  end
end
