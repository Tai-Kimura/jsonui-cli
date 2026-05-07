#!/usr/bin/env ruby

require_relative 'base_view_converter'

module SjuiTools
  module SwiftUI
    module Views
      class WebConverter < BaseViewConverter
        def convert
          url = @component['url'] || "https://example.com"
          
          # @{...}形式のテンプレート処理
          if url.start_with?('@{') && url.end_with?('}')
            # @{...}の中身を取り出す
            url_var = url[2...-1]
            url_binding = "data.#{to_camel_case(url_var)}"
          else
            url_binding = "\"#{url}\""
          end
          
          # Build WebView with optional backgroundColor
          bg = @component['background']
          if bg
            bg_color = "UIColor(#{get_swiftui_color(bg)})"
            add_line "WebView(url: URL(string: #{url_binding}), backgroundColor: #{bg_color})"
          else
            add_line "WebView(url: URL(string: #{url_binding}))"
          end
          
          # 共通のモディファイアを適用
          apply_modifiers
          
          generated_code
        end
      end
    end
  end
end