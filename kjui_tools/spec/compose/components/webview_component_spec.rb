# frozen_string_literal: true

require 'compose/components/webview_component'
require 'compose/helpers/modifier_builder'

RSpec.describe KjuiTools::Compose::Components::WebviewComponent do
  let(:required_imports) { Set.new }

  describe '.generate' do
    it 'generates AndroidView for WebView' do
      json_data = { 'type' => 'WebView' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('AndroidView(')
      expect(result).to include('WebView(context)')
      expect(required_imports).to include(:webview)
    end

    it 'includes static URL' do
      json_data = { 'type' => 'WebView', 'url' => 'https://example.com' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('loadUrl("https://example.com")')
    end

    it 'handles URL binding' do
      json_data = { 'type' => 'WebView', 'url' => '@{pageUrl}' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('loadUrl(data.pageUrl)')
    end

    it 'enables JavaScript by default' do
      json_data = { 'type' => 'WebView' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('javaScriptEnabled = true')
    end

    it 'disables JavaScript when specified' do
      json_data = { 'type' => 'WebView', 'javaScriptEnabled' => false }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('javaScriptEnabled = false')
    end

    it 'sets custom user agent' do
      json_data = { 'type' => 'WebView', 'userAgent' => 'CustomAgent/1.0' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('userAgentString = "CustomAgent/1.0"')
    end

    it 'adds cornerRadius modifier' do
      json_data = { 'type' => 'WebView', 'cornerRadius' => 8 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('RoundedCornerShape(8.dp)')
      expect(required_imports).to include(:shape)
    end
  end
end
