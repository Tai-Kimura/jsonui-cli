# frozen_string_literal: true

require 'swiftui/views/web_converter'

RSpec.describe SjuiTools::SwiftUI::Views::WebConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'with static URL' do
      let(:component) do
        {
          'type' => 'Web',
          'url' => 'https://example.com'
        }
      end

      it 'generates WebView with URL' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('WebView(url:')
        expect(code).to include('"https://example.com"')
      end

      # The generator now emits a bare WebView(url:) without an inline reminder comment
      # because the SwiftJsonUI library already provides the WebView implementation.
      it 'emits a plain WebView invocation for the URL' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('WebView(url:')
      end
    end

    context 'with default URL' do
      let(:component) { { 'type' => 'Web' } }

      it 'uses example.com as default' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('https://example.com')
      end
    end

    context 'with binding URL' do
      let(:component) do
        {
          'type' => 'Web',
          'url' => '@{pageUrl}'
        }
      end

      it 'uses data binding' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('data.pageUrl')
      end
    end

    context 'with common modifiers' do
      let(:component) do
        {
          'type' => 'Web',
          'url' => 'https://example.com',
          'cornerRadius' => 8
        }
      end

      it 'applies common modifiers' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.cornerRadius(8)')
      end
    end
  end
end
