#!/usr/bin/env ruby

require_relative 'base_view_converter'

module SjuiTools
  module SwiftUI
    module Views
      # Generated code network image converter
      # Dynamic mode equivalent: Sources/SwiftJsonUI/Classes/SwiftUI/Dynamic/Converters/NetworkImageConverter.swift
      class NetworkImageConverter < BaseViewConverter
        def convert
          # `url` is the canonical spelling; `source`/`src` are aliases
          # (kjui reads all three; the ios converter only read `src`).
          url = @component['url'] || @component['source'] || @component['src'] || ""

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

            # プレースホルダー — `hint` is the canonical spelling,
            # `placeholder` the alias (kjui reads hint first; parity).
            hint_value = @component['hint'] || @component['placeholder']
            if hint_value
              add_line "placeholder: \"#{hint_value}\","
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

            # contentMode. A BOUND spelling resolves at run time through the
            # non-DEBUG library seam (NetworkImage.ContentMode.from,
            # SwiftJsonUI >= 911293f) — the compile-time map cannot see a
            # `@{...}` value and fell through to `.fit`, freezing the binding
            # to a constant (C1/bound-frozen, NetworkImage.contentMode [ios]).
            if bound_value?(@component['contentMode'])
              expr = SjuiTools::SwiftUI::Binding::BindingExpression
                     .swift_text_expr(@component['contentMode'][2..-2])
              add_line "contentMode: NetworkImage.ContentMode.from(#{expr}),"
            elsif @component['contentMode']
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
          when 'fill', 'Fill', 'scaleToFill', 'ScaleToFill'
            # fill = stretch (canonical image.fill,
            # shared/core/attribute_semantics.json) — NetworkImage gained the
            # .stretch case for it.
            '.stretch'
          when 'top', 'Top', 'bottom', 'Bottom', 'left', 'Left', 'right', 'Right'
            # Positional modes draw unscaled and aligned — NetworkImage has
            # carried the cases since the contentMode wave; the map dropped
            # them to .fit (32 parity, d=50-79).
            ".#{mode.downcase}"
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
