# frozen_string_literal: true

require 'uikit/handlers/label_binding_handler'

RSpec.describe SjuiTools::UIKit::LabelBindingHandler do
  let(:binding_content) { [] }
  let(:reset_text_views) { {} }
  let(:reset_constraint_views) { {} }
  let(:handler) { described_class.new(binding_content, reset_text_views, reset_constraint_views) }

  describe '#handle_specific_binding' do
    it 'handles text' do
      result = handler.handle_specific_binding('label', 'text', 'model.title')

      expect(result).to be true
      expect(reset_text_views['label'][:text]).to eq('model.title')
    end

    it 'handles selected' do
      result = handler.handle_specific_binding('label', 'selected', 'true')

      expect(result).to be true
      expect(binding_content.join).to include('label?.selected = true')
    end

    it 'handles font' do
      result = handler.handle_specific_binding('label', 'font', "'Helvetica-Bold'")

      expect(result).to be true
      expect(binding_content.join).to include('UIFont(name:')
      expect(reset_text_views['label']).not_to be_nil
    end

    it 'handles fontSize' do
      result = handler.handle_specific_binding('label', 'fontSize', '16')

      expect(result).to be true
      expect(binding_content.join).to include('FontName')
      expect(binding_content.join).to include('size: 16')
    end

    it 'handles fontColor' do
      result = handler.handle_specific_binding('label', 'fontColor', 'UIColor.red')

      expect(result).to be true
      expect(binding_content.join).to include('NSAttributedString.Key.foregroundColor')
      expect(binding_content.join).to include('UIColor.red')
    end

    it 'handles highlightColor' do
      result = handler.handle_specific_binding('label', 'highlightColor', 'UIColor.blue')

      expect(result).to be true
      expect(binding_content.join).to include('highlightAttributes')
    end

    it 'handles hintColor' do
      result = handler.handle_specific_binding('label', 'hintColor', 'UIColor.gray')

      expect(result).to be true
      expect(binding_content.join).to include('hintAttributes')
    end

    it 'handles partialAttributes with binding range' do
      partial_attrs = [
        { 'range' => ['@{startIndex}', '@{endIndex}'] }
      ]
      result = handler.handle_specific_binding('label', 'partialAttributes', partial_attrs)

      expect(result).to be true
      expect(binding_content.join).to include('partialAttributesJSON')
    end

    it 'handles partialAttributes with non-binding range' do
      partial_attrs = [
        { 'range' => [0, 5] }
      ]
      result = handler.handle_specific_binding('label', 'partialAttributes', partial_attrs)

      expect(result).to be true
      # Non-binding ranges don't generate output
    end

    it 'handles partialAttributes with !! suffix' do
      partial_attrs = [
        { 'range' => ['@{value!!}'] }
      ]
      result = handler.handle_specific_binding('label', 'partialAttributes', partial_attrs)

      expect(result).to be true
      expect(binding_content.join).not_to include('??')
    end

    it 'returns false for unknown key' do
      result = handler.handle_specific_binding('label', 'unknownKey', 'value')

      expect(result).to be false
    end
  end
end
