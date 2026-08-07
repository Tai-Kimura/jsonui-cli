# frozen_string_literal: true

require_relative '../helpers/binding_expression'
require_relative '../helpers/modifier_builder'

module KjuiTools
  module Compose
    module Components
      class WebviewComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          required_imports&.add(:webview)
          
          # WebView uses 'url' for the web page URL
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

          code += "\n" + indent("webViewClient = WebViewClient()", depth + 3)
          code += "\n" + indent("webChromeClient = WebChromeClient()", depth + 3)

          # Background color (resolved outside factory as Int)
          if bg
            code += "\n" + indent("setBackgroundColor(webViewBgColor)", depth + 3)
          end

          # Load URL
          code += "\n" + indent("loadUrl(#{url})", depth + 3)
          
          code += "\n" + indent("}", depth + 2)
          code += "\n" + indent("},", depth + 1)
          
          # Build modifiers
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, nil, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_alignment(json_data, required_imports, parent_type))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          if json_data['cornerRadius']
            required_imports&.add(:shape)
            modifiers << ".clip(RoundedCornerShape(#{json_data['cornerRadius']}.dp))"
          end
          
          code += Helpers::ModifierBuilder.format(modifiers, depth)
          
          code += "\n" + indent(")", depth)
          code
        end
        
        private
        
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