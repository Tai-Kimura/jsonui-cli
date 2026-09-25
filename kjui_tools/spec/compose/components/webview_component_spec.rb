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
        update = result[/update = \{ webView ->(.*?)\n\s*\},/m, 1]
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
              fun fillMaxSize(): Modifier = this
          }
          @Composable
          fun Box(modifier: Modifier = Modifier, content: () -> Unit) { content() }
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

    # kjui-webview-testtag-on-androidview-not-projected-as-resource-id: a
    # testTag on the AndroidView's own modifier never reached UiAutomator
    # (`class="android.webkit.WebView" resource-id=""` on the bar face, while
    # the screen marker on a Compose node did). The id goes on a Compose Box
    # that wraps the AndroidView — measured on conf_ci before this emit was
    # changed: the Box node carries `resource-id="<id>"`, the WebView stays
    # its child. Every layout modifier moves to the Box; the AndroidView
    # fills it.
    context 'an id' do
      let(:with_id) do
        { 'type' => 'WebView', 'id' => 'web_view', 'url' => '@{webViewUrl}',
          'width' => 'matchParent', 'weight' => 1 }
      end

      it 'wraps the AndroidView in a Box that carries the testTag as a Compose node' do
        result = described_class.generate(with_id, 0, required_imports, 'Column')
        expect(result).to start_with("Box(\n")
        box_chain = result[/\ABox\(\n    modifier = Modifier(.*?)\n\) \{/m, 1]
        expect(box_chain).not_to be_nil, result
        expect(box_chain).to include('.testTag("web_view")')
        expect(box_chain).to include('.semantics { testTagsAsResourceId = true }')
        # The layout modifiers ride on the Box, not the AndroidView.
        expect(box_chain).to include('.fillMaxWidth()')
        expect(box_chain).to include('.weight(1f)')
        expect(required_imports).to include(:box)
      end

      it 'gives the AndroidView the whole Box and nothing else' do
        result = described_class.generate(with_id, 0, required_imports, 'Column')
        inner = result[/\n    AndroidView\((.*)\n    \)\n\}\z/m, 1]
        expect(inner).not_to be_nil, result
        expect(inner).to include('modifier = Modifier.fillMaxSize()')
        expect(inner).not_to include('testTag')
        expect(inner).not_to include('.weight(')
        # The bound-url update block is still inside.
        expect(inner).to include('update = { webView ->')
      end

      it 'wraps a static url the same way' do
        result = described_class.generate({ 'type' => 'WebView', 'id' => 'wv', 'url' => 'https://example.com' }, 0, required_imports)
        expect(result).to start_with("Box(\n")
        expect(result).to include('.testTag("wv")')
        expect(result).to include('loadUrl("https://example.com")')
        expect(result).not_to include('update =')
      end
    end

    it 'adds cornerRadius modifier' do
      json_data = { 'type' => 'WebView', 'cornerRadius' => 8 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('RoundedCornerShape(8.dp)')
      expect(required_imports).to include(:shape)
    end
  end
  describe 'onLoadFailed and reloadToken' do
    # A static url emitted no `update` at all; a node that declares either
    # attribute needs one, because that is where the view state is fed.
    it 'opens an update block for a static url that declares them' do
      code = described_class.generate(
        { 'type' => 'WebView', 'url' => 'https://a.test',
          'onLoadFailed' => '@{failed}', 'reloadToken' => '@{token}' }, 0, required_imports
      )
      # The body sits two levels in (8 spaces at depth 0).
      update = code[/update = \{ webView ->\n(.*?)\n    \},/m, 1].gsub(/^ {8}/, '')
      expect(update).to eq(<<~KOTLIN.chomp)
            // Requires KotlinJsonUI >= 2.41.0 (Web onLoadFailed / reloadToken)
            val loadState = KjuiWebLoadState.of(webView)
            loadState.onLoadFailed = { data.failed?.invoke() }
            if (loadState.reloadTokenChanged(data.token)) {
                webView.loadUrl("https://a.test")
            }
      KOTLIN
      expect(required_imports).to include(:web_load_state)
    end

    it 'puts the token before the bound-url follow, which then loads once' do
      code = described_class.generate(
        { 'type' => 'WebView', 'url' => '@{pageUrl}', 'reloadToken' => '@{token}' }, 0, Set.new
      )
      expect(code).to include("if (loadState.reloadTokenChanged(data.token)) {\n            webView.tag = null\n        }\n        val url = data.pageUrl")
      expect(code.scan('loadUrl(').size).to eq(2) # the factory's and the follow's
    end

    it 'still emits no update block for a static url without them' do
      code = described_class.generate({ 'type' => 'WebView', 'url' => 'https://a.test' }, 0, required_imports)
      expect(code).not_to include('update =')
      expect(required_imports).not_to include(:web_load_state)
    end
  end
end
