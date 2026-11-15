#!/usr/bin/env ruby

require_relative 'base_view_converter'
require_relative 'image_accessibility_modifiers'

module SjuiTools
  module SwiftUI
    module Views
      # Generated code network image converter
      # Dynamic mode equivalent: Sources/SwiftJsonUI/Classes/SwiftUI/Dynamic/Converters/NetworkImageConverter.swift
      class NetworkImageConverter < BaseViewConverter
        include ImageAccessibilityModifiers

        def convert
          # `url` is the canonical spelling; `source`/`src` are aliases
          # (kjui reads all three; the ios converter only read `src`).
          url = @component['url'] || @component['source'] || @component['src'] || ""

          # The load listener's arguments are new NetworkImage parameters, so
          # an image that writes one does not compile against an older library;
          # one that writes none emits exactly what it did before.
          load_args = load_listener_arguments
          add_line '// Requires SwiftJsonUI >= 10.41.0 (NetworkImage loadingRenderer / loadingDelay / transitionDuration / onLoadStateChange)' unless load_args.empty?

          # NetworkImageを使用
          add_line "NetworkImage("
          indent do
            # URL
            processed_url = process_template_value(url)
            if processed_url.is_a?(Hash) && processed_url[:template_var]
              add_line "url: data.#{to_camel_case(processed_url[:template_var])},"
            else
              add_line "url: #{swift_string_literal(url)},"
            end

            # プレースホルダー — `hint` is the canonical spelling,
            # `placeholder` the alias (kjui reads hint first; parity).
            hint_value = @component['hint'] || @component['placeholder']
            if hint_value
              add_line "placeholder: #{name_operand(hint_value)},"
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
              add_line "defaultImage: #{name_operand(@component['defaultImage'])},"
            end
            if @component['loadingImage']
              add_line "loadingImage: #{name_operand(@component['loadingImage'])},"
            end
            if @component['errorImage']
              add_line "errorImage: #{name_operand(@component['errorImage'])},"
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
                  add_line "#{swift_string_literal(key)}: #{swift_string_literal(value)}#{comma}"
                end
              end
              add_line(load_args.empty? ? "]" : "],")
            end

            load_args.each_with_index do |arg, index|
              add_line(index < load_args.length - 1 ? "#{arg}," : arg)
            end

            if !@component['headers'] && load_args.empty?
              # 最後のカンマを削除
              if @generated_code.last.end_with?(',')
                @generated_code[-1] = @generated_code.last.chomp(',')
              end
            end
          end
          add_line ")"

          # What VoiceOver reads for the image: its alt, nothing, or (an image
          # operating a control with no alt) the asset name as before.
          apply_image_accessibility

          # Apply all common modifiers (padding, frame, background, cornerRadius, border, margins, opacity, etc.)
          apply_modifiers

          # Apply binding modifiers (borderColor, background, etc. with @{...})
          apply_binding_modifiers

          generated_code
        end

        private

        # Delay and fade bounds (attribute_definitions.json NetworkImage).
        LOAD_MILLIS_RANGE = {
          'loadingDelay' => 0..2000,
          'transitionDuration' => 0..1000
        }.freeze

        # The arguments of the load listener (ticket
        # jui-networkimage-load-listener), in the order NetworkImage's init
        # declares them; [] when the image writes none of the four.
        def load_listener_arguments
          args = []
          renderer = @component['loadingRenderer']
          unless renderer.nil?
            if bound_value?(renderer)
              expr = SjuiTools::SwiftUI::Binding::BindingExpression.swift_text_expr(renderer.to_s[2..-2])
              args << "loadingRenderer: #{expr}"
            else
              args << "loadingRenderer: #{swift_string_literal(renderer.to_s)}"
            end
          end
          delay = load_millis('loadingDelay', @component['loadingDelay'])
          args << "loadingDelay: #{delay}" unless delay.nil?
          fade = load_millis('transitionDuration', @component['transitionDuration'])
          args << "transitionDuration: #{fade}" unless fade.nil?
          handler = @component['onLoadStateChange']
          if handler && is_binding?(handler)
            call = get_event_handler_invocation(handler, view_id, 'state')
            args << "onLoadStateChange: { state in #{call} }"
          end
          args
        end

        # A written number of milliseconds as an Int literal, held to its
        # declared range: a value outside it is WARNed and clamped. Not
        # bindable, so anything but a number is WARNed and left out.
        def load_millis(key, value)
          return nil if value.nil?

          number = value.is_a?(Numeric) ? value : (Float(value.to_s) rescue nil)
          if number.nil?
            SjuiTools::Core::Logger.warn "[sjui] NetworkImage #{@component['id'].inspect}: '#{key}' is #{value.inspect}, not a number of milliseconds; left out"
            return nil
          end
          range = LOAD_MILLIS_RANGE.fetch(key)
          millis = number.round
          unless range.cover?(millis)
            clamped = millis.clamp(range.min, range.max)
            SjuiTools::Core::Logger.warn "[sjui] NetworkImage #{@component['id'].inspect}: '#{key}' #{value} is outside #{range.min}-#{range.max} ms; #{clamped} is used"
            millis = clamped
          end
          millis
        end

        # A value is its declared spelling, case and all (1.9.0): NetworkImage
        # declares fit / fill / center / top / bottom / left / right and
        # AspectFill / AspectFit / Center.
        def map_content_mode_enum(mode)
          case (key = JsonUIShared::EnumSpelling.lowered(mode, 'NetworkImage', 'contentMode'))
          when 'aspectfill'
            '.fill'
          when 'aspectfit'
            '.fit'
          when 'center'
            '.center'
          when 'fill'
            # fill = stretch (canonical image.fill,
            # shared/core/attribute_semantics.json) — NetworkImage gained the
            # .stretch case for it.
            '.stretch'
          when 'top', 'bottom', 'left', 'right'
            # Positional modes draw unscaled and aligned — NetworkImage has
            # carried the cases since the contentMode wave; the map dropped
            # them to .fit (32 parity, d=50-79).
            ".#{key}"
          else
            '.fit'
          end
        end

        def map_rendering_mode(mode)
          case JsonUIShared::EnumSpelling.lowered(mode, 'NetworkImage', 'renderingMode')
          when 'template'
            '.template'
          when 'original'
            '.original'
          else
            'nil'
          end
        end
      end
    end
  end
end
