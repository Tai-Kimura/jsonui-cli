# frozen_string_literal: true

require 'swiftui/helpers/string_manager_helper'

RSpec.describe SjuiTools::SwiftUI::Helpers::StringManagerHelper do
  # Create a test class that includes the helper
  let(:helper_instance) do
    Class.new do
      include SjuiTools::SwiftUI::Helpers::StringManagerHelper
    end.new
  end

  describe '#get_text_with_string_manager' do
    context 'with snake_case text' do
      it 'returns localized string for simple snake_case' do
        result = helper_instance.get_text_with_string_manager('"hello_world"')
        expect(result).to eq('"hello_world".localized()')
      end

      it 'returns localized string for snake_case with numbers' do
        result = helper_instance.get_text_with_string_manager('"item_count_3"')
        expect(result).to eq('"item_count_3".localized()')
      end

      it 'returns localized string for single word' do
        result = helper_instance.get_text_with_string_manager('"settings"')
        expect(result).to eq('"settings".localized()')
      end
    end

    context 'with regular text (not snake_case)' do
      it 'returns original text for CamelCase' do
        result = helper_instance.get_text_with_string_manager('"HelloWorld"')
        expect(result).to eq('"HelloWorld"')
      end

      it 'returns original text with spaces' do
        result = helper_instance.get_text_with_string_manager('"Hello World"')
        expect(result).to eq('"Hello World"')
      end

      it 'returns original text with uppercase' do
        result = helper_instance.get_text_with_string_manager('"HELLO"')
        expect(result).to eq('"HELLO"')
      end

      it 'returns original text starting with uppercase' do
        result = helper_instance.get_text_with_string_manager('"Hello_world"')
        expect(result).to eq('"Hello_world"')
      end
    end

    context 'with binding expression' do
      it 'returns original binding' do
        result = helper_instance.get_text_with_string_manager('"@{userName}"')
        expect(result).to eq('"@{userName}"')
      end

      it 'handles binding without quotes' do
        result = helper_instance.get_text_with_string_manager('@{userName}')
        expect(result).to eq('@{userName}')
      end
    end

    context 'with single quotes' do
      it 'processes single-quoted snake_case' do
        result = helper_instance.get_text_with_string_manager("'hello_world'")
        expect(result).to eq('"hello_world".localized()')
      end
    end

    context 'edge cases' do
      it 'handles empty string' do
        result = helper_instance.get_text_with_string_manager('""')
        expect(result).to eq('""')
      end

      it 'handles string with only underscores' do
        result = helper_instance.get_text_with_string_manager('"___"')
        expect(result).to eq('"___"')
      end

      it 'handles numbers only' do
        result = helper_instance.get_text_with_string_manager('"123"')
        expect(result).to eq('"123"')
      end
    end
  end
end
