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
