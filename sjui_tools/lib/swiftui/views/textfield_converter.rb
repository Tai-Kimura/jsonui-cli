#!/usr/bin/env ruby

require_relative 'base_view_converter'
require_relative '../helpers/font_helper'
require_relative '../helpers/string_manager_helper'

module SjuiTools
  module SwiftUI
    module Views
      class TextFieldConverter < BaseViewConverter
        include SjuiTools::SwiftUI::Helpers::FontHelper
        include SjuiTools::SwiftUI::Helpers::StringManagerHelper
        def convert
          # Get text field handler for this component
          textfield_handler = @binding_handler.is_a?(SjuiTools::SwiftUI::Binding::TextFieldBindingHandler) ?
                             @binding_handler :
                             SjuiTools::SwiftUI::Binding::TextFieldBindingHandler.new

          # hint (SwiftJsonUIではplaceholderではなくhint)
          hint_raw = @component['hint'] || @component['placeholder'] || ""
          if hint_raw.is_a?(String) && hint_raw.start_with?('@{') && hint_raw.end_with?('}')
            # Binding expression -> resolve to data property (canonical
            # expression parsing: path + optional '?? default')
            hint = SwiftUI::Binding::BindingExpression.swift_value_expr(hint_raw[2..-2])
          else
            # Use localized strings for snake_case hint text
            hint = get_text_with_string_manager("\"#{hint_raw}\"")
          end
          id = @component['id'] || "textField"

          # hintAttributes の処理
          if @component['hintAttributes']
            # SwiftUIではplaceholderのスタイルをカスタマイズすることが難しいため、コメントとして記録
            add_line "// hintAttributes: #{@component['hintAttributes'].to_json}"
          end

          # Get text binding
          text_binding = if @component['text'] && is_binding?(@component['text'])
                          textfield_handler.get_text_binding(@component)
                        else
                          # If no binding, create a constant binding with empty string
                          ".constant(\"\")"
                        end

          # Check if it should be a SecureField
          is_secure = textfield_handler.is_secure_field?(@component)

          # hideOnFocused: EXPLICIT true hides the placeholder the moment the
          # field focuses (UIKit SJUITextField semantics), driven by the
          # auto-generated <id>IsFocused property. Absent keeps the historical
          # SwiftUI behaviour (placeholder until text is typed) so existing
          # screens do not change under them; explicit false is the same.
          if @component['hideOnFocused'] == true && @component['id'] && hint != '""'
            focus_prop = "#{to_camel_case(@component['id'])}IsFocused"
            hint = "data.#{focus_prop} ? \"\" : #{hint}"
          end

          # TextField or SecureField
          if is_secure
            add_line "SecureField(#{hint}, text: #{text_binding})"
          else
            add_line "TextField(#{hint}, text: #{text_binding})"
          end

          # Apply font modifiers using helper
          apply_font_modifiers(@component, self)

          # textAlign
          if @component['textAlign']
            alignment = text_alignment_to_swiftui(@component['textAlign'])
            add_modifier_line ".multilineTextAlignment(#{alignment})"
          end

          # fontColor
          if @component['fontColor']
            color = get_swiftui_color(@component['fontColor'])
            add_modifier_line ".foregroundColor(#{color})"
          end

          # hintColor (placeholder color) - SwiftUIではプレースホルダーの色を直接変更できないためコメントとして記録
          if @component['hintColor'] || @component['placeholderColor']
            hint_color = @component['hintColor'] || @component['placeholderColor']
            add_line "// hintColor/placeholderColor: #{hint_color} - Note: SwiftUI TextField doesn't directly support placeholder color customization"
          end

          # hintFont/hintFontSize/hintLineHeightMultiple - SwiftUI TextFieldではプレースホルダースタイルをカスタマイズできないためコメント
          if @component['hintFont']
            add_line "// hintFont: #{@component['hintFont']} - Note: SwiftUI TextField doesn't support placeholder font customization"
          end
          if @component['hintFontSize']
            add_line "// hintFontSize: #{@component['hintFontSize']} - Note: SwiftUI TextField doesn't support placeholder font size customization"
          end
          if @component['hintLineHeightMultiple']
            add_line "// hintLineHeightMultiple: #{@component['hintLineHeightMultiple']} - Note: SwiftUI TextField doesn't support placeholder line height customization"
          end

          # textFieldStyle
          if @component['borderStyle']
            style = text_field_style(@component['borderStyle'])
            add_modifier_line ".textFieldStyle(#{style})"
          end

          # input type (keyboard type)
          if @component['input']
            keyboard_type = input_to_keyboard_type(@component['input'])
            add_modifier_line ".keyboardType(#{keyboard_type})"
          end

          # contentType (for auto-fill)
          if @component['contentType']
            content_type = map_content_type(@component['contentType'])
            add_modifier_line ".textContentType(#{content_type})"
          end

          # returnKeyType (submit label)
          if @component['returnKeyType']
            submit_label = return_key_to_submit_label(@component['returnKeyType'])
            add_modifier_line ".submitLabel(#{submit_label})"
          end

          # Secure text entry - input == 'password'
          if @component['input'] == 'password'
            # SecureField should be handled above, not here
          end

          # Disabled state. Literal only by design: the bound form is
          # TextFieldBindingHandler's job (it emits `.disabled(!<binding>)`),
          # so adding it here would double the machinery.
          if @component['enabled'] == false
            @modifier_bag.register(:disabled, ".disabled(true)")
          end

          # tintColor / caretAttributes（カーソル色の設定）
          caret_color_value = @component['tintColor'] || (@component['caretAttributes'] && @component['caretAttributes']['fontColor'])
          if caret_color_value
            caret_color = get_swiftui_color(caret_color_value)
            @modifier_bag.register(:tint_color, ".tint(#{caret_color})")
          end

          # textPaddingLeft（テキストの左パディング）
          if @component['textPaddingLeft']
            @modifier_bag.append(:padding, ".padding(.leading, #{@component['textPaddingLeft']})")
          end

          # Text change handler
          # onTextChange (camelCase) -> binding format only (@{functionName})
          if @component['onTextChange'] && is_binding?(@component['onTextChange'])
            # Get the binding variable name from text_binding
            binding_var = text_binding.gsub('$', '').gsub('.constant(', '').gsub(')', '')
            if text_binding.start_with?('$')
              handler_call = get_event_handler_invocation(@component['onTextChange'], id, 'newValue')
              indent_str = "    " * (@indent_level + 1)
              # Guard: only call callback when value actually changed (prevent feedback loop)
              @modifier_bag.append(:on_text_change, ".onChange(of: #{binding_var}) { oldValue, newValue in\n#{indent_str}guard oldValue != newValue else { return }\n#{indent_str}#{handler_call}\n#{indent_str[0...-4]}}")
            else
              add_line "// onTextChange requires data binding"
            end
          end

          # FocusState support - sync with Data property for ViewModel control.
          #
          # Also where the focus handlers live. onFocus / onBeginEditing and
          # onBlur / onEndEditing are the web and UIKit names for the same two
          # moments; Compose wires all four (textfield_component: `onFocus = {
          # ... }`) and the SwiftUI codegen wired none, so a field declared with
          # them silently did nothing. Both names fire, in declaration order, so
          # a layout that sets one or the other or both behaves the same.
          # Written out rather than looped over a name list: the
          # attribute-coverage scan matches a literal `@component['name']`, so a
          # loop reads as "nobody consumes this" and the ledger keeps counting
          # the attribute as unimplemented after it is implemented.
          focus_handlers = [@component['onFocus'], @component['onBeginEditing']].compact
          blur_handlers = [@component['onBlur'], @component['onEndEditing']].compact

          focus_var = nil
          needs_focus_state = @component['id'] || focus_handlers.any? || blur_handlers.any? ||
                              clear_button_needs_focus?
          if needs_focus_state
            field_id = to_camel_case(@component['id'] || 'field')
            focus_var = "#{field_id}IsFocused"

            @state_variables ||= []
            @state_variables << "@FocusState private var #{focus_var}: Bool"

            add_modifier_line ".focused($#{focus_var})"
            if @component['id']
              # Sync: Data -> FocusState
              add_modifier_line ".onChange(of: data.#{focus_var}) { _, newValue in"
              indent do
                add_line "#{focus_var} = newValue"
              end
              add_line "}"
            end
            # Sync: FocusState -> Data, plus the focus/blur handlers. Skipped when
            # the FocusState only exists to feed clearButtonMode — the closure
            # would have no body.
            if @component['id'] || focus_handlers.any? || blur_handlers.any?
              add_modifier_line ".onChange(of: #{focus_var}) { _, newValue in"
              indent do
                add_line "data.#{focus_var} = newValue" if @component['id']
                if focus_handlers.any? || blur_handlers.any?
                  add_line "if newValue {"
                  indent { focus_handlers.each { |h| add_line "data.#{to_camel_case(h.to_s)}?()" } }
                  add_line "} else {"
                  indent { blur_handlers.each { |h| add_line "data.#{to_camel_case(h.to_s)}?()" } }
                  add_line "}"
                end
              end
              add_line "}"
            end
          end

          apply_clear_button_mode(text_binding, focus_var)

          apply_text_input_traits

          # Combined .onSubmit { } block — handles `nextFocus` (focus chain)
          # and/or `onSubmit` (user-defined handler). When both are set, focus
          # chain runs first then onSubmit handler fires, both inside the
          # single SwiftUI .onSubmit closure (SwiftUI does not expose
          # per-return-key slots like Compose's KeyboardActions).
          on_submit_body = []
          if @component['id'] && @component['nextFocus']
            field_id = to_camel_case(@component['id'])
            focus_var = "#{field_id}IsFocused"
            next_field = to_camel_case(@component['nextFocus'])
            next_focus_var = "#{next_field}IsFocused"
            on_submit_body << "data.#{focus_var} = false"
            on_submit_body << "data.#{next_focus_var} = true"
          end
          if @component['onSubmit']
            on_submit = @component['onSubmit']
            view_id = @component['id'] || 'textfield'
            on_submit_body << if is_binding?(on_submit)
                                get_event_handler_invocation(on_submit, view_id)
                              else
                                "data.#{on_submit}?()"
                              end
          end
          unless on_submit_body.empty?
            add_modifier_line ".onSubmit {"
            indent do
              on_submit_body.each { |line| add_line line }
            end
            add_line "}"
          end

          # TextField manages its own padding/background/cornerRadius/border
          # Corresponding to Dynamic mode: TextFieldConverter.swift

          # Apply padding (internal spacing) first
          apply_padding

          # Apply frame constraints and size after padding
          apply_frame_constraints
          apply_frame_size

          # Apply background
          if @component['background']
            color = get_swiftui_color(@component['background'])
            @modifier_bag.register(:background, ".background(#{color})")
          end

          # Apply cornerRadius
          if @component['cornerRadius']
            @modifier_bag.register(:corner_radius, ".cornerRadius(#{@component['cornerRadius'].to_i})")
          end

          # Apply border (after cornerRadius, before margins)
          if @component['borderWidth'] && @component['borderColor']
            color = get_swiftui_color(@component['borderColor'])
            border_code = build_border_overlay(color, (@component['cornerRadius'] || 0).to_i, @component['borderWidth'].to_i)
            @modifier_bag.register(:border, border_code)
          end

          # Apply margins (external spacing)
          apply_margins

          # Apply opacity
          alpha_value = attr_with_alias('opacity', 'alpha')
          if alpha_value
            @modifier_bag.register(:opacity, ".opacity(#{alpha_value})")
          end

          # Apply shadow if needed
          if @component['shadow']
            shadow_code = build_shadow_modifier(@component['shadow'])
            @modifier_bag.register(:shadow, shadow_code) if shadow_code
          end

          # Apply clipping
          if @component['clipToBounds']
            @modifier_bag.register(:clip_to_bounds, ".clipped()")
          end

          # Apply offset
          if @component['offsetX'] || @component['offsetY']
            offset_x = @component['offsetX'] || 0
            offset_y = @component['offsetY'] || 0
            @modifier_bag.register(:offset, ".offset(x: #{offset_x}, y: #{offset_y})")
          end

          # Apply hidden state — visibility:"invisible" shorthand: keep
          # layout space, hide drawing + accessibility (never collapse)
          hidden_value = @component['hidden']
          if hidden_value == true
            @modifier_bag.register(:hidden, ".opacity(0).accessibilityHidden(true)")
          elsif hidden_value.is_a?(String) && hidden_value.start_with?('@{') && hidden_value.end_with?('}')
            hidden_expr = SwiftUI::Binding::BindingExpression.swift_bool_expr(hidden_value[2..-2])
            @modifier_bag.register(:hidden, ".opacity(#{hidden_expr} ? 0 : 1).accessibilityHidden(#{hidden_expr})")
          end

          # Apply binding-specific modifiers
          apply_binding_modifiers

          generated_code
        end

        private

        def text_field_style(style)
          case style
          when 'RoundedRect', 'roundedRect'
            '.roundedBorder'
          when 'none'
            '.plain'
          else
            '.automatic'
          end
        end

        def input_to_keyboard_type(input)
          case input
          when 'email'
            '.emailAddress'
          when 'password'
            '.default'  # SwiftUIではセキュア入力は別途設定
          when 'number'
            '.numberPad'
          when 'decimal'
            '.decimalPad'
          when 'URL'
            '.URL'
          when 'twitter'
            '.twitter'
          when 'webSearch'
            '.webSearch'
          when 'namePhonePad'
            '.namePhonePad'
          else
            '.default'
          end
        end

        # UITextContentType mapping — vocabulary kept in step with rjui's
        # map_content_type (autocomplete) and kjui's keyboard handling.
        # Unknown values warn instead of silently degrading to .none
        # (sjui-textfield-contenttype-newpassword-not-mapped).
        def map_content_type(type)
          case type.to_s.downcase
          when 'username'
            '.username'
          when 'password'
            '.password'
          when 'newpassword'
            '.newPassword'
          when 'onetimecode'
            '.oneTimeCode'
          when 'email', 'emailaddress'
            '.emailAddress'
          when 'name'
            '.name'
          when 'givenname'
            '.givenName'
          when 'familyname'
            '.familyName'
          when 'tel', 'telephonenumber'
            '.telephoneNumber'
          when 'streetaddress'
            '.streetAddressLine1'
          when 'postalcode'
            '.postalCode'
          when 'country'
            '.countryName'
          when 'creditcardnumber'
            '.creditCardNumber'
          when 'url'
            '.URL'
          else
            puts "Warning: unknown contentType '#{type}' — emitting .textContentType(.none); add a mapping if this is a canonical value"
            '.none'
          end
        end

        def return_key_to_submit_label(return_key)
          case return_key
          when 'Done'
            '.done'
          when 'Go'
            '.go'
          when 'Next'
            '.next'
          when 'Return'
            '.return'
          when 'Search'
            '.search'
          when 'Send'
            '.send'
          when 'Continue'
            '.continue'
          when 'Join'
            '.join'
          when 'Route'
            '.route'
          else
            '.done'
          end
        end

        def text_alignment_to_swiftui(alignment)
          case alignment.downcase
          when 'left', 'leading' then '.leading'
          when 'right', 'trailing' then '.trailing'
          when 'center' then '.center'
          else '.leading'
          end
        end

        def add_state_variable(name, type, default_value)
          @state_variables ||= []
          @state_variables << "@State private var #{name}: #{type} = #{default_value}"
        end
        private

        # clearButtonMode — UIKit's `UITextField.ViewMode`. SwiftUI has no clear
        # button, so the library supplies the overlay
        # (TextFieldClearButton.swift); this decides whether it applies and
        # where the editing flag comes from.
        CLEAR_BUTTON_MODES = {
          'never' => '.never',
          'whileediting' => '.whileEditing',
          'unlessediting' => '.unlessEditing',
          'always' => '.always'
        }.freeze

        def clear_button_mode
          raw = @component['clearButtonMode']
          return nil unless raw.is_a?(String)

          CLEAR_BUTTON_MODES[raw.gsub('_', '').downcase]
        end

        # `whileEditing` / `unlessEditing` need the field's focus state, so they
        # force a @FocusState even on a field that would not otherwise have one.
        def clear_button_needs_focus?
          %w[.whileEditing .unlessEditing].include?(clear_button_mode)
        end

        def apply_clear_button_mode(text_binding, focus_var)
          mode = clear_button_mode
          return if mode.nil? || mode == '.never'

          args = ["mode: #{mode}", "text: #{text_binding}"]
          args << "isEditing: #{focus_var}" if focus_var && clear_button_needs_focus?
          @modifier_bag.append(:component_specific, ".textFieldClearButton(#{args.join(', ')})")
        end

        # autocapitalizationType / autocorrectionType / maxLength / fieldPadding.
        #
        # All four are declared, all four are honoured by Compose or UIKit, and
        # none were read here. The naming is UIKit's, but the concepts exist on
        # every platform — `.textInputAutocapitalization` and
        # `.autocorrectionDisabled` are the SwiftUI spellings.
        def apply_text_input_traits
          if (cap = @component['autocapitalizationType'])
            resolved = case cap.to_s.downcase
                       when 'none' then '.never'
                       when 'words' then '.words'
                       when 'sentences' then '.sentences'
                       when 'allcharacters', 'characters' then '.characters'
                       end
            @modifier_bag.append(
              :component_specific, ".textInputAutocapitalization(#{resolved})"
            ) if resolved
          end

          if (corr = @component['autocorrectionType'])
            disabled = %w[no none false off].include?(corr.to_s.downcase)
            @modifier_bag.append(
              :component_specific, ".autocorrectionDisabled(#{disabled})"
            )
          end

          if (padding = @component['fieldPadding'])
            @modifier_bag.append(:padding, ".padding(#{padding})")
          end

          apply_max_length
        end

        # maxLength — SwiftUI's TextField has no length limit, so it is enforced
        # by truncating on change. Compose passes it to the value filter and web
        # sets the `maxLength` attribute; here it needs a binding to write back
        # to, and without one there is nothing to truncate.
        def apply_max_length
          max_length = @component['maxLength']
          return if max_length.nil?

          raw = @component['text'] || @component['value'] || @component['bind']
          return unless raw.is_a?(String) && is_binding?(raw)

          prop = extract_binding_property(raw)
          indent_str = "    " * (@indent_level + 1)
          @modifier_bag.append(
            :on_text_change,
            ".onChange(of: data.#{prop}) { _, newValue in\n" \
            "#{indent_str}if newValue.count > #{max_length} {\n" \
            "#{indent_str}    data.#{prop} = String(newValue.prefix(#{max_length}))\n" \
            "#{indent_str}}\n" \
            "#{indent_str[0...-4]}}"
          )
        end
      end
    end
  end
end
