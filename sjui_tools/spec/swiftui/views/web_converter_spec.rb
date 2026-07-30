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
  describe 'html and the WKWebView flags' do
    def generated(component)
      described_class.new(component, 0, nil).convert
    end

    # `url` takes precedence in the component, so the placeholder default has to
    # stand down when html is the only content — otherwise example.com wins and
    # the HTML never renders.
    it 'passes html and no url when only html is given' do
      code = generated({ 'type' => 'Web', 'html' => '<b>hi</b>' })
      expect(code).to include('url: nil')
      expect(code).to include('html: "<b>hi</b>"')
    end

    it 'keeps the placeholder url only when there is nothing at all to show' do
      expect(generated({ 'type' => 'Web' })).to include('https://example.com')
    end

    it 'escapes quotes in html so the Swift literal stays valid' do
      code = generated({ 'type' => 'Web', 'html' => '<a title="x">' })
      expect(code).to include('\\"x\\"')
    end

    it 'emits the flags only when declared, leaving WebKit defaults otherwise' do
      with = generated({
        'type' => 'Web', 'url' => 'https://a.test',
        'allowsLinkPreview' => false, 'allowsBackForwardNavigationGestures' => false
      })
      expect(with).to include('allowsLinkPreview: false')
      expect(with).to include('allowsBackForwardNavigationGestures: false')

      without = generated({ 'type' => 'Web', 'url' => 'https://a.test' })
      expect(without).not_to include('allowsLinkPreview')
      expect(without).not_to include('allowsBackForwardNavigationGestures')
    end

    it 'leaves the url-only form unchanged' do
      expect(generated({ 'type' => 'Web', 'url' => 'https://a.test' }))
        .to eq('WebView(url: URL(string: "https://a.test"))')
    end
  end
end
