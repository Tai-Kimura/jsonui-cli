# frozen_string_literal: true

require_relative 'base_view_converter'
require_relative 'text_style_helper'
require_relative '../helpers/font_helper'
require_relative '../helpers/string_manager_helper'
require_relative 'frame_helper'

module SjuiTools
  module SwiftUI
    module Views
      # Generated code label/text converter
      # Dynamic mode equivalent: Sources/SwiftJsonUI/Classes/SwiftUI/Dynamic/Converters/TextConverter.swift
      class LabelConverter < BaseViewConverter
        include SjuiTools::SwiftUI::Helpers::FontHelper
        include SjuiTools::SwiftUI::Helpers::StringManagerHelper
        include SjuiTools::SwiftUI::Views::FrameHelper
        include SjuiTools::SwiftUI::Views::TextStyleHelper
        def convert
          # Get text handler for this component
          label_handler = @binding_handler.is_a?(SjuiTools::SwiftUI::Binding::LabelBindingHandler) ?
                          @binding_handler :
                          SjuiTools::SwiftUI::Binding::LabelBindingHandler.new

          # Get text content with binding support
          text_content = get_text_with_string_manager(label_handler.get_text_content(@component))

          # hint / hintAttributes — the Label placeholder (canonical: UIKit
          # SJUILabel swaps in the styled hint when the text is empty, and
          # requires BOTH keys; `placeholder` is the declared alias of hint,
          # hintAttributes.fontColor wins over hintColor). kjui has carried
          # the same branch since 2026-07; this closes the ios side.
          hint = label_hint_config
          raw_text = @component['text'] || ''
          hint_static = hint && raw_text.to_s.strip.empty?
          hint_dynamic = hint && !hint_static &&
                         raw_text.is_a?(String) && raw_text.strip.match?(/\A@\{[^}]+\}\z/)
          hint_condition = nil
          if hint_static
            text_content = get_text_with_string_manager("\"#{hint[:text]}\"")
          elsif hint_dynamic
            hint_literal = get_text_with_string_manager("\"#{hint[:text]}\"")
            # The emptiness test must run on the ORIGINAL expression — the
            # wrapped ternary is never empty (its fallback is the hint).
            hint_condition = "(#{text_content}).isEmpty"
            text_content = "(#{hint_condition} ? #{hint_literal} : #{text_content})"
          end

          has_partials = @component['partialAttributes'].is_a?(Array) &&
                         !@component['partialAttributes'].empty?

          # Use PartialAttributedText for all text rendering
          add_line "PartialAttributedText("
          indent do
            add_line "#{text_content},"

            # Add partialAttributes if present
            if has_partials
              add_line "partialAttributes: ["
              indent do
                @component['partialAttributes'].each_with_index do |partial, index|
                  add_line "PartialAttribute("
                  indent do
                    # Handle range - either array, binding, or string
                    if partial['range']
                      if partial['range'].is_a?(Array) && partial['range'].length == 2
                        add_line "range: #{partial['range'][0]}..<#{partial['range'][1]},"
                      elsif partial['range'].is_a?(String) && is_binding?(partial['range'])
                        prop = extract_binding_property(partial['range'])
                        add_line "textPattern: data.#{prop},"
                      elsif partial['range'].is_a?(String)
                        # Use StringManager for snake_case range text
                        range_text = get_text_with_string_manager("\"#{partial['range']}\"")
                        add_line "textPattern: #{range_text},"
                      end
                    end

                    # Add fontColor
                    if partial['fontColor']
                      color = get_swiftui_color(partial['fontColor'])
                      add_line "fontColor: #{color},"
                    end

                    # Add fontSize
                    if partial['fontSize']
                      add_line "fontSize: #{partial['fontSize']},"
                    end

                    # Add fontWeight
                    if partial['fontWeight']
                      weight = font_weight_to_swiftui(partial['fontWeight'])
                      add_line "fontWeight: #{weight},"
                    end

                    # Add underline
                    if partial['underline']
                      add_line "underline: true,"
                    end

                    # Add strikethrough
                    if partial['strikethrough']
                      add_line "strikethrough: true,"
                    end

                    # Add backgroundColor
                    if partial['background']
                      bg_color = get_swiftui_color(partial['background'])
                      add_line "backgroundColor: #{bg_color},"
                    end

                    # Add onClick as closure (SwiftUI uses onClick, not onclick)
                    if partial['onClick']
                      method_name = extract_binding_property(partial['onClick'])
                      add_line "onClick: { data.#{method_name}?() },"
                    end

                    # Remove trailing comma from last item
                    @generated_code[-1] = @generated_code[-1].chomp(',')
                  end
                  add_line ")#{ index < @component['partialAttributes'].length - 1 ? ',' : '' }"
                end
              end
              add_line "],"
            end

            # Add fontSize (the hint's size wins while the hint is showing;
            # statically-empty text always shows it)
            if hint_static && hint[:size]
              add_line "fontSize: #{hint[:size]},"
            elsif @component['fontSize']
              add_line "fontSize: #{bound_number(@component['fontSize']) || @component['fontSize']},"
            end

            # Add fontWeight (handle both fontWeight and font:"bold")
            #
            # The type depends on which initializer the call resolves to. With
            # partialAttributes present that is the PartialAttribute-taking one,
            # whose fontWeight is a Font.Weight; the String convenience
            # initializer does not accept partialAttributes, so emitting the
            # string form alongside them yields Swift that does not compile
            # ("cannot convert value of type 'String' to expected argument type
            # 'Font.Weight'"). StateAwareButtonView has a combined overload,
            # which is why Button never hit this.
            weight_name = if @component['fontWeight']
                            @component['fontWeight']
                          elsif @component['font'] == 'bold'
                            'bold'
                          end
            if weight_name
              # `fontWeight` is declared `["string", "number"]`, and `600` is
              # an example the declaration itself gives. The String
              # initializer resolves through `Font.Weight.from(string:)`,
              # which knows names only, so a numeric weight arrived as
              # .regular — the same defect Button had. Resolving it here also
              # picks the Font.Weight initializer, which is the one the
              # partialAttributes overload needs anyway.
              numeric_weight = weight_name.to_s.match?(/\A\d+\z/) &&
                               numeric_weight_table[weight_name.to_i]
              if has_partials || numeric_weight
                add_line "fontWeight: #{numeric_weight || font_weight_to_swiftui(weight_name)},"
              else
                add_line "fontWeight: \"#{weight_name}\","
              end
            end

            # Add fontFamily (with binding support)
            if @component['fontFamily']
              if is_binding?(@component['fontFamily'])
                property_name = extract_binding_property(@component['fontFamily'])
                add_line "fontFamily: data.#{property_name},"
              else
                add_line "fontFamily: \"#{@component['fontFamily']}\","
              end
            end

            # Add fontColor (with binding support). When a hint is showing
            # (statically empty text, or a bound text that is empty at
            # runtime) the hint colour replaces the base one.
            base_color = if @component['enabled'] == false && @component['disabledFontColor']
                           get_font_color_with_binding(@component['disabledFontColor'])
                         elsif @component['fontColor']
                           get_font_color_with_binding(@component['fontColor'])
                         end
            if hint_static && hint[:color]
              add_line "fontColor: #{hint[:color]},"
            elsif hint_dynamic && hint[:color]
              add_line "fontColor: (#{hint_condition} ? #{hint[:color]} : #{base_color || 'nil'}),"
            elsif base_color
              add_line "fontColor: #{base_color},"
            end


            # Add underline
            if @component['underline']
              add_line "underline: true,"
            end

            # Add strikethrough
            if @component['strikethrough']
              add_line "strikethrough: true,"
            end

            # Add lineSpacing. `.to_f` on a binding is 0.0, which is how a
            # bound lineSpacing froze to no spacing at all and a bound
            # lineHeightMultiple froze to (0 - 1) * fontSize — a NEGATIVE
            # constant that pulled the lines together.
            if @component['lineHeightMultiple']
              add_line "lineSpacing: #{line_spacing_from_multiple(@component['lineHeightMultiple'])},"
            elsif @component['lineSpacing']
              add_line "lineSpacing: #{bound_number(@component['lineSpacing']) || @component['lineSpacing'].to_f},"
            end

            # Add lineLimit. 0 means "unlimited" and has to stay a `nil` —
            # `.to_i` made every bound declaration exactly that, so a bound
            # `lines` silently unlimited the label. The bound form carries the
            # same 0-means-nil rule into the Swift.
            if @component['lines']
              if (bound_lines = bound_number(@component['lines'], cast: 'Int'))
                add_line "lineLimit: (#{bound_lines} == 0 ? nil : #{bound_lines}),"
              elsif @component['lines'].to_i == 0
                add_line "lineLimit: nil,"
              else
                add_line "lineLimit: #{@component['lines'].to_i},"
              end
            elsif @component['autoShrink']
              add_line "lineLimit: 1,"
            end

            # Add textAlignment (default to .leading). A binding is not one of
            # the spellings `text_alignment_to_swiftui` switches on, so it hit
            # the else branch and froze every bound alignment to .leading.
            alignment = if @component['textAlign']
                          bound_text_alignment(@component['textAlign']) ||
                            text_alignment_to_swiftui(@component['textAlign'])
                        else
                          '.leading'
                        end
            add_line "textAlignment: #{alignment},"

            # Add linkable if true. Ruby truthiness never entered here for a
            # binding (`"@{x}" == true` is false), so the declaration was
            # dropped; the bound form passes the condition to Swift instead.
            if (bound_linkable = bound_bool(@component['linkable']))
              add_line "linkable: #{bound_linkable},"
            elsif @component['linkable'] == true || @component['linkable'] == 'true'
              add_line "linkable: true,"
            end

            # highlightAttributes / highlightColor / selected. Emitted last
            # because Swift requires argument labels in declaration order and
            # these are the trailing parameters of PartialAttributedText.
            emit_highlight_attributes

            # Remove trailing comma from last parameter
            @generated_code[-1] = @generated_code[-1].chomp(',')
          end
          add_line ")"

          apply_text_shadow

          # lineBreakMode (SwiftJsonUI uses short forms: Char, Clip, Word, Head, Middle, Tail)
          if @component['lineBreakMode']
            mode = case @component['lineBreakMode']
                   when 'Head'
                     '.head'
                   when 'Middle'
                     '.middle'
                   when 'Tail'
                     '.tail'
                   when 'Clip'
                     '.tail'
                   else
                     nil
                   end
            @modifier_bag.append(:component_specific, ".truncationMode(#{mode})") if mode
          end

          # autoShrink & minimumScaleFactor
          if @component['autoShrink']
            scale_factor = bound_number(@component['minimumScaleFactor']) ||
                           @component['minimumScaleFactor'] || 0.5
            @modifier_bag.append(:component_specific, ".minimumScaleFactor(#{scale_factor})")
          elsif @component['minimumScaleFactor']
            factor = bound_number(@component['minimumScaleFactor']) || @component['minimumScaleFactor']
            @modifier_bag.append(:component_specific, ".minimumScaleFactor(#{factor})")
          end

          # edgeInset (Label内部パディング - UIKitに合わせて配列形式対応)
          if @component['edgeInset']
            edge_inset = @component['edgeInset']
            if edge_inset.is_a?(Array)
              case edge_inset.length
              when 1
                @modifier_bag.append(:padding, ".padding(#{edge_inset[0].to_i})")
              when 2
                @modifier_bag.append(:padding, ".padding(.vertical, #{edge_inset[0].to_i})")
                @modifier_bag.append(:padding, ".padding(.horizontal, #{edge_inset[1].to_i})")
              when 3
                @modifier_bag.append(:padding, ".padding(.top, #{edge_inset[0].to_i})")
                @modifier_bag.append(:padding, ".padding(.horizontal, #{edge_inset[1].to_i})")
                @modifier_bag.append(:padding, ".padding(.bottom, #{edge_inset[2].to_i})")
              when 4
                @modifier_bag.append(:padding, ".padding(EdgeInsets(top: #{edge_inset[0].to_i}, leading: #{edge_inset[1].to_i}, bottom: #{edge_inset[2].to_i}, trailing: #{edge_inset[3].to_i}))")
              end
            elsif edge_inset.is_a?(String) && edge_inset.include?('|')
              # パイプ区切り形式もサポート (UIKit互換)
              parts = edge_inset.split('|').map(&:to_i)
              case parts.length
              when 1
                @modifier_bag.append(:padding, ".padding(#{parts[0]})")
              when 2
                @modifier_bag.append(:padding, ".padding(.vertical, #{parts[0]})")
                @modifier_bag.append(:padding, ".padding(.horizontal, #{parts[1]})")
              when 3
                @modifier_bag.append(:padding, ".padding(.top, #{parts[0]})")
                @modifier_bag.append(:padding, ".padding(.horizontal, #{parts[1]})")
                @modifier_bag.append(:padding, ".padding(.bottom, #{parts[2]})")
              when 4
                @modifier_bag.append(:padding, ".padding(EdgeInsets(top: #{parts[0]}, leading: #{parts[1]}, bottom: #{parts[2]}, trailing: #{parts[3]}))")
              end
            else
              @modifier_bag.append(:padding, ".padding(#{edge_inset.to_i})")
            end
          end

          # Apply frame modifiers for weighted views FIRST
          # If this label has a weight in a horizontal/vertical container, make it fill the appropriate dimension
          @skip_frame_width = false
          if @component['weight'] && @component['weight'].to_f > 0
            parent_orientation = @component['parent_orientation']

            if parent_orientation == 'horizontal'
              # In horizontal stack with weight - fill width
              # Add alignment based on textAlign
              frame_alignment = case @component['textAlign'].to_s.downcase
              when 'center'
                '.center'
              when 'right', 'trailing'
                '.trailing'
              else
                '.leading'
              end
              @modifier_bag.append(:frame_size, ".frame(maxWidth: .infinity, alignment: #{frame_alignment})")
              @skip_frame_width = true  # Prevent frame_helper from adding duplicate maxWidth
            elsif parent_orientation == 'vertical'
              # In vertical stack with weight - fill height
              @modifier_bag.append(:frame_size, ".frame(maxHeight: .infinity)")
            end
          end

          # Apply padding (internal spacing) first
          apply_padding

          # Apply frame size (width/height) after padding -- skip width if already set by weight
          apply_frame_size

          # Apply frame constraints (minWidth, maxWidth, minHeight, maxHeight)
          apply_frame_constraints

          # Apply background and corner radius AFTER padding
          # This ensures the background includes the padding area
          if @component['background']
            color = get_swiftui_color(@component['background'])
            @modifier_bag.register(:background, ".background(#{color})")
          end

          if @component['cornerRadius']
            @modifier_bag.register(:corner_radius, ".cornerRadius(#{@component['cornerRadius'].to_i})")
          end

          # ボーダー（cornerRadiusの直後、marginsの前に適用）
          if (border_code = border_overlay)
            @modifier_bag.register(:border, border_code)
          end

          # Apply binding-specific modifiers (borderColor, fontColor, etc.)
          # Must be BEFORE margins so borders don't include margin area
          apply_binding_modifiers

          # Apply margins (external spacing)
          apply_margins

          # Opacity (alpha/opacity)
          alpha_value = attr_with_alias('opacity', 'alpha')
          if alpha_value
            if is_binding?(alpha_value)
              @modifier_bag.register(:opacity, ".opacity(#{binding_data_expr(alpha_value)})")
            else
              @modifier_bag.register(:opacity, ".opacity(#{alpha_value})")
            end
          end

          # Hidden — visibility:"invisible" shorthand: keep layout space,
          # hide drawing + accessibility (never collapse)
          hidden_value = @component['hidden']
          if hidden_value == true
            @modifier_bag.register(:hidden, ".opacity(0).accessibilityHidden(true)")
          elsif is_binding?(hidden_value)
            hidden_expr = binding_data_expr(hidden_value)
            @modifier_bag.register(:hidden, ".opacity(#{hidden_expr} ? 0 : 1).accessibilityHidden(#{hidden_expr})")
          end

          # onClick
          if @component['onClick'] && is_binding?(@component['onClick']) && @component['enabled'] != false
            on_click_lines = build_on_click_lines(@component['onClick'])
            @modifier_bag.register(:on_click, on_click_lines)
          end

          generated_code
        end

        # {text:, color:, size:} when the Label hint contract is satisfied
        # (hint/placeholder + hintAttributes both present).
        def label_hint_config
          attrs = @component['hintAttributes']
          hint = @component['hint'] || @component['placeholder']
          return nil unless attrs.is_a?(Hash) && hint.is_a?(String) && !hint.empty?

          color_value = attrs['fontColor'] || @component['hintColor']
          {
            text: hint,
            color: color_value ? get_swiftui_color(color_value) : nil,
            size: attrs['fontSize']
          }
        end

        private

        # UIKit's formula, `(multiple - 1) * fontSize`, with either operand
        # possibly bound. Both static operands keep the exact arithmetic the
        # generator did before (a Ruby Float, printed the same way).
        def line_spacing_from_multiple(multiple)
          bound_multiple = bound_number(multiple)
          bound_size = bound_number(@component['fontSize'])
          return (multiple.to_f - 1) * (@component['fontSize'] || 17).to_i if bound_multiple.nil? && bound_size.nil?

          multiple_expr = bound_multiple || multiple.to_f
          size_expr = bound_size || (@component['fontSize'] || 17).to_i
          "((#{multiple_expr} - 1) * #{size_expr})"
        end

        # Get fontColor with binding support
        # Supports both direct color values and @{propertyName} binding expressions
        def get_font_color_with_binding(font_color)
          return nil unless font_color

          if is_binding?(font_color)
            # Binding expression - get color from data
            property_name = extract_binding_property(font_color)
            data_def = ColorHelper.data_definitions[property_name]
            if data_def && data_def['class'].to_s == 'String'
              # String type: resolve via configuration (no cast needed)
              "SwiftJsonUIConfiguration.shared.getColor(for: data.#{property_name})"
            else
              # Color type: use directly
              "data.#{property_name}"
            end
          else
            # Direct color value
            get_swiftui_color(font_color)
          end
        end
        # textShadow — `{ color:, blur:, offset: [x, y] }`, the same shape UIKit
        # turns into an NSShadow (SJUILabel: `attributes[.shadow] = s`).
        #
        # SwiftUI's `.shadow(color:radius:x:y:)` is the direct equivalent. The
        # attribute was read by nobody on the SwiftUI path, so a label with a
        # shadow rendered flat. A bare string form is accepted as a colour with
        # UIKit's default 1pt blur, since the attribute is declared
        # `["string", "object"]`.
        def apply_text_shadow
          shadow = @component['textShadow']
          return if shadow.nil?

          if shadow.is_a?(String)
            @modifier_bag.append(
              :component_specific,
              ".shadow(color: #{get_swiftui_color(shadow)}, radius: 1, x: 0, y: 1)"
            )
            return
          end
          return unless shadow.is_a?(Hash)

          color = shadow['color'] ? get_swiftui_color(shadow['color']) : 'Color.black.opacity(0.3)'
          blur = shadow['blur'] || 1
          offset = shadow['offset']
          x, y = offset.is_a?(Array) && offset.length >= 2 ? [offset[0], offset[1]] : [0, 1]
          @modifier_bag.append(
            :component_specific,
            ".shadow(color: #{color}, radius: #{blur}, x: #{x}, y: #{y})"
          )
        end
        # highlightAttributes / highlightColor — the styling a label switches to
        # while it is selected.
        #
        # UIKit keeps two attribute dictionaries and swaps between them when
        # `selected` flips (SJUILabel#applyAttributedText:
        # `let attr = selected ? highlightAttributes : attributes`), so the
        # driver here is `selected` as well. A press gesture would be the wrong
        # trigger: selection is state the screen owns, and it outlives the touch.
        #
        # `highlightAttributes` wins over `highlightColor` when both are given,
        # and an empty attribute object falls through to `highlightColor` —
        # both matching the precedence in SJUILabel's creator
        # (`if !attr["highlightAttributes"].isEmpty ... else if highlightColor`).
        def emit_highlight_attributes
          attrs = @component['highlightAttributes']
          highlight_color = @component['highlightColor']

          fields = attrs.is_a?(Hash) ? highlight_attribute_fields(attrs) : []
          if fields.empty? && highlight_color
            fields = ["fontColor: #{get_font_color_with_binding(highlight_color)}"]
          end
          return if fields.empty?

          add_line "highlightAttributes: TextHighlightAttributes(#{fields.join(', ')}),"
          add_line "isHighlighted: #{highlight_condition},"
        end

        # Fields for the TextHighlightAttributes initializer.
        #
        # Emitted in the struct's declaration order (fontFamily, fontSize,
        # fontWeight, fontColor, lineHeightMultiple, textAlignment) because
        # Swift requires argument labels in that order.
        def highlight_attribute_fields(attrs)
          fields = []
          font = attrs['font']

          # UIKit resolves the literal name "bold" to the bold system font
          # rather than to a family, so it maps to a weight and not a family:
          # `UIFont(name: highlightName, size:) ?? (highlightName == "bold" ? ...)`
          fields << "fontFamily: \"#{font}\"" if font && font != 'bold'
          fields << "fontSize: #{attrs['fontSize'].to_f}" if attrs['fontSize']
          fields << 'fontWeight: .bold' if font == 'bold'
          if attrs['fontColor']
            fields << "fontColor: #{get_font_color_with_binding(attrs['fontColor'])}"
          end
          if attrs['lineHeightMultiple']
            fields << "lineHeightMultiple: #{attrs['lineHeightMultiple'].to_f}"
          end
          if attrs['textAlign']
            alignment = text_alignment_to_swiftui(attrs['textAlign'])
            fields << "textAlignment: #{alignment}" if alignment
          end
          fields
        end

        # The `selected` state that decides which attribute set is in force.
        # Absent means never highlighted, which is what UIKit does with a label
        # whose `selected` is never set.
        def highlight_condition
          value = @component['selected']
          return 'true' if value == true || value == 'true'
          return "data.#{extract_binding_property(value)}" if value.is_a?(String) && is_binding?(value)

          'false'
        end
      end
    end
  end
end
