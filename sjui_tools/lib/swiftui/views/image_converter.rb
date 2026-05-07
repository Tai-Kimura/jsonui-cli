#!/usr/bin/env ruby

require_relative 'base_view_converter'

module SjuiTools
  module SwiftUI
    module Views
      # Generated code image converter
      # Dynamic mode equivalent: Sources/SwiftJsonUI/Classes/SwiftUI/Dynamic/Converters/ImageViewConverter.swift
      class ImageConverter < BaseViewConverter
        def convert
          # srcName優先（srcNameはアセット名を直接指定）
          if @component['srcName']
            if is_binding?(@component['srcName'])
              prop = extract_binding_property(@component['srcName'])
              add_line "Image(data.#{prop})"
            else
              add_line "Image(\"#{@component['srcName']}\")"
            end
          elsif @component['src']
            processed_src = process_template_value(@component['src'])
            if processed_src.is_a?(Hash) && processed_src[:template_var]
              # テンプレート変数の場合
              add_line "Image(data.#{to_camel_case(processed_src[:template_var])})"
            else
              # 通常の画像名
              add_line "Image(\"#{@component['src']}\")"
            end
          elsif @component['defaultImage']
            # defaultImageが指定されている場合はそれを使用
            add_line "Image(\"#{@component['defaultImage']}\")"
          else
            # デフォルトのシステムイメージ
            add_line "Image(systemName: \"photo\")"
          end

          @modifier_bag.append(:component_specific, ".resizable()")

          # contentMode
          if @component['contentMode']
            content_mode = map_content_mode(@component['contentMode'])
            @modifier_bag.append(:component_specific, ".aspectRatio(contentMode: #{content_mode})")
          else
            @modifier_bag.append(:component_specific, ".aspectRatio(contentMode: .fit)")
          end

          # CircleImageの場合
          if @component['type'] == 'CircleImage'
            @modifier_bag.append(:component_specific, ".clipShape(Circle())")
          end

          # onSrcプロパティ（画像読み込み完了時のコールバック）
          if @component['onSrc']
            add_line "// onSrc: #{@component['onSrc']} - Image loaded callback"
            method_name = extract_binding_property(@component['onSrc'])
            indent_str = "    " * (@indent_level + 1)
            @modifier_bag.append(:on_appear, ".onAppear {\n#{indent_str}// Call #{@component['onSrc']} when image appears\n#{indent_str}data.#{method_name}?()\n#{indent_str[0...-4]}}")
          end

          # onClick handler (canTap is optional, onClick alone is sufficient)
          if @component['onClick'] && is_binding?(@component['onClick'])
            handler_call = get_event_handler_invocation(@component['onClick'], @component['id'] || 'image')
            on_click_lines = [
              ".contentShape(Rectangle())",
              build_on_tap_gesture(handler_call)
            ]
            @modifier_bag.register(:on_click, on_click_lines)
          end

          # Apply all common modifiers (padding, frame, background, cornerRadius, border, margins, opacity, etc.)
          apply_modifiers

          # Apply binding modifiers (borderColor, background, etc. with @{...})
          apply_binding_modifiers

          generated_code
        end

        private

        def map_content_mode(mode)
          case mode
          when 'AspectFill', 'aspectFill'
            '.fill'
          when 'AspectFit', 'aspectFit'
            '.fit'
          when 'center'
            '.fit'  # SwiftUIには直接的なcenterモードがないため
          else
            '.fit'
          end
        end

        def build_on_tap_gesture(handler_call)
          indent_str = "    " * (@indent_level + 1)
          ".onTapGesture {\n#{indent_str}#{handler_call}\n#{indent_str[0...-4]}}"
        end
      end
    end
  end
end
