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
            code += "\n" + indent("loadUrl(#{url})", depth + 3)
          end
          
          # WebViewClient for handling navigation
          code += "\n" + indent("webViewClient = WebViewClient()", depth + 3)
          
          # WebChromeClient for JavaScript alerts
          if json_data['javaScriptEnabled'] != false
            code += "\n" + indent("webChromeClient = WebChromeClient()", depth + 3)
          end
          
          code += "\n" + indent("}", depth + 2)
          code += "\n" + indent("},", depth + 1)
          
          # Update callback to handle URL changes
          code += "\n" + indent("update = { webView ->", depth + 1)
          
          if json_data['url'] && json_data['url'].match(/@\{([^}]+)\}/)
            code += "\n" + indent("webView.loadUrl(#{url})", depth + 2)
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
            modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, nil, required_imports))
          end
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          # Border for WebView
          if json_data['borderWidth'] && json_data['borderColor']
            required_imports&.add(:border)
            modifiers << ".border(#{json_data['borderWidth']}.dp, Helpers::ResourceResolver.process_color('#{json_data['borderColor']}', required_imports))"
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