# frozen_string_literal: true

require 'compose/components/web_component'
require 'compose/helpers/import_manager'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'

RSpec.describe KjuiTools::Compose::Components::WebComponent do
  let(:required_imports) { Set.new }

  # Same defect and same shape as webview_component.rb (the two converters are
  # the AndroidView twins): an id becomes a testTag on a Compose Box around
  # the AndroidView, so UiAutomator sees it as a resource-id. Without an id
  # the emit is the bytes it was — pinned whole below.
  describe 'the id as a Compose node (resource-id projection)' do
    it 'wraps the AndroidView in a Box carrying the testTag, layout modifiers on the Box' do
      result = described_class.generate({ 'type' => 'Web', 'id' => 'wv', 'url' => 'https://example.com', 'weight' => 1 }, 0, required_imports, 'Row')
      expect(result).to start_with("Box(\n")
      box_chain = result[/\ABox\(\n    modifier = Modifier(.*?)\n\) \{/m, 1]
      expect(box_chain).not_to be_nil, result
      expect(box_chain).to include('.testTag("wv")')
      expect(box_chain).to include('.semantics { testTagsAsResourceId = true }')
      expect(box_chain).to include('.fillMaxSize()')
      expect(box_chain).to include('.weight(1f)')
      inner = result[/\n    AndroidView\((.*)\n    \)\n\}\z/m, 1]
      expect(inner).not_to be_nil, result
      expect(inner).to include('modifier = Modifier.fillMaxSize()')
      expect(inner).not_to include('testTag')
      expect(required_imports).to include(:box)
    end

    it 'leaves a static url inside the Box byte-identical to 1.8.104' do
      result = described_class.generate({ 'type' => 'Web', 'id' => 'wv', 'url' => 'https://example.com' }, 0, required_imports)
      expect(result).to eq(<<~KOTLIN.chomp)
        Box(
            modifier = Modifier
                .testTag("wv")
                .semantics { testTagsAsResourceId = true }
                .fillMaxSize()
        ) {
            AndroidView(
                factory = { context ->
                    WebView(context).apply {
                        settings.javaScriptEnabled = true
                        loadUrl("https://example.com")
                        webViewClient = KjuiWebViewClient()
                        webChromeClient = WebChromeClient()
                    }
                },
                update = { webView ->
                },
                modifier = Modifier.fillMaxSize()
            )
        }
      KOTLIN
    end

    it 'leaves the emit without an id byte-identical (no Box)' do
      result = described_class.generate({ 'type' => 'Web', 'url' => 'https://example.com' }, 0, required_imports)
      expect(result).to eq(<<~KOTLIN.chomp)
        AndroidView(
            factory = { context ->
                WebView(context).apply {
                    settings.javaScriptEnabled = true
                    loadUrl("https://example.com")
                    webViewClient = KjuiWebViewClient()
                    webChromeClient = WebChromeClient()
                }
            },
            update = { webView ->
            },
            modifier = Modifier.fillMaxSize()
        )
      KOTLIN
    end
  end

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
      expect(result).to include('val url = data.webUrl')
      expect(result).to include('webView.loadUrl(url)')
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

    it 'always includes the library WebViewClient' do
      json_data = { 'type' => 'Web' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('webViewClient = KjuiWebViewClient()')
    end

    # 🔻 THE ARM THAT WOULD HAVE CAUGHT IT. A bare `WebViewClient()` overrides
    # nothing, so the generated WebView reports no page-load completion and a
    # conformance host captures whatever the page happened to paint. Measured
    # 2026-09-16 on conformance-mobile run 34987243780: the dynamic leg reported
    # markerAbsent=0 and the codegen leg markerAbsent=2 — in ONE run, on ONE
    # emulator image, so the difference is the emitter and not the environment.
    #
    # ⚠️ The assertion is on the exact assignment, not on the substring
    # "WebViewClient()" — `KjuiWebViewClient()` contains it, so a `not_to
    # include('WebViewClient()')` would fail on the CORRECT output.
    it 'never emits the bare client, which is the one that signals nothing' do
      json_data = { 'type' => 'Web' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).not_to include('webViewClient = WebViewClient()')
    end

    # Two halves, because the emitter and the import table are separate files:
    # the emitter registers a KEY, the table turns that key into import lines.
    # Asserting only the key would pass with a table that never mentions the
    # class, and the generated file would not compile.
    it 'requires the import key, and that key carries the client import' do
      json_data = { 'type' => 'Web' }
      described_class.generate(json_data, 0, required_imports)
      expect(required_imports).to include(:webview)
      lines = Array(KjuiTools::Compose::Helpers::ImportManager.get_imports_map[:webview])
      expect(lines).to include('import com.kotlinjsonui.core.KjuiWebViewClient')
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
        expect(result).to include('.requiredWidth(300.dp)')
        expect(result).to include('.requiredHeight(400.dp)')
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
        expect(result).to include('val url = data.dynamicUrl')
        expect(result).to include('webView.loadUrl(url)')
      end

      # kjui-web-codegen-reloads-bound-url-on-every-recomposition: the update
      # used to call loadUrl unconditionally, and `update` runs on every
      # recomposition — a bound page was reloaded whenever anything around it
      # recomposed. `type: "WebView"` (1.8.103) keeps the last LOADED url on
      # the view's `tag` and reloads only when the binding moved; this is the
      # same shape. Not `webView.url`: that follows redirects.
      describe 'a bound url reloads only when it moved' do
        let(:bound) { { 'type' => 'Web', 'url' => '@{pageUrl}' } }

        def update_body(code)
          code[/update = \{ webView ->\n(.*?)\n\s*\},\n/m, 1]
        end

        it 'compares against the url the view last loaded before reloading' do
          body = update_body(described_class.generate(bound, 0, required_imports))
          expect(body).not_to be_nil
          expect(body).to eq(<<~KOTLIN.chomp.gsub(/^/, '        '))
            val url = data.pageUrl
            if (webView.tag != url) {
                webView.tag = url
                webView.loadUrl(url)
            }
          KOTLIN
        end

        it 'records what the factory loaded, so the first update is a no-op' do
          result = described_class.generate(bound, 0, required_imports)
          expect(result).to match(/tag = data\.pageUrl\n\s+loadUrl\(data\.pageUrl\)/)
        end

        it 'keeps the same update inside the Box when there is an id' do
          result = described_class.generate(bound.merge('id' => 'w'), 0, required_imports)
          expect(result).to start_with("Box(\n")
          expect(result).to include("        update = { webView ->\n" \
                                    "            val url = data.pageUrl\n" \
                                    "            if (webView.tag != url) {\n")
          expect(result).to match(/tag = data\.pageUrl\n\s+loadUrl\(data\.pageUrl\)/)
        end

        it 'does not put the comparison on a static url, whose emit is unchanged' do
          result = described_class.generate({ 'type' => 'Web', 'url' => 'https://example.com' }, 0, required_imports)
          expect(result).not_to include('tag')
          expect(update_body(result)).to be_nil  # the update block is still the empty one
        end

        it 'does not touch the html branch' do
          result = described_class.generate({ 'type' => 'Web', 'html' => '<b>x</b>' }, 0, required_imports)
          expect(result).not_to include('tag')
          expect(result).not_to include('loadUrl')
        end
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
  describe 'html' do
    it 'loads raw html when there is no url' do
      code = described_class.generate({ 'type' => 'Web', 'html' => '<b>hi</b>' }, 0, Set.new)
      expect(code).to include('loadDataWithBaseURL(null, "<b>hi</b>", "text/html", "utf-8", null)')
      expect(code).not_to include('loadUrl')
    end

    # `url` wins, matching the other platforms.
    it 'prefers the url when both are given' do
      code = described_class.generate(
        { 'type' => 'Web', 'url' => 'https://a.test', 'html' => '<b>hi</b>' }, 0, Set.new
      )
      expect(code).to include('loadUrl("https://a.test")')
      expect(code).not_to include('loadDataWithBaseURL')
    end

    # A Kotlin template would otherwise interpolate, and a bare quote would end
    # the literal.
    it 'escapes quotes and dollar signs in the html literal' do
      code = described_class.generate({ 'type' => 'Web', 'html' => '<a t="x">$y' }, 0, Set.new)
      expect(code).to include('\\"x\\"')
      expect(code).to include('\\$y')
    end
  end
  # ssot-web-component-has-no-load-failure-event-or-reload-trigger. Both feed
  # KjuiWebLoadState from `update`, which runs again when the data it reads
  # changes — the handler handed over is always the current one.
  describe 'onLoadFailed and reloadToken' do
    # With a bound url the token only forgets the last load; the url follow
    # after it then loads once, so a token and url that move together cost
    # one load, not two.
    it 'hands the handler to the view state and lets the url follow reload on a moved token' do
      code = described_class.generate(
        { 'type' => 'Web', 'url' => '@{pageUrl}',
          'onLoadFailed' => '@{onLoadFailed}', 'reloadToken' => '@{reloadToken}' },
        0, required_imports
      )
      # The body sits two levels in (8 spaces at depth 0).
      update = code[/update = \{ webView ->\n(.*?)\n    \},/m, 1].gsub(/^ {8}/, '')
      expect(update).to eq(<<~KOTLIN.chomp)
            // Requires KotlinJsonUI >= 2.41.0 (Web onLoadFailed / reloadToken)
            val loadState = KjuiWebLoadState.of(webView)
            loadState.onLoadFailed = { data.onLoadFailed?.invoke() }
            if (loadState.reloadTokenChanged(data.reloadToken)) {
                webView.tag = null
            }
            val url = data.pageUrl
            if (webView.tag != url) {
                webView.tag = url
                webView.loadUrl(url)
            }
      KOTLIN
      expect(required_imports).to include(:web_load_state)
    end

    it 'reloads a static url as the literal the factory loaded' do
      code = described_class.generate(
        { 'type' => 'Web', 'url' => 'https://a.test', 'reloadToken' => '@{token}' }, 0, Set.new
      )
      expect(code).to include("if (loadState.reloadTokenChanged(data.token)) {\n            webView.loadUrl(\"https://a.test\")")
      expect(code).not_to include('loadState.onLoadFailed')
    end

    it 'reloads the html when there is no url' do
      code = described_class.generate(
        { 'type' => 'Web', 'html' => '<b>hi</b>', 'reloadToken' => '@{token}' }, 0, Set.new
      )
      expect(code).to include('webView.loadDataWithBaseURL(null, "<b>hi</b>", "text/html", "utf-8", null)')
      expect(code).not_to include('loadUrl')
    end

    it 'emits nothing, and no import, for bare strings' do
      imports = Set.new
      bare = described_class.generate(
        { 'type' => 'Web', 'url' => 'https://a.test', 'onLoadFailed' => 'f', 'reloadToken' => '1' }, 0, imports
      )
      plain = described_class.generate({ 'type' => 'Web', 'url' => 'https://a.test' }, 0, Set.new)
      expect(bare).to eq(plain)
      expect(imports).not_to include(:web_load_state)
    end
  end
end
