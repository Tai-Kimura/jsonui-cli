# frozen_string_literal: true

require 'swiftui/views/view_converter'
require 'swiftui/converter_factory'
require 'swiftui/view_registry'

RSpec.describe SjuiTools::SwiftUI::Views::ViewConverter, 'responsive integration' do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  let(:binding_registry) { SjuiTools::SwiftUI::Binding::BindingHandlerRegistry.new }
  let(:converter_factory) { SjuiTools::SwiftUI::ConverterFactory.new(binding_registry) }
  let(:view_registry) { SjuiTools::SwiftUI::ViewRegistry.new }

  describe '#convert with responsive container' do
    let(:component) do
      {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 8,
        'responsive' => {
          'regular' => { 'orientation' => 'horizontal', 'spacing' => 24 }
        },
        'child' => [
          { 'type' => 'Label', 'text' => 'Hello' },
          { 'type' => 'Label', 'text' => 'World' }
        ]
      }
    end

    it 'generates a function call instead of inline stack' do
      converter = described_class.new(
        component, 0, nil, converter_factory, view_registry, binding_registry
      )
      code = converter.convert

      # Should reference the responsive function, not generate HStack/VStack inline
      expect(code).to include('responsive0 {')
      expect(code).not_to include('VStack(alignment:')
      expect(code).not_to include('HStack(alignment:')
    end

    it 'still renders children inline' do
      converter = described_class.new(
        component, 0, nil, converter_factory, view_registry, binding_registry
      )
      code = converter.convert

      # Children should still appear in the generated code
      expect(code).to include('PartialAttributedText(')
    end

    it 'registers a responsive function in the converter_factory' do
      converter = described_class.new(
        component, 0, nil, converter_factory, view_registry, binding_registry
      )
      converter.convert

      expect(converter_factory.responsive_functions.length).to eq(1)
      func_code = converter_factory.responsive_functions.first
      expect(func_code).to include('private func responsive0<Content: View>')
      expect(func_code).to include('content()')
    end

    it 'increments the responsive counter' do
      converter = described_class.new(
        component, 0, nil, converter_factory, view_registry, binding_registry
      )
      converter.convert

      expect(converter_factory.responsive_counter).to eq(1)
    end
  end

  describe '#convert without responsive' do
    let(:component) do
      {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 8,
        'child' => [
          { 'type' => 'Label', 'text' => 'Hello' }
        ]
      }
    end

    it 'generates normal VStack code (no responsive function)' do
      converter = described_class.new(
        component, 0, nil, converter_factory, view_registry, binding_registry
      )
      code = converter.convert

      expect(code).to include('VStack(alignment:')
      expect(code).not_to include('responsive0')
      expect(converter_factory.responsive_functions).to be_empty
    end
  end

  describe '#convert responsive with background on parent' do
    let(:component) do
      {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 8,
        'background' => '#FFFFFF',
        'responsive' => {
          'regular' => { 'orientation' => 'horizontal', 'spacing' => 24 }
        },
        'child' => [
          { 'type' => 'Label', 'text' => 'Hello' }
        ]
      }
    end

    it 'applies non-responsive modifiers like background' do
      converter = described_class.new(
        component, 0, nil, converter_factory, view_registry, binding_registry
      )
      code = converter.convert

      # Background is not overridden by responsive, so it should be applied
      expect(code).to include('.background(')
    end
  end

  describe 'multiple responsive components' do
    it 'assigns unique function names' do
      component1 = {
        'type' => 'View',
        'orientation' => 'vertical',
        'responsive' => { 'regular' => { 'orientation' => 'horizontal' } },
        'child' => [{ 'type' => 'Label', 'text' => 'A' }]
      }
      component2 = {
        'type' => 'View',
        'orientation' => 'vertical',
        'responsive' => { 'regular' => { 'orientation' => 'horizontal' } },
        'child' => [{ 'type' => 'Label', 'text' => 'B' }]
      }

      c1 = described_class.new(component1, 0, nil, converter_factory, view_registry, binding_registry)
      c1.convert

      c2 = described_class.new(component2, 0, nil, converter_factory, view_registry, binding_registry)
      c2.convert

      expect(converter_factory.responsive_functions.length).to eq(2)
      expect(converter_factory.responsive_functions[0]).to include('responsive0')
      expect(converter_factory.responsive_functions[1]).to include('responsive1')
    end
  end
end
