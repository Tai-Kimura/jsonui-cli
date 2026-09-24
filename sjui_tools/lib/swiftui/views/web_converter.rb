#!/usr/bin/env ruby

require_relative 'base_view_converter'

module SjuiTools
  module SwiftUI
    module Views
      class WebConverter < BaseViewConverter
        def convert
          url = @component['url']
          html = @component['html']

          # The placeholder URL only applies when there is nothing to show at
          # all. `url` wins over `html` in the component, so defaulting it while
          # html is present would render example.com and never the HTML.
          url = "https://example.com" if url.nil? && html.nil?

          # Argument order follows the WebView initializer: Swift resolves
          # labels positionally.
          args = []
          args << if url
                    "url: URL(string: #{swift_string_or_binding(url)})"
                  else
                    'url: nil'
                  end
          args << "html: #{swift_string_or_binding(html)}" if html

          bg = @component['background']
          args << "backgroundColor: UIColor(#{get_swiftui_color(bg)})" if bg

          # Absent means "leave WebKit's own default", which is true for both.
          unless @component['allowsLinkPreview'].nil?
            args << "allowsLinkPreview: #{@component['allowsLinkPreview'] == true || @component['allowsLinkPreview'] == 'true'}"
          end
          unless @component['allowsBackForwardNavigationGestures'].nil?
            gestures = @component['allowsBackForwardNavigationGestures']
            args << "allowsBackForwardNavigationGestures: #{gestures == true || gestures == 'true'}"
          end

          # Both are binding-only (attribute_definitions.json Web). A bare
          # string names nothing on either, so it emits nothing — the same
          # rule onLongPress follows.
          handler = @component['onLoadFailed']
          if handler && is_binding?(handler)
            args << "onLoadFailed: { #{get_event_handler_invocation(handler, @component['id'])} }"
          end
          token = @component['reloadToken']
          if token && is_binding?(token)
            args << "reloadToken: #{swift_string_or_binding(token)}"
          end

          add_line "WebView(#{args.join(', ')})"
          
          # 共通のモディファイアを適用
          apply_modifiers
          
          generated_code
        end
        private

        # A literal as an escaped Swift string, or a `@{...}` binding as its
        # canonical value expression.
        def swift_string_or_binding(value)
          text = value.to_s
          if text.start_with?('@{') && text.end_with?('}')
            SwiftUI::Binding::BindingExpression.swift_value_expr(text[2..-2])
          else
            escaped = text.gsub('\\', '\\\\').gsub('"', '\\"')
                          .gsub("\n", '\\n').gsub("\t", '\\t')
            "\"#{escaped}\""
          end
        end
      end
    end
  end
end