# frozen_string_literal: true

require 'swiftui/views/blur_converter'

RSpec.describe SjuiTools::SwiftUI::Views::BlurConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'with no children' do
      let(:component) { { 'type' => 'Blur' } }

      it 'generates Color.clear as placeholder' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Color.clear')
        expect(code).to include('.background(.ultraThinMaterial)')
      end
    end

    context 'with regular style' do
      let(:component) do
        {
          'type' => 'Blur',
          'style' => 'regular'
        }
      end

      it 'applies ultraThinMaterial background' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.background(.ultraThinMaterial)')
      end
    end

    context 'with dark style' do
      let(:component) do
        {
          'type' => 'Blur',
          'style' => 'dark'
        }
      end

      it 'adds dark color scheme' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.preferredColorScheme(.dark)')
      end
    end

    context 'with light style' do
      let(:component) do
        {
          'type' => 'Blur',
          'style' => 'light'
        }
      end

      it 'adds light color scheme' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.preferredColorScheme(.light)')
      end
    end

    context 'with common modifiers' do
      let(:component) do
        {
          'type' => 'Blur',
          'cornerRadius' => 12,
          'alpha' => 0.8
        }
      end

      it 'applies common modifiers' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.cornerRadius(12)')
        expect(code).to include('.opacity(0.8)')
      end
    end
  end
end
