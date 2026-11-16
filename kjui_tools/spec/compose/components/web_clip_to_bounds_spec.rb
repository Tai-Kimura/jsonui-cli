# frozen_string_literal: true

require 'set'
require 'compose/components/web_component'
require 'compose/components/webview_component'

# Every WebView kjui emits is clipped to its own bounds, with an id (the Box
# wrap) and without. An AndroidView does not clip, and a WebView paints its
# background over the whole window until its first frame settles: measured on
# conf_ci (API 35), a 200dp WebView turned the window white edge to edge for
# ~1.3 s after every open, and conformance captured Web/html__static in either
# state (2 of 12 settled, parity distance 34-35). With the clip, 0 of 8 opens
# showed white outside the view. Ticket
# kjui-webview-paints-the-whole-window-white-until-its-first-frame. The
# dynamic face (DynamicWebComponent) clips the same way.
RSpec.describe 'a WebView is clipped to its own bounds (kjui)' do
  # The stubs the four emits below name — types only (spec/support/
  # kotlin_compiler.rb): this says the emits are well-typed Kotlin, not valid
  # Compose.
  stubs = <<~KOTLIN
    annotation class Composable
    class Context
    class SemanticsScope { var testTagsAsResourceId: Boolean = false }
    interface Modifier { companion object : Modifier }
    fun Modifier.fillMaxSize(): Modifier = this
    fun Modifier.testTag(tag: String): Modifier = this
    fun Modifier.semantics(block: SemanticsScope.() -> Unit): Modifier = this
    fun Modifier.clipToBounds(): Modifier = this
    @Composable
    fun Box(modifier: Modifier = Modifier, content: () -> Unit) { content() }
    class WebSettings { var javaScriptEnabled: Boolean = false }
    open class WebViewClient
    class KjuiWebViewClient : WebViewClient()
    class WebChromeClient
    class WebView(context: Context) {
        val settings = WebSettings()
        var webViewClient: WebViewClient = WebViewClient()
        var webChromeClient: WebChromeClient? = null
        fun loadUrl(u: String) {}
    }
    @Composable
    fun AndroidView(factory: (Context) -> WebView, update: (WebView) -> Unit = {}, modifier: Modifier = Modifier) {}
  KOTLIN

  # One broad arm (each costs a JVM start): both types, with and without an id.
  it 'emits Kotlin that compiles, all four shapes' do
    emits = {
      KjuiTools::Compose::Components::WebComponent => 'Web',
      KjuiTools::Compose::Components::WebviewComponent => 'WebView'
    }.flat_map do |component, type|
      [{ 'id' => 'wv' }, {}].map do |extra|
        component.generate({ 'type' => type, 'url' => 'https://example.com' }.merge(extra), 1, Set.new)
      end
    end
    expect(emits.size).to eq(4)
    expect(emits).to all(include('clipToBounds()'))
    body = emits.each_with_index.map { |code, i| "@Composable\nfun Host#{i}() {\n#{code}\n}" }.join("\n")
    expect("#{stubs}\n#{body}\n").to compile_as_kotlin
  end

  {
    KjuiTools::Compose::Components::WebComponent => 'Web',
    KjuiTools::Compose::Components::WebviewComponent => 'WebView'
  }.each do |component, type|
    context type do
      it 'clips the AndroidView itself when it has an id (inside the Box)' do
        imports = Set.new
        code = component.generate({ 'type' => type, 'id' => 'wv', 'width' => 200, 'height' => 200, 'url' => 'https://example.com' }, 0, imports)
        inner = code[/AndroidView\(.*\)/m]
        expect(inner).to include('modifier = Modifier.fillMaxSize().clipToBounds()')
        expect(imports).to include(:shape)
      end

      it 'clips it last in its own chain when it has none' do
        imports = Set.new
        code = component.generate({ 'type' => type, 'width' => 200, 'height' => 200, 'url' => 'https://example.com' }, 0, imports)
        chain = code[/modifier = Modifier(.*)\n\)\z/m, 1]
        expect(chain).not_to be_nil
        expect(chain.strip.lines.last.strip).to eq('.clipToBounds()')
        expect(imports).to include(:shape)
      end
    end
  end
end
