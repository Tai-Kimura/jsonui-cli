#!/usr/bin/env ruby

require_relative 'base_view_converter'
require_relative 'text_style_helper'
require_relative '../helpers/font_helper'
require_relative '../helpers/string_manager_helper'

module SjuiTools
  module SwiftUI
    module Views
      # Generated code button converter
      # Dynamic mode equivalent: Sources/SwiftJsonUI/Classes/SwiftUI/Dynamic/Converters/ButtonConverter.swift
      class ButtonConverter < BaseViewConverter
        include SjuiTools::SwiftUI::Helpers::FontHelper
        include SjuiTools::SwiftUI::Helpers::StringManagerHelper
        include SjuiTools::SwiftUI::Views::TextStyleHelper
        def convert
          # Always use StateAwareButtonView for dynamic state change support
          convert_state_aware_button
        end

        private

        def convert_state_aware_button
          image = @component['image']
          has_image = !image.nil? && !image.to_s.empty?
          # "Button" is the placeholder for a button with nothing in it. An
          # icon-only button has content, so it must not render the word
          # "Button" beside its icon. Without an icon the fallback is
          # unchanged (including the explicit empty-string case).
          text = if has_image
                   @component['text'].to_s
                 else
                   @component['text'] || "Button"
                 end
          action = @component['onClick']

          # Use StateAwareButtonView for state-dependent styling
          # `image:` / `imageTint:` are new parameters, so generated output
          # for an icon button does not compile against an older library.
          add_line '// Requires SwiftJsonUI >= 10.9.0 (Button image)' if has_image
          add_line "StateAwareButtonView("
          indent do
            # Process text with binding support
            if text.include?('@{')
              # Text with interpolation: "Some text @{property} more text"
              interpolated = text.gsub(/@\{([^}]+)\}/) do |match|
                property_name = $1
                # For interpolated text, use data directly
                "\\(data.#{property_name})"
              end
              escaped_text = interpolated.gsub('"', '\\"').gsub("\n", "\\n")
              add_line "text: \"#{escaped_text}\","
            else
              # Check if it's snake_case for localized strings
              text_content = get_text_with_string_manager("\"#{text}\"")
              # If it's a localized string (StringManager call or .localized()), use it directly
              if text_content.start_with?('StringManager.') || text_content.end_with?('.localized()')
                add_line "text: #{text_content},"
              else
                # Regular text - escape double quotes
                escaped_text = text.gsub('"', '\\"')
                add_line "text: \"#{escaped_text}\","
              end
            end

            # Add partialAttributes if present (same as label)
            if @component['partialAttributes'] && @component['partialAttributes'].is_a?(Array) && !@component['partialAttributes'].empty?
              add_line "partialAttributes: ["
              indent do
                @component['partialAttributes'].each_with_index do |partial, index|
                  add_line "PartialAttribute("
                  indent do
                    # Handle range - either array or string
                    if partial['range']
                      if partial['range'].is_a?(Array) && partial['range'].length == 2
                        add_line "range: #{partial['range'][0]}..<#{partial['range'][1]},"
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
                    if line_decoration?(partial['underline'])
                      add_line "underline: true,"
                    end

                    # Add strikethrough
                    if line_decoration?(partial['strikethrough'])
                      add_line "strikethrough: true,"
                    end

                    # Add backgroundColor
                    if partial['background']
                      bg_color = get_swiftui_color(partial['background'])
                      add_line "backgroundColor: #{bg_color},"
                    end

                    # Add onClick as closure (SwiftUI uses onClick, not onclick)
                    # onClick (camelCase) -> binding format only (@{functionName})
                    if partial['onClick'] && is_binding?(partial['onClick'])
                      # For partial click, no value to pass
                      handler_call = get_event_handler_invocation(partial['onClick'], @component['id'] || 'button', nil)
                      add_line "onClick: { #{handler_call} },"
                    end

                    # Remove trailing comma from last item
                    @generated_code[-1] = @generated_code[-1].chomp(',')
                  end
                  add_line ")#{ index < @component['partialAttributes'].length - 1 ? ',' : '' }"
                end
              end
              add_line "],"
            end

            # Action (onClick uses binding format @{functionName})
            # onClick (camelCase) -> binding format only (@{functionName})
            if action && is_binding?(action)
              id = @component['id'] || 'button'
              handler_call = get_event_handler_invocation(action, id, nil)
              add_line "action: { #{handler_call} },"
            else
              add_line "action: { },"
            end

            # Font properties
            if @component['fontSize']
              add_line "fontSize: #{@component['fontSize'].to_i},"
            end
            # StateAwareButtonView takes the weight either as a Font.Weight or
            # as the String spelling (it has both initializers), and the
            # String one is what the static path uses. A binding went into
            # those quotes and the button asked for a weight literally named
            # "@{weight}", which `Font.Weight.from(string:)` resolves to
            # .regular — the declaration compiled and did nothing. The bound
            # form resolves the same vocabulary itself and passes a
            # Font.Weight, which picks the other initializer.
            if (bound_weight = swift_weight_expr(@component['fontWeight']) ||
                               swift_weight_expr(@component['font']))
              add_line "fontWeight: #{bound_weight},"
            elsif (numeric_weight = numeric_weight_table[@component['fontWeight'].to_i]) &&
                  @component['fontWeight'].to_s.match?(/\A\d+\z/)
              # A NUMERIC weight is a declared spelling — "e.g. 'bold',
              # 'semibold', '500', 600". The String initializer resolves it
              # through `Font.Weight.from(string:)`, which knows names only,
              # so `600` arrived as `.regular`. Resolve it here instead, which
              # also picks the Font.Weight initializer.
              add_line "fontWeight: #{numeric_weight},"
            elsif @component['fontWeight']
              add_line "fontWeight: \"#{@component['fontWeight']}\","
            elsif @component['font']
              add_line "fontWeight: \"#{@component['font']}\","
            end
            # fontFamily rides into StateAwareButtonView, which routes it
            # through PartialAttributedText's FontSpec path (family + weight +
            # size to Configuration.fontProvider) — the declared semantics.
            # Read-only binding: the parameter is a String?, not a Binding.
            if @component['fontFamily']
              if is_binding?(@component['fontFamily'])
                prop = extract_binding_property(@component['fontFamily'])
                add_line "fontFamily: data.#{prop},"
              else
                add_line "fontFamily: \"#{@component['fontFamily']}\","
              end
            end

            # Color properties
            if @component['fontColor']
              add_line "fontColor: #{get_swiftui_color(@component['fontColor'])},"
            end
            if @component['background']
              add_line "backgroundColor: #{get_swiftui_color(@component['background'])},"
            end

            # State-dependent colors
            if @component['tapBackground']
              add_line "tapBackground: #{get_swiftui_color(@component['tapBackground'])},"
            end
            highlight_color = attr_with_alias('highlightColor', 'hilightColor')
            if highlight_color
              add_line "highlightColor: #{get_swiftui_color(highlight_color)},"
            end
            # highlightBackground is the UIKit-era spelling of the pressed-state
            # background; the SwiftUI component's parameter is tapBackground.
            # Emitting the attribute name verbatim produced an "extra argument"
            # compile error (caught by the codegen parity host). Canonical
            # tapBackground wins when both are present.
            if @component['highlightBackground'] && !@component['tapBackground']
              add_line "tapBackground: #{get_swiftui_color(@component['highlightBackground'])},"
            end
            if @component['disabledFontColor']
              add_line "disabledFontColor: #{get_swiftui_color(@component['disabledFontColor'])},"
            end
            if @component['disabledBackground']
              add_line "disabledBackground: #{get_swiftui_color(@component['disabledBackground'])},"
            end

            # Corner radius and border - all applied inside StateAwareButtonView
            if @component['cornerRadius']
              add_line "cornerRadius: #{@component['cornerRadius'].to_i},"
            end
            if @component['borderWidth']
              add_line "borderWidth: #{@component['borderWidth'].to_i},"
            end
            if @component['borderColor']
              add_line "borderColor: #{get_swiftui_color(@component['borderColor'])},"
            end

            # Paddings（paddings配列 or 個別指定 leftPadding/rightPadding/paddingTop/paddingBottom）
            if @component['paddings']
              padding = @component['paddings']
              if padding.is_a?(Array)
                case padding.length
                when 1
                  add_line "padding: EdgeInsets(top: #{padding[0]}, leading: #{padding[0]}, bottom: #{padding[0]}, trailing: #{padding[0]}),"
                when 2
                  add_line "padding: EdgeInsets(top: #{padding[0]}, leading: #{padding[1]}, bottom: #{padding[0]}, trailing: #{padding[1]}),"
                when 4
                  add_line "padding: EdgeInsets(top: #{padding[0]}, leading: #{padding[1]}, bottom: #{padding[2]}, trailing: #{padding[3]}),"
                end
              else
                add_line "padding: EdgeInsets(top: #{padding}, leading: #{padding}, bottom: #{padding}, trailing: #{padding}),"
              end
            elsif @component['leftPadding'] || @component['rightPadding'] || @component['paddingTop'] || @component['paddingBottom']
              top = @component['paddingTop'] || 0
              left = @component['leftPadding'] || @component['paddingLeft'] || 0
              bottom = @component['paddingBottom'] || 0
              right = @component['rightPadding'] || @component['paddingRight'] || 0
              add_line "padding: EdgeInsets(top: #{top}, leading: #{left}, bottom: #{bottom}, trailing: #{right}),"
            end

            # Enabled state
            if @component['enabled'] != nil
              enabled_value = @component['enabled']
              if enabled_value.is_a?(String) && enabled_value.start_with?('@{') && enabled_value.end_with?('}')
                enabled_expr = SwiftUI::Binding::BindingExpression.swift_value_expr(enabled_value[2..-2])
                add_line "isEnabled: #{enabled_expr},"
              elsif enabled_value == false
                add_line "isEnabled: false,"
              elsif enabled_value == true
                add_line "isEnabled: true,"
              end
            else
              add_line "isEnabled: true,"
            end

            # Handle width/height - pass to StateAwareButtonView so background fills the frame
            if @component['width'] == 'matchParent' || @component['width'] == -1
              add_line "width: -1,"
            elsif @component['width'].is_a?(Numeric) && @component['width'] > 0
              add_line "width: #{@component['width']},"
            elsif @component['weight'] && @component['weight'].to_f > 0
              parent_orientation = @component['parent_orientation']
              if parent_orientation == 'horizontal'
                add_line "width: -1,"
              end
            end

            if @component['height'] == 'matchParent' || @component['height'] == -1
              add_line "height: -1,"
            elsif @component['height'].is_a?(Numeric) && @component['height'] > 0
              add_line "height: #{@component['height']},"
            elsif @component['weight'] && @component['weight'].to_f > 0
              parent_orientation = @component['parent_orientation']
              if parent_orientation == 'vertical'
                add_line "height: -1,"
              end
            end

            # Icon. `image` was declared for Button but no SwiftUI converter
            # read it, so an icon-only button rendered as an empty button.
            # Resolution follows Image#srcName: a bare name is an asset name,
            # a binding resolves through data.
            #
            # The tint is only passed when the layout asked for one — a
            # template rendering mode would flatten a multi-colour asset to a
            # single colour. Same rule as the Compose and web converters.
            #
            # Emitted LAST: Swift requires call-site argument order to match
            # the declaration, and image/imageTint are the final parameters of
            # StateAwareButtonView.init ("argument 'isEnabled' must precede
            # argument 'image'" — caught by the codegen parity host).
            if has_image
              if is_binding?(image)
                add_line "image: data.#{extract_binding_property(image)},"
              else
                add_line "image: \"#{image}\","
              end
              image_tint = @component['tintColor'] || @component['fontColor']
              add_line "imageTint: #{get_swiftui_color(image_tint)}," if image_tint
            end

            # Remove trailing comma from last parameter
            if @generated_code.last&.end_with?(',')
              @generated_code[-1] = @generated_code.last.chomp(',')
            end
          end
          add_line ")"

          # textAlign. StateAwareButtonView has no alignment argument and
          # nothing here read the attribute, so the declared alignment was
          # inert on this platform. `multilineTextAlignment` is an
          # environment modifier, so it reaches the Text inside the button
          # without the library growing a parameter — the same treatment the
          # TextField converter gives the same spelling.
          if @component['textAlign']
            @modifier_bag.append(:component_specific,
                                 ".multilineTextAlignment(#{text_alignment_to_swiftui(@component['textAlign'])})")
          end

          # Apply frame constraints and margins
          # Note: background, cornerRadius, border are all applied inside StateAwareButtonView
          apply_frame_constraints
          apply_frame_size
          apply_margins

          # confirmationDialog / alert (iOS 15+)
          apply_confirmation_dialog_to_bag
          apply_alert_to_bag

          generated_code
        end

        def apply_padding_to_text
          # Apply paddings to the Text inside the button（UIKitに合わせてpaddingsに統一）
          if @component['paddings']
            padding = @component['paddings']
            # Handle array padding values (from style files)
            if padding.is_a?(Array)
              case padding.length
              when 1
                add_modifier_line ".padding(#{padding[0].to_i})"
              when 2
                # Vertical, Horizontal padding
                add_modifier_line ".padding(.horizontal, #{padding[1].to_i})"
                add_modifier_line ".padding(.vertical, #{padding[0].to_i})"
              when 4
                # Top, Right, Bottom, Left
                add_modifier_line ".padding(.top, #{padding[0].to_i})"
                add_modifier_line ".padding(.trailing, #{padding[1].to_i})"
                add_modifier_line ".padding(.bottom, #{padding[2].to_i})"
                add_modifier_line ".padding(.leading, #{padding[3].to_i})"
              end
            else
              add_modifier_line ".padding(#{padding.to_i})"
            end
          elsif @component['paddingTop'] || @component['paddingBottom'] ||
                @component['paddingLeft'] || @component['paddingRight']
            # UIKitに合わせてpaddingTop形式に統一
            top = @component['paddingTop'] || 0
            bottom = @component['paddingBottom'] || 0
            left = @component['paddingLeft'] || 0
            right = @component['paddingRight'] || 0

            add_modifier_line ".padding(EdgeInsets(top: #{top}, leading: #{left}, bottom: #{bottom}, trailing: #{right}))"
          end
        end

        def button_style_to_swiftui(style)
          case style
          when 'plain'
            '.plain'
          when 'bordered'
            '.bordered'
          when 'borderedProminent'
            '.borderedProminent'
          when 'borderless'
            '.borderless'
          else
            '.automatic'
          end
        end
      end
    end
  end
end
