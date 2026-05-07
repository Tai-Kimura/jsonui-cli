# frozen_string_literal: true

require 'compose/components/web_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'

RSpec.describe KjuiTools::Compose::Components::WebComponent do
  let(:required_imports) { Set.new }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
  end

  describe '.generate' do
    it 'generates AndroidView with WebView factory' do
      json_data = { 'type' => 'Web' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('AndroidView(')
      expect(result).to include('factory = { context ->')
      expect(result).to include('WebView(context).apply {')
      expect(required_imports).to include(:webview)
    end

    it 'generates WebView with static url' do
      json_data = { 'type' => 'Web', 'url' => 'https://example.com' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('loadUrl("https://example.com")')
    end

    it 'generates WebView with data binding url' do
      json_data = { 'type' => 'Web', 'url' => '@{webUrl}' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('loadUrl(data.webUrl)')
      expect(result).to include('update = { webView ->')
      expect(result).to include('webView.loadUrl(data.webUrl)')
    end

    it 'generates WebView with empty url when not provided' do
      json_data = { 'type' => 'Web' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('loadUrl("")')
    end

    it 'enables JavaScript by default' do
      json_data = { 'type' => 'Web' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('settings.javaScriptEnabled = true')
    end

    it 'disables JavaScript when javaScriptEnabled is false' do
      json_data = { 'type' => 'Web', 'javaScriptEnabled' => false }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('settings.javaScriptEnabled = false')
    end

    it 'includes WebChromeClient when JavaScript enabled' do
      json_data = { 'type' => 'Web', 'javaScriptEnabled' => true }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('webChromeClient = WebChromeClient()')
    end

    it 'excludes WebChromeClient when JavaScript disabled' do
      json_data = { 'type' => 'Web', 'javaScriptEnabled' => false }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).not_to include('webChromeClient')
    end

    it 'sets userAgent when provided' do
      json_data = { 'type' => 'Web', 'userAgent' => 'CustomAgent/1.0' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('settings.userAgentString = "CustomAgent/1.0"')
    end

    it 'enables zoom controls when allowZoom is true' do
      json_data = { 'type' => 'Web', 'allowZoom' => true }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('settings.builtInZoomControls = true')
      expect(result).to include('settings.displayZoomControls = false')
    end

    it 'always includes WebViewClient' do
      json_data = { 'type' => 'Web' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('webViewClient = WebViewClient()')
    end

    context 'modifiers' do
      it 'uses fillMaxSize by default' do
        json_data = { 'type' => 'Web' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.fillMaxSize()')
      end

      it 'uses custom width and height when provided' do
        json_data = { 'type' => 'Web', 'width' => 300, 'height' => 400 }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.width(300.dp)')
        expect(result).to include('.height(400.dp)')
      end

      it 'includes padding' do
        json_data = { 'type' => 'Web', 'padding' => 16 }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('modifier = Modifier')
      end

      it 'includes margins' do
        json_data = { 'type' => 'Web', 'margins' => [8, 16] }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('modifier = Modifier')
      end

      it 'includes border when both borderWidth and borderColor provided' do
        json_data = {
          'type' => 'Web',
          'borderWidth' => 1,
          'borderColor' => '#CCCCCC'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.border(')
        expect(required_imports).to include(:border)
      end
    end

    context 'update callback' do
      it 'includes update callback' do
        json_data = { 'type' => 'Web' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('update = { webView ->')
      end

      it 'reloads url in update callback for data binding' do
        json_data = { 'type' => 'Web', 'url' => '@{dynamicUrl}' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('update = { webView ->')
        expect(result).to include('webView.loadUrl(data.dynamicUrl)')
      end
    end
  end

  describe '.indent' do
    it 'returns text unchanged for level 0' do
      result = described_class.send(:indent, 'text', 0)
      expect(result).to eq('text')
    end

    it 'adds indentation for level 1' do
      result = described_class.send(:indent, 'text', 1)
      expect(result).to eq('    text')
    end

    it 'adds indentation for level 2' do
      result = described_class.send(:indent, 'text', 2)
      expect(result).to eq('        text')
    end

    it 'handles multi-line text' do
      result = described_class.send(:indent, "line1\nline2", 1)
      expect(result).to eq("    line1\n    line2")
    end

    it 'preserves empty lines' do
      result = described_class.send(:indent, "line1\n\nline2", 1)
      expect(result).to eq("    line1\n\n    line2")
    end
  end
end
