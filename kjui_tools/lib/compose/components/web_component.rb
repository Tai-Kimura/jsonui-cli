# frozen_string_literal: true

require_relative '../helpers/binding_expression'
require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'

module KjuiTools
  module Compose
    module Components
      class WebComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          required_imports&.add(:webview)
          
          # Web uses 'url' for the web page URL
          url_is_bound = json_data['url'].is_a?(String) && json_data['url'].match?(/@\{([^}]+)\}/)
          url = if json_data['url'] && json_data['url'].match(/@\{([^}]+)\}/)
            # `data.#{$1}` spliced the inner expression in verbatim, so a
            # `?? default` reached the emit as `data.x ?? y`, which is not
            # Kotlin. No validator rule covers this attribute (only
            # `binding_direction: "two-way"` ones are checked for a complex
            # expression) — plan 49 lane C.
            Helpers::BindingExpression.value_access($1)
          elsif json_data['url']
            "\"#{json_data['url']}\""
          else
            '""'
          end
          
          # Resolve background color outside factory (Composable context)
          code = ""
          bg = json_data['background']
          if bg
            bg_color = Helpers::ResourceResolver.process_color(bg, required_imports)
            if bg_color
              required_imports&.add(:to_argb)
              code += indent("val webViewBgColor = #{bg_color}.toArgb()", depth) + "\n"
            end
          end

          # Generate WebView using AndroidView
          code += indent("AndroidView(", depth)
          code += "\n" + indent("factory = { context ->", depth + 1)
          code += "\n" + indent("WebView(context).apply {", depth + 2)

          # WebView settings
          code += "\n" + indent("settings.javaScriptEnabled = #{json_data['javaScriptEnabled'] != false}", depth + 3)

          if json_data['userAgent']
            code += "\n" + indent("settings.userAgentString = \"#{json_data['userAgent']}\"", depth + 3)
          end

          if json_data['allowZoom']
            code += "\n" + indent("settings.builtInZoomControls = true", depth + 3)
            code += "\n" + indent("settings.displayZoomControls = false", depth + 3)
          end

          # Background color (resolved outside factory as Int)
          if bg
            code += "\n" + indent("setBackgroundColor(webViewBgColor)", depth + 3)
          end

          # Load the URL, or the raw HTML when there is no URL. `url` wins, the
          # same precedence the other platforms use (iframe src over srcdoc).
          if json_data['url'].nil? && json_data['html']
            # A base URL of null keeps the document in an opaque origin, which is
            # what loading an author-supplied string should do.
            code += "\n" + indent("loadDataWithBaseURL(null, #{kotlin_string(json_data['html'])}, \"text/html\", \"utf-8\", null)", depth + 3)
          else
            # A bound url records what it loaded on the view, so the first
            # `update` below is a no-op rather than a second load.
            code += "\n" + indent("tag = #{url}", depth + 3) if url_is_bound
            code += "\n" + indent("loadUrl(#{url})", depth + 3)
          end
          
          # WebViewClient for handling navigation
          code += "\n" + indent("webViewClient = KjuiWebViewClient()", depth + 3)
          
          # WebChromeClient for JavaScript alerts
          if json_data['javaScriptEnabled'] != false
            code += "\n" + indent("webChromeClient = WebChromeClient()", depth + 3)
          end
          
          code += "\n" + indent("}", depth + 2)
          code += "\n" + indent("},", depth + 1)
          
          # Update callback to handle URL changes. `update` runs on every
          # recomposition, so a bound url is reloaded only when it moved since
          # the last load — kept on the view's `tag`, the same shape
          # webview_component.rb has had since 1.8.103. Until
          # kjui-web-codegen-reloads-bound-url-on-every-recomposition this
          # called loadUrl unconditionally and threw away scroll position,
          # form input and page state whenever anything around it recomposed.
          # Not `webView.url`: it follows redirects, so a redirected page would
          # still reload every time. A static url keeps its empty block.
          code += "\n" + indent("update = { webView ->", depth + 1)
          
          if url_is_bound
            code += "\n" + indent("val url = #{url}", depth + 2)
            code += "\n" + indent("if (webView.tag != url) {", depth + 2)
            code += "\n" + indent("webView.tag = url", depth + 3)
            code += "\n" + indent("webView.loadUrl(url)", depth + 3)
            code += "\n" + indent("}", depth + 2)
          end
          
          code += "\n" + indent("},", depth + 1)
          
          # Build modifiers
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))

          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))

          # Default size for WebView
          if !json_data['width'] && !json_data['height']
            modifiers << ".fillMaxSize()"
          else
            modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports))
          end
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          # Border for WebView
          if json_data['borderWidth'] && json_data['borderColor']
            required_imports&.add(:border)
            modifiers << ".border(#{json_data['borderWidth']}.dp, Helpers::ResourceResolver.process_color('#{json_data['borderColor']}', required_imports))"
          end
          
          # 🔻 THE ID LIVES ON A COMPOSE NODE, NOT ON THE AndroidView. A testTag
          # on the AndroidView's own modifier is never projected as a UiAutomator
          # resource-id: the holder exposes the real android.webkit.WebView,
          # whose resource-id is empty (bar face, 2026-09-17:
          # `class="android.webkit.WebView" resource-id=""` while the screen
          # marker on a Compose node was found). So an id wraps the view in a
          # Box that carries the WHOLE modifier chain — tag, margins, size,
          # alpha, clip, weight — and the AndroidView fills the Box. Measured on
          # conf_ci (api 35) before this emit changed: with the wrap the tree
          # holds `android.view.View resource-id="<id>"` with the WebView as
          # its child, same bounds; without it, no node carries the id.
          # Without an id nothing is wrapped and the emit is byte-identical.
          # (kjui-webview-testtag-on-androidview-not-projected-as-resource-id;
          # the dynamic runtime's DynamicWebComponent does the same.)
          if json_data['id']
            required_imports&.add(:box)
            # Statements emitted before the call (`val webViewBgColor = …`)
            # stay outside the Box; only the AndroidView(...) call is wrapped.
            head, call = code.split(indent("AndroidView(", depth), 2)
            call = indent("AndroidView(", depth) + call
            box = head.to_s + indent("Box(", depth)
            box += Helpers::ModifierBuilder.format(modifiers, depth)
            box += "\n" + indent(") {", depth)
            inner = call.split("\n").map { |l| l.empty? ? l : "    " + l }.join("\n")
            inner += "\n" + indent("modifier = Modifier.fillMaxSize()", depth + 2)
            inner += "\n" + indent(")", depth + 1)
            return box + "\n" + inner + "\n" + indent("}", depth)
          end

          code += Helpers::ModifierBuilder.format(modifiers, depth)
          
          code += "\n" + indent(")", depth)
          code
        end
        
        private
        
        # A Kotlin string literal. HTML carries quotes, backslashes and newlines
        # that would otherwise break the generated source.
        def self.kotlin_string(value)
          escaped = value.to_s
                         .gsub('\\', '\\\\')
                         .gsub('"', '\\"')
                         .gsub('$', '\\$')
                         .gsub("\n", '\\n')
                         .gsub("\t", '\\t')
          "\"#{escaped}\""
        end

        def self.indent(text, level)
          return text if level == 0
          spaces = '    ' * level
          text.split("\n").map { |line| 
            line.empty? ? line : spaces + line 
          }.join("\n")
        end
      end
    end
  end
end