# frozen_string_literal: true

require 'swiftui/binding/handlers/text_field_binding_handler'

RSpec.describe SjuiTools::SwiftUI::Binding::TextFieldBindingHandler do
  let(:handler) { described_class.new }

  describe '#get_text_binding' do
    context 'with binding expression' do
      let(:component) { { 'text' => '@{userName}' } }

      it 'returns viewModel.data binding' do
        result = handler.get_text_binding(component)
        expect(result).to eq('$data.userName')
      end
    end

    context 'with literal text' do
      let(:component) { { 'text' => 'Hello' } }

      it 'returns constant binding' do
        result = handler.get_text_binding(component)
        expect(result).to eq('.constant("Hello")')
      end
    end

    context 'with empty text' do
      let(:component) { { 'text' => '' } }

      it 'returns constant binding with empty string' do
        result = handler.get_text_binding(component)
        expect(result).to eq('.constant("")')
      end
    end

    context 'with nil text' do
      let(:component) { {} }

      it 'returns constant binding with empty string' do
        result = handler.get_text_binding(component)
        expect(result).to eq('.constant("")')
      end
    end
  end

  describe '#is_secure_field?' do
    context 'with secure = true' do
      let(:component) { { 'secure' => true } }

      it 'returns true' do
        expect(handler.is_secure_field?(component)).to be true
      end
    end

    context 'with secure = "true" (string)' do
      let(:component) { { 'secure' => 'true' } }

      it 'returns true' do
        expect(handler.is_secure_field?(component)).to be true
      end
    end

    context 'with secure = false' do
      let(:component) { { 'secure' => false } }

      it 'returns false' do
        expect(handler.is_secure_field?(component)).to be false
      end
    end

    context 'without secure attribute' do
      let(:component) { {} }

      it 'returns false' do
        expect(handler.is_secure_field?(component)).to be false
      end
    end

    context 'with input = password (no secure attribute)' do
      let(:component) { { 'input' => 'password' } }

      it 'returns true' do
        expect(handler.is_secure_field?(component)).to be true
      end
    end

    context 'with input = password and secure = false (secure takes priority)' do
      let(:component) { { 'input' => 'password', 'secure' => false } }

      it 'returns false' do
        expect(handler.is_secure_field?(component)).to be false
      end
    end

    context 'with input = email (not password)' do
      let(:component) { { 'input' => 'email' } }

      it 'returns false' do
        expect(handler.is_secure_field?(component)).to be false
      end
    end
  end

  describe '#handle_specific_binding' do
    context 'with enabled binding' do
      let(:component) { { 'type' => 'TextField' } }

      # .disabled takes Bool (read-only), so uses data. not $data.
      it 'returns disabled modifier' do
        result = handler.handle_specific_binding(component, 'enabled', '@{isEnabled}')
        expect(result).to eq('.disabled(!data.isEnabled)')
      end
    end

    context 'with text binding' do
      let(:component) { { 'type' => 'TextField' } }

      it 'returns nil (handled in initialization)' do
        result = handler.handle_specific_binding(component, 'text', '@{textValue}')
        expect(result).to be_nil
      end
    end
  end
end
