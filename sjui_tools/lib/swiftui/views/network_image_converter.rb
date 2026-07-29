#!/usr/bin/env ruby

require_relative 'base_view_converter'

module SjuiTools
  module SwiftUI
    module Views
      # Generated code network image converter
      # Dynamic mode equivalent: Sources/SwiftJsonUI/Classes/SwiftUI/Dynamic/Converters/NetworkImageConverter.swift
      class NetworkImageConverter < BaseViewConverter
        def convert
          url = @component['src'] || ""

          # NetworkImageを使用
          add_line "NetworkImage("
          indent do
            # URL
            processed_url = process_template_value(url)
            if processed_url.is_a?(Hash) && processed_url[:template_var]
              add_line "url: data.#{to_camel_case(processed_url[:template_var])},"
            else
              add_line "url: \"#{url}\","
            end

            # プレースホルダー
            if @component['placeholder']
              add_line "placeholder: \"#{@component['placeholder']}\","
            end

            # defaultImage / loadingImage / errorImage.
            #
            # The NetworkImage view has taken all three since it was written —
            # loadingImage while the request is in flight, errorImage on
            # failure, placeholder/defaultImage as the fallback for both — and
            # the codegen passed none of them. A layout that set them got the
            # built-in ProgressView and the built-in broken-photo glyph instead,
            # on the SwiftUI path only; the UIKit runtime honours all three.
            if @component['defaultImage']
              add_line "defaultImage: \"#{@component['defaultImage']}\","
            end
            if @component['loadingImage']
              add_line "loadingImage: \"#{@component['loadingImage']}\","
            end
            if @component['errorImage']
              add_line "errorImage: \"#{@component['errorImage']}\","
            end

            # contentMode
            if @component['contentMode']
              content_mode = map_content_mode_enum(@component['contentMode'])
              add_line "contentMode: #{content_mode},"
            end

            # renderingMode
            if @component['renderingMode']
              rendering_mode = map_rendering_mode(@component['renderingMode'])
              add_line "renderingMode: #{rendering_mode},"
            end

            # ヘッダー
            if @component['headers']
              add_line "headers: ["
              indent do
                @component['headers'].each_with_index do |(key, value), index|
                  comma = index < @component['headers'].length - 1 ? "," : ""
                  add_line "\"#{key}\": \"#{value}\"#{comma}"
                end
              end
              add_line "]"
            else
              # 最後のカンマを削除
              if @generated_code.last.end_with?(',')
                @generated_code[-1] = @generated_code.last.chomp(',')
              end
            end
          end
          add_line ")"

          # Apply all common modifiers (padding, frame, background, cornerRadius, border, margins, opacity, etc.)
          apply_modifiers

          # Apply binding modifiers (borderColor, background, etc. with @{...})
          apply_binding_modifiers

          generated_code
        end

        private

        def map_content_mode_enum(mode)
          case mode
          when 'AspectFill', 'aspectFill'
            '.fill'
          when 'AspectFit', 'aspectFit'
            '.fit'
          when 'center', 'Center'
            '.center'
          else
            '.fit'
          end
        end

        def map_rendering_mode(mode)
          case mode
          when 'template', 'Template'
            '.template'
          when 'original', 'Original'
            '.original'
          else
            'nil'
          end
        end
      end
    end
  end
end
