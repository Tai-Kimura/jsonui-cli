# frozen_string_literal: true

require 'compose/components/scrollview_component'
require 'compose/helpers/modifier_builder'

RSpec.describe KjuiTools::Compose::Components::ScrollViewComponent do
  let(:required_imports) { Set.new }

  describe '.generate' do
    it 'generates vertical LazyColumn by default' do
      json_data = { 'type' => 'ScrollView' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('LazyColumn(')
      expect(required_imports).to include(:lazy_column)
    end

    it 'generates horizontal LazyRow when horizontalScroll is true' do
      json_data = { 'type' => 'ScrollView', 'horizontalScroll' => true }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('LazyRow(')
      expect(required_imports).to include(:lazy_row)
    end

    it 'generates horizontal LazyRow when orientation is horizontal' do
      json_data = { 'type' => 'ScrollView', 'orientation' => 'horizontal' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('LazyRow(')
    end

    it 'returns children for parent to process' do
      json_data = { 
        'type' => 'ScrollView', 
        'child' => [{ 'type' => 'Text', 'text' => 'Hello' }] 
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:children]).to be_an(Array)
      expect(result[:children].first['type']).to eq('Text')
    end

    it 'returns closing braces' do
      json_data = { 'type' => 'ScrollView' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:closing]).to include('}')
    end

    it 'handles single child as array' do
      json_data = { 
        'type' => 'ScrollView', 
        'child' => { 'type' => 'Text', 'text' => 'Single' } 
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:children]).to be_an(Array)
    end

    it 'detects horizontal from child View orientation' do
      json_data = {
        'type' => 'ScrollView',
        'child' => [{ 'type' => 'View', 'orientation' => 'horizontal' }]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('LazyRow(')
    end

    context 'keyboardAvoidance' do
      it 'adds imePadding by default' do
        json_data = { 'type' => 'ScrollView' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result[:code]).to include('.imePadding()')
        expect(required_imports).to include(:ime_padding)
      end

      it 'adds imePadding when keyboardAvoidance is true' do
        json_data = { 'type' => 'ScrollView', 'keyboardAvoidance' => true }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result[:code]).to include('.imePadding()')
        expect(required_imports).to include(:ime_padding)
      end

      it 'does not add imePadding when keyboardAvoidance is false' do
        json_data = { 'type' => 'ScrollView', 'keyboardAvoidance' => false }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result[:code]).not_to include('imePadding()')
        expect(required_imports).not_to include(:ime_padding)
      end

      it 'works with horizontal scroll and keyboardAvoidance disabled' do
        json_data = {
          'type' => 'ScrollView',
          'horizontalScroll' => true,
          'keyboardAvoidance' => false
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result[:code]).to include('LazyRow(')
        expect(result[:code]).not_to include('imePadding()')
      end
    end
  end
end
