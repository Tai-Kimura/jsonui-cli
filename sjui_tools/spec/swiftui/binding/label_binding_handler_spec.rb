# frozen_string_literal: true

require 'swiftui/binding/handlers/label_binding_handler'

RSpec.describe SjuiTools::SwiftUI::Binding::LabelBindingHandler do
  let(:handler) { described_class.new }

  describe '#handle_specific_binding' do
    it 'returns nil for text binding' do
      component = { 'type' => 'Label', 'text' => '@{labelText}' }
      result = handler.handle_specific_binding(component, 'text', '@{labelText}')

      expect(result).to be_nil
    end

    it 'handles fontColor binding' do
      component = { 'type' => 'Label', 'fontColor' => '@{textColor}' }
      result = handler.handle_specific_binding(component, 'fontColor', '@{textColor}')

      expect(result).to include('.foregroundColor(')
    end

    it 'handles fontSize binding' do
      component = { 'type' => 'Label', 'fontSize' => '@{size}' }
      result = handler.handle_specific_binding(component, 'fontSize', '@{size}')

      expect(result).to include('.font(.system(size:')
    end

    it 'handles font binding' do
      component = { 'type' => 'Label', 'font' => '@{fontWeight}' }
      result = handler.handle_specific_binding(component, 'font', '@{fontWeight}')

      expect(result).to include('.fontWeight(')
    end

    it 'returns nil for unknown key' do
      component = { 'type' => 'Label' }
      result = handler.handle_specific_binding(component, 'unknown', '@{value}')

      expect(result).to be_nil
    end
  end

  describe '#get_text_content' do
    it 'returns interpolated string for binding' do
      component = { 'text' => '@{userName}' }
      result = handler.get_text_content(component)

      expect(result).to include('userName')
      expect(result).to include('\\(')
    end

    it 'returns quoted string for static text' do
      component = { 'text' => 'Hello World' }
      result = handler.get_text_content(component)

      expect(result).to eq('"Hello World"')
    end

    it 'handles text with embedded bindings' do
      component = { 'text' => 'Hello @{name}!' }
      result = handler.get_text_content(component)

      expect(result).to include('Hello')
      expect(result).to include('data.name')
    end

    it 'escapes quotes in text' do
      component = { 'text' => 'Say "Hello"' }
      result = handler.get_text_content(component)

      expect(result).to include('\\"')
    end

    it 'escapes newlines in text' do
      component = { 'text' => "Line1\nLine2" }
      result = handler.get_text_content(component)

      expect(result).to include('\\n')
    end

    it 'returns empty string for nil text' do
      component = {}
      result = handler.get_text_content(component)

      expect(result).to eq('""')
    end

    it 'handles multiple embedded bindings' do
      component = { 'text' => '@{firstName} @{lastName}' }
      result = handler.get_text_content(component)

      expect(result).to include('firstName')
      expect(result).to include('lastName')
    end

    context 'with data_definitions for optional/non-optional' do
      after(:each) do
        SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {}
      end

      it 'returns binding with ?? "" for optional property (no defaultValue)' do
        # Property without defaultValue is optional
        SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
          'userName' => { 'name' => 'userName', 'class' => 'String' }
        }
        component = { 'text' => '@{userName}' }
        result = handler.get_text_content(component)

        expect(result).to include('data.userName ?? ""')
      end

      it 'returns binding without ?? for non-optional property (with defaultValue)' do
        # Property with defaultValue is non-optional
        SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
          'userName' => { 'name' => 'userName', 'class' => 'String', 'defaultValue' => 'Guest' }
        }
        component = { 'text' => '@{userName}' }
        result = handler.get_text_content(component)

        expect(result).to include('data.userName')
        expect(result).not_to include('?? ""')
      end

      it 'handles embedded binding with ?? "" for optional' do
        SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
          'name' => { 'name' => 'name', 'class' => 'String' }
        }
        component = { 'text' => 'Hello @{name}!' }
        result = handler.get_text_content(component)

        # The ?? "" is escaped as \\\"\\\"
        expect(result).to include('data.name ?? \\"\\"')
      end

      it 'handles embedded binding without ?? for non-optional' do
        SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
          'name' => { 'name' => 'name', 'class' => 'String', 'defaultValue' => 'World' }
        }
        component = { 'text' => 'Hello @{name}!' }
        result = handler.get_text_content(component)

        expect(result).to include('data.name)')
        expect(result).not_to include('?? ""')
      end
    end
  end
end
