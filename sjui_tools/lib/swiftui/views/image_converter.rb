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
            # systemIcon reinterprets `src` as an SF Symbol name rather than an
            # asset name, which is a different Image initializer — not a
            # modifier — so it has to be decided here.
            system_icon = @component['systemIcon'] == true || @component['systemIcon'] == 'true'
            if processed_src.is_a?(Hash) && processed_src[:template_var]
              # テンプレート変数の場合
              var = "data.#{to_camel_case(processed_src[:template_var])}"
              add_line(system_icon ? "Image(systemName: #{var})" : "Image(#{var})")
            elsif system_icon
              add_line "Image(systemName: \"#{@component['src']}\")"
            else
              # 通常の画像名
              add_line "Image(\"#{@component['src']}\")"
            end
          elsif @component['defaultImage'] || @component['errorImage'] || @component['loadingImage']
            # Fallback imagery when no src resolves. A STATIC Image never
            # loads over the network, so `errorImage` / `loadingImage` cannot
            # mean in-flight states here — they join the fallback chain
            # (defaultImage first, the UIKit runtime honours the full
            # semantics). Better an intended asset than the photo glyph.
            fallback = @component['defaultImage'] || @component['errorImage'] || @component['loadingImage']
            add_line "Image(\"#{fallback}\")"
          else
            # デフォルトのシステムイメージ
            add_line "Image(systemName: \"photo\")"
          end

          # renderingMode — template tints via .foregroundColor/tint,
          # original suppresses tinting (same mapping the Compose side ships).
          if @component['renderingMode']
            mode = @component['renderingMode'].to_s.downcase == 'template' ? '.template' : '.original'
            @modifier_bag.append(:component_specific, ".renderingMode(#{mode})")
          end

          @modifier_bag.append(:component_specific, ".resizable()")

          apply_highlight_src

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

          apply_pinch_zoom

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

        # minZoom/maxZoom — pinch zoom on a static image (mode: swiftui;
        # the UIKit runtime has its own UIScrollView zoom). Cumulative
        # MagnifyGesture scale, clamped to the declared bounds; state rides a
        # per-view @State var. Either bound alone still works: the other side
        # defaults to no-zoom-out (1.0) / the given ceiling.
        def apply_pinch_zoom
          min_zoom = @component['minZoom']
          max_zoom = @component['maxZoom']
          return unless min_zoom || max_zoom

          id_part = to_camel_case(@component['id'] || 'image')
          state_var = "#{id_part}ZoomScale"
          @state_variables << "@State private var #{state_var}: CGFloat = 1.0"
          lower = min_zoom || 1.0
          upper = max_zoom || 'CGFloat.greatestFiniteMagnitude'
          @modifier_bag.append(:component_specific, ".scaleEffect(#{state_var})")
          @modifier_bag.register(:on_pinch, [
            ".simultaneousGesture(",
            "    MagnifyGesture().onChanged { value in",
            "        #{state_var} = min(max(value.magnification, #{lower}), #{upper})",
            "    }",
            ")"
          ])
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
        private

        # highlightSrc — the image shown while the view is pressed.
        #
        # UIKit gets this for free: UIImageView has `highlightedImage`, and
        # SJUIImageView sets it (SJUIImageView.swift:84). SwiftUI has no such
        # property, so the swap has to be driven by a press gesture, which is
        # what this emits. Local `@State` rather than the data object: it is
        # transient view state, not screen state, and adding a data property for
        # it would change the generated ViewModel.
        def apply_highlight_src
          highlight = @component['highlightSrc']
          return if highlight.nil?

          state_var = "#{(@component['id'] || 'image').gsub(/[^A-Za-z0-9]/, '_')}IsPressed"
          @state_variables ||= []
          @state_variables << "@State private var #{state_var} = false"

          resolved = if is_binding?(highlight)
                       "data.#{extract_binding_property(highlight)}"
                     else
                       "\"#{highlight}\""
                     end
          # The highlighted image replaces the base one entirely, so it is an
          # overlay with the base hidden underneath rather than a second layer.
          @modifier_bag.append(:component_specific, ".opacity(#{state_var} ? 0 : 1)")
          @modifier_bag.append(:component_specific, ".overlay(")
          @modifier_bag.append(:component_specific, "    Image(#{resolved})")
          @modifier_bag.append(:component_specific, "        .resizable()")
          @modifier_bag.append(:component_specific, "        .opacity(#{state_var} ? 1 : 0)")
          @modifier_bag.append(:component_specific, ")")
          @modifier_bag.append(
            :component_specific,
            ".onLongPressGesture(minimumDuration: 0, pressing: { #{state_var} = $0 }, perform: {})"
          )
        end
      end
    end
  end
end
