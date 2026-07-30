# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/web_converter'

RSpec.describe RjuiTools::React::Converters::WebConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'basic web view with url' do
      it 'generates iframe with src' do
        converter = create_converter({ 'class' => 'Web', 'url' => 'https://example.com' })
        result = converter.convert
        expect(result).to include('<iframe')
        expect(result).to include('src="https://example.com"')
        expect(result).to include('border-0')
      end
    end

    context 'with url binding' do
      it 'generates dynamic src' do
        converter = create_converter({ 'class' => 'Web', 'url' => '@{pageUrl}' })
        result = converter.convert
        expect(result).to include('src={data.pageUrl}')
      end
    end

    context 'with html content' do
      it 'generates srcDoc' do
        converter = create_converter({ 'class' => 'Web', 'html' => '<h1>Hello</h1>' })
        result = converter.convert
        expect(result).to include('srcDoc="<h1>Hello</h1>"')
      end
    end

    context 'with html binding' do
      it 'generates dynamic srcDoc' do
        converter = create_converter({ 'class' => 'Web', 'html' => '@{htmlContent}' })
        result = converter.convert
        expect(result).to include('srcDoc={data.htmlContent}')
      end
    end

    context 'with javaScriptEnabled false' do
      it 'excludes allow-scripts from sandbox' do
        converter = create_converter({ 'class' => 'Web', 'url' => 'https://example.com', 'javaScriptEnabled' => false })
        result = converter.convert
        expect(result).not_to include('allow-scripts')
      end
    end

    context 'with javaScriptCanOpenWindowsAutomatically' do
      it 'includes allow-popups in sandbox' do
        converter = create_converter({ 'class' => 'Web', 'url' => 'https://example.com', 'javaScriptCanOpenWindowsAutomatically' => true })
        result = converter.convert
        expect(result).to include('allow-popups')
      end
    end

    context 'with allowsInlineMediaPlayback' do
      it 'includes autoplay in allow' do
        converter = create_converter({ 'class' => 'Web', 'url' => 'https://example.com', 'allowsInlineMediaPlayback' => true })
        result = converter.convert
        expect(result).to include('allow="autoplay')
      end
    end

    context 'with allowCamera and allowMicrophone' do
      it 'includes camera and microphone in allow' do
        converter = create_converter({ 'class' => 'Web', 'url' => 'https://example.com', 'allowCamera' => true, 'allowMicrophone' => true })
        result = converter.convert
        expect(result).to include('camera')
        expect(result).to include('microphone')
      end
    end

    context 'with title/accessibilityLabel' do
      it 'includes title attribute' do
        converter = create_converter({ 'class' => 'Web', 'url' => 'https://example.com', 'title' => 'External Content' })
        result = converter.convert
        expect(result).to include('title="External Content"')
      end
    end

    context 'with lazyLoad' do
      it 'includes loading="lazy"' do
        converter = create_converter({ 'class' => 'Web', 'url' => 'https://example.com', 'lazyLoad' => true })
        result = converter.convert
        expect(result).to include('loading="lazy"')
      end
    end

    context 'with scrollEnabled false' do
      it 'adds overflow-hidden class' do
        converter = create_converter({ 'class' => 'Web', 'url' => 'https://example.com', 'scrollEnabled' => false })
        result = converter.convert
        expect(result).to include('overflow-hidden')
      end
    end

    context 'with testId' do
      it 'generates data-testid attribute' do
        converter = create_converter({ 'class' => 'Web', 'url' => 'https://example.com', 'testId' => 'iframe-content' })
        result = converter.convert
        expect(result).to include('data-testid="iframe-content"')
      end
    end

    context 'with visibility binding' do
      it 'wraps with conditional rendering' do
        converter = create_converter({ 'class' => 'Web', 'url' => 'https://example.com', 'visibility' => '@{showWebView}' })
        result = converter.convert
        expect(result).to include('{data.showWebView !== "gone" &&')
      end
    end
  end
  describe 'allow' do
    # The declared attribute is a raw feature-policy string; the convenience
    # flags are undeclared conveniences that top it up rather than replace it.
    it 'emits the declared policy tokens' do
      result = create_converter({ 'type' => 'Web', 'allow' => 'clipboard-write; payment' }).convert
      expect(result).to include('clipboard-write')
      expect(result).to include('payment')
    end

    it 'unions with the derived tokens without duplicating them' do
      result = create_converter({
        'type' => 'Web', 'allow' => 'fullscreen; camera', 'allowCamera' => true
      }).convert
      allow_value = result[/allow="([^"]*)"/, 1]

      expect(allow_value.scan('camera').length).to eq(1)
      expect(allow_value.scan('fullscreen').length).to eq(1)
    end

    it 'still derives from the flags when allow is absent' do
      result = create_converter({ 'type' => 'Web', 'allowGeolocation' => true }).convert
      expect(result).to include('geolocation')
    end
  end
end
