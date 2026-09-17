# frozen_string_literal: true

require 'compose/components/webview_component'
require 'compose/helpers/modifier_builder'

RSpec.describe KjuiTools::Compose::Components::WebviewComponent do
  let(:required_imports) { Set.new }

  describe '.generate' do
    it 'uses the library WebViewClient, not the bare one' do
      json_data = { 'type' => 'WebView' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('webViewClient = KjuiWebViewClient()')
      expect(result).not_to include('webViewClient = WebViewClient()')
    end

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

    # kjui-webview-codegen-does-not-follow-url-binding-changes: `type: "WebView"`
    # loaded a bound url ONCE, in `factory`, and emitted no `update`, so a
    # url set after the first composition never reached the view. The
    # sibling `type: "Web"` converter, SwiftJsonUI's `updateUIView` and the
    # dynamic runtime all follow the binding; this converter was the outlier.
    context 'a bound url' do
      let(:bound) { { 'type' => 'WebView', 'id' => 'wv', 'url' => '@{webViewUrl}' } }

      it 'is followed after the first composition: an update that reloads only when it moved' do
        result = described_class.generate(bound, 0, required_imports)
        expect(result).to include('update = { webView ->')
        # Compared against the url this view last LOADED, kept on the view
        # itself — not against `webView.url`, which follows redirects and
        # would reload on every recomposition after one.
        expect(result).to include('if (webView.tag != url) {')
        expect(result).to include('webView.tag = url')
        expect(result).to include('webView.loadUrl(url)')
        # The first load records what it loaded, so the first update is a no-op.
        expect(result).to match(/tag = data\.webViewUrl\n\s+loadUrl\(data\.webViewUrl\)/)
        # 1.8.100's load signal stays on the factory line, untouched.
        expect(result).to include('webViewClient = KjuiWebViewClient()')
      end

      it 'is not followed by reloading on every recomposition' do
        result = described_class.generate(bound, 0, required_imports)
        update = result[/update = \{ webView ->(.*?)\n    \},/m, 1]
        expect(update).not_to be_nil
        expect(update.scan('loadUrl').size).to eq(1)
        expect(update).to include('if (webView.tag != url)')
      end

      # The control: a static url has nothing to follow, and its emit is
      # the same bytes it was before this arm existed — pinned whole, so
      # "no update for a static url" cannot drift into "some other change".
      it 'leaves a static url emit byte-identical (no update, no tag)' do
        result = described_class.generate({ 'type' => 'WebView', 'url' => 'https://example.com' }, 0, required_imports)
        expect(result).to eq(<<~KOTLIN.chomp)
          AndroidView(
              factory = { context ->
                  WebView(context).apply {
                      settings.javaScriptEnabled = true
                      webViewClient = KjuiWebViewClient()
                      webChromeClient = WebChromeClient()
                      loadUrl("https://example.com")
                  }
              },
          )
        KOTLIN
      end

      # One broad arm: the bound emit, update included, is well-typed against
      # a stub universe (spec/support/kotlin_compiler.rb). Types against
      # stubs only — not the Compose compiler's rules.
      it 'emits a call that compiles, update included' do
        result = described_class.generate(bound, 1, required_imports)
        expect(<<~KOTLIN).to compile_as_kotlin
          annotation class Composable
          class Context
          class SemanticsScope { var testTagsAsResourceId: Boolean = false }
          object Modifier {
              fun testTag(tag: String): Modifier = this
              fun semantics(block: SemanticsScope.() -> Unit): Modifier = this
          }
          class WebSettings { var javaScriptEnabled: Boolean = false; var userAgentString: String = "" }
          open class WebViewClient
          class KjuiWebViewClient : WebViewClient()
          class WebChromeClient
          class WebView(context: Context) {
              val settings = WebSettings()
              var webViewClient: WebViewClient = WebViewClient()
              var webChromeClient: WebChromeClient? = null
              var tag: Any? = null
              val url: String? = null
              fun setBackgroundColor(c: Int) {}
              fun loadUrl(u: String) {}
          }
          @Composable
          fun AndroidView(factory: (Context) -> WebView, update: (WebView) -> Unit = {}, modifier: Modifier = Modifier) {}
          class Data(val webViewUrl: String)
          @Composable
          fun Host(data: Data) {
          #{result}
          }
        KOTLIN
      end
    end

    it 'adds cornerRadius modifier' do
      json_data = { 'type' => 'WebView', 'cornerRadius' => 8 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('RoundedCornerShape(8.dp)')
      expect(required_imports).to include(:shape)
    end
  end
end
