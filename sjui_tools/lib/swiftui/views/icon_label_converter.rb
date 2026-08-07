#!/usr/bin/env ruby

require_relative 'base_view_converter'

module SjuiTools
  module SwiftUI
    module Views
      class IconLabelConverter < BaseViewConverter
        def convert
          text = @component['text'] || ""
          iconOn = @component['icon_on']
          iconOff = @component['icon_off']
          iconPosition = @component['iconPosition'] || 'left'
          onClick = @component['onClick']

          # IconLabelViewまたはIconLabelButtonを使用
          if onClick
            add_line "IconLabelButton("
          else
            add_line "IconLabelView("
          end
          
          indent do
            # text. A binding was pasted between the quotes, so the label
            # showed the characters `@{...}` instead of the bound value.
            add_line "text: #{bound_string(@component['text']) || "\"#{text}\""},"
            
            # icons
            if iconOn
              add_line "iconOn: \"#{iconOn}\","
            end
            
            if iconOff
              add_line "iconOff: \"#{iconOff}\","
            end
            
            # iconPosition
            case iconPosition.downcase
            when 'top'
              add_line "iconPosition: .top,"
            when 'right'
              add_line "iconPosition: .right,"
            when 'bottom'
              add_line "iconPosition: .bottom,"
            else # left or default
              add_line "iconPosition: .left,"
            end
            
            # iconSize — declared number|array: a number sizes both edges,
            # a two-element [width, height] sizes them separately. The raw
            # interpolation put a Ruby array literal into Swift for the array
            # face (`iconSize: [40, 20],` does not compile); the axes go to
            # the dedicated parameters instead.
            if (icon_size = @component['iconSize'])
              if icon_size.is_a?(Array)
                add_line "iconWidth: #{icon_size[0]}," if icon_size[0]
                add_line "iconHeight: #{icon_size[1] || icon_size[0]}," if icon_size[0]
              else
                add_line "iconSize: #{icon_size},"
              end
            end
            
            # iconMargin
            if @component['iconMargin']
              add_line "iconMargin: #{@component['iconMargin']},"
            end
            
            # fontSize
            if @component['fontSize']
              add_line "fontSize: #{@component['fontSize']},"
            end
            
            # fontColor
            if @component['fontColor']
              color = get_swiftui_color(@component['fontColor'])
              add_line "fontColor: #{color},"
            end
            
            # selectedFontColor
            if @component['selectedFontColor']
              color = get_swiftui_color(@component['selectedFontColor'])
              add_line "selectedFontColor: #{color},"
            end
            
            # fontName — weight spellings route to fontWeight instead
            # (IconLabelView carries the weight; the converter dropped
            # `font: "bold"` on the floor — 32 parity). fontWeight is emitted
            # AFTER isSelected: Swift call sites follow the init's declared
            # argument order (fontName, isSelected, fontWeight).
            font_value = @component['font'].to_s
            font_weight = font_value.downcase if %w[bold semibold medium].include?(font_value.downcase)
            if @component['font'] && !font_weight
              add_line "fontName: \"#{@component['font']}\","
            end

            # selected — the state that chooses icon_on over icon_off and
            # selectedFontColor over fontColor. Nothing read it here, so both
            # attributes were inert on the SwiftUI path: IconLabelView defaults
            # isSelected to false and the converter never passed anything.
            if (selected = selected_expression)
              add_line "isSelected: #{selected},"
            end

            if font_weight
              add_line "fontWeight: .#{font_weight},"
            end

            # action for button (最後のパラメータなのでカンマなし)
            if onClick
              method_name = extract_binding_property(onClick)
              add_line "action: {"
              indent do
                add_line "data.#{method_name}?()"
              end
              add_line "}"
            else
              # 最後のカンマを削除
              if @generated_code.last.end_with?(',')
                @generated_code[-1] = @generated_code.last.chomp(',')
              end
            end
          end
          add_line ")"

          apply_text_shadow

          # Apply common modifiers
          apply_modifiers
          
          generated_code
        end

        private

        # `selected` is a boolean|binding. A binding resolves against the data
        # object; a literal passes straight through. Returns nil when absent so
        # the argument is omitted and the library default (false) stands.
        def selected_expression
          value = @component['selected']
          return nil if value.nil?
          return 'true' if value == true || value == 'true'
          return 'false' if value == false || value == 'false'
          return "data.#{extract_binding_property(value)}" if is_binding?(value)

          nil
        end

        # textShadow — declared as a plain string here (a colour) rather than the
        # object form Label takes, and UIKit passes it straight through to
        # SJUILabelWithIcon as `shadow:`. Nothing read it on the SwiftUI path.
        # The object form is accepted too, so a layout that shares a style block
        # with a Label behaves the same.
        def apply_text_shadow
          shadow = @component['textShadow']
          return if shadow.nil?

          if shadow.is_a?(Hash)
            color = shadow['color'] ? get_swiftui_color(shadow['color']) : 'Color.black.opacity(0.3)'
            blur = shadow['blur'] || 1
            offset = shadow['offset']
            x, y = offset.is_a?(Array) && offset.length >= 2 ? [offset[0], offset[1]] : [0, 1]
          else
            color = get_swiftui_color(shadow)
            blur = 1
            x = 0
            y = 1
          end
          @modifier_bag.append(
            :component_specific,
            ".shadow(color: #{color}, radius: #{blur}, x: #{x}, y: #{y})"
          )
        end
      end
    end
  end
end