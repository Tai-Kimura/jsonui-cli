# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/binding_expression'
require_relative '../helpers/resource_resolver'
require_relative '../helpers/font_spec_helper'

module KjuiTools
  module Compose
    module Components
      class TextFieldComponent
        # The declared `contentType` vocabulary as Compose keyboard types.
        # `url` is present on both tables: `input: "url"` used to fall through
        # to KeyboardType.Text, which made every non-email/password/number
        # input emit the SAME keyboard and measure as presence-only (plan 49
        # lane C: TextField.input / TextView.input C2).
        CONTENT_TYPE_KEYBOARD = {
          'emailaddress' => 'KeyboardType.Email',
          'email' => 'KeyboardType.Email',
          'password' => 'KeyboardType.Password',
          'newpassword' => 'KeyboardType.Password',
          'telephonenumber' => 'KeyboardType.Phone',
          'phone' => 'KeyboardType.Phone',
          'tel' => 'KeyboardType.Phone',
          'url' => 'KeyboardType.Uri',
          'creditcardnumber' => 'KeyboardType.Number',
          'postalcode' => 'KeyboardType.Number'
        }.freeze

        # `default` is deliberately absent from both tables. It means "the
        # platform's own keyboard", i.e. no opinion — and emitting
        # `KeyboardType.Text` for it made `input: "default"` and
        # `input: "alphabet"` produce identical output, which is what
        # measured as presence-only (plan 49 lane C: TextField.input /
        # TextView.input / TextView.keyboardType C2).
        #
        # `alphabet` maps to Text on purpose: sjui reaches for
        # `.asciiCapable`, and Compose's peer `KeyboardType.Ascii` was
        # deprecated in favour of `Text` — so Text IS the honest answer here,
        # and the discrimination comes from `default` emitting nothing.
        INPUT_KEYBOARD = {
          'alphabet' => 'KeyboardType.Text',
          'allphabet' => 'KeyboardType.Text',
          'asciicapable' => 'KeyboardType.Text',
          'text' => 'KeyboardType.Text',
          'email' => 'KeyboardType.Email',
          'password' => 'KeyboardType.Password',
          'number' => 'KeyboardType.Number',
          'decimal' => 'KeyboardType.Decimal',
          'phone' => 'KeyboardType.Phone',
          'url' => 'KeyboardType.Uri'
        }.freeze

        @counter ||= 0

        # Per-file determinism: compose_builder calls this before each layout
        # so resolved_* local names don't drift with process build history.
        def self.reset_counter!
          @counter = 0
        end

        def self.next_resolved_var
          @counter += 1
          "resolved_textfield#{@counter}"
        end

        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # TextField uses 'text' for value and supports both 'hint' and 'placeholder'
          # For TextField value, we need direct data binding (not string interpolation)
          raw_text = json_data['text'] || ''
          value = if (inner = Helpers::BindingExpression.extract_inner(raw_text))
            # Two-way context: flat path only (a `??` default here is a
            # validator error — binding-two-way-complex); shared parse via
            # BindingExpression.
            "data.#{Helpers::BindingExpression.two_way_path(inner)}"
          else
            Helpers::ResourceResolver.process_text(raw_text, required_imports)
          end
          placeholder_text = json_data['hint'] || json_data['placeholder'] || ''
          placeholder = placeholder_text.empty? ? '""' : Helpers::ResourceResolver.process_text(placeholder_text, required_imports)
          is_secure = json_data['secure'] == true ||
                      json_data['input']&.downcase == 'password' ||
                      json_data['contentType']&.downcase == 'password' ||
                      json_data['contentType']&.downcase == 'newpassword'

          # Detect hidden TextField (fontColor: "transparent" means invisible field, e.g. 2FA auto-fill)
          is_hidden = json_data['fontColor']&.downcase == 'transparent'
          
          # Check if we need to wrap in Box for margins
          has_margins = json_data['margins'] || json_data['topMargin'] || json_data['bottomMargin'] || 
                       json_data['leftMargin'] || json_data['rightMargin']
          
          # Always use CustomTextField
          required_imports&.add(:custom_textfield)
          required_imports&.add(:secure_text_field) if is_secure
          
          # For data-bound TextFields, use a local remember state to avoid
          # BasicTextField resetting on async StateFlow recomposition.
          # The local state provides synchronous updates for typing,
          # while viewModel.updateData propagates changes to the rest of the UI.
          code = ""
          has_data_binding = json_data['text'] && json_data['text'].match(/@\{([^}]+)\}/)
          local_state_var = nil

          # TextFieldState-based API (Compose BOM 2026.03.00+)
          required_imports&.add(:text_field_state)
          required_imports&.add(:launched_effect)
          # id-less TextFields get a counter suffix — a bare shared "field"
          # name produced conflicting `val` declarations when one scope held
          # more than one id-less TextField.
          state_var = if json_data['id']
            "textFieldState_#{json_data['id']}"
          else
            "textFieldState_#{next_resolved_var.sub('resolved_textfield', 'field')}"
          end
          code += indent("val #{state_var} = rememberTextFieldState(initialText = #{value})", depth) + "\n"

          # `maxLength` was read by nobody on Compose — only
          # `lib/xml/helpers/mappers/input_mapper.rb`, and XML mode is frozen
          # (plan 49 lane C: TextField.maxLength; sjui and rjui both honour
          # it). `CustomTextField` belongs to the KotlinJsonUI repo, which this
          # lane must not touch, so the clamp is expressed entirely in
          # generated code against the public TextFieldState API — which is
          # also where the binding write-back below already lives, so the
          # truncation lands BEFORE the value propagates outward.
          if json_data['maxLength']
            max_len = Helpers::BoundValue.int(json_data['maxLength'])
            code += indent("LaunchedEffect(#{state_var}.text) { val limit = #{max_len}; " \
                           "if (limit > 0 && #{state_var}.text.length > limit) " \
                           "#{state_var}.edit { replace(limit, length, \"\") } }", depth) + "\n"
          end

          if has_data_binding
            variable = extract_variable_name(json_data['text'])
            # Sync external → state
            code += indent("LaunchedEffect(#{value}) { if (#{state_var}.text.toString() != #{value}) #{state_var}.edit { replace(0, length, #{value}) } }", depth) + "\n"
            # Sync state → external
            view_id = json_data['id'] || 'textfield'
            if json_data['onTextChange']
              if Helpers::ModifierBuilder.is_binding?(json_data['onTextChange'])
                handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(json_data['onTextChange'], view_id, 'newValue')
                code += indent("LaunchedEffect(#{state_var}.text) { val newValue = #{state_var}.text.toString(); if (newValue != #{value}) { viewModel.updateData(mapOf(\"#{variable}\" to newValue)); #{handler_call} } }", depth) + "\n"
              else
                code += indent("LaunchedEffect(#{state_var}.text) { val newValue = #{state_var}.text.toString(); if (newValue != #{value}) { viewModel.updateData(mapOf(\"#{variable}\" to newValue)); data.#{json_data['onTextChange']}?.invoke() } }", depth) + "\n"
              end
            else
              code += indent("LaunchedEffect(#{state_var}.text) { val newValue = #{state_var}.text.toString(); if (newValue != #{value}) viewModel.updateData(mapOf(\"#{variable}\" to newValue)) }", depth) + "\n"
            end
          elsif json_data['onTextChange']
            view_id = json_data['id'] || 'textfield'
            if Helpers::ModifierBuilder.is_binding?(json_data['onTextChange'])
              handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(json_data['onTextChange'], view_id, 'newValue')
              code += indent("LaunchedEffect(#{state_var}.text) { val newValue = #{state_var}.text.toString(); #{handler_call} }", depth) + "\n"
            else
              code += indent("LaunchedEffect(#{state_var}.text) { data.#{json_data['onTextChange']}?.invoke() }", depth) + "\n"
            end
          end

          # Build FontSpec resolve block before CustomTextField(...) so the
          # textStyle parameter can reference the resolved local. Emits only when
          # at least one font attribute is set.
          tf_font_args = Helpers::FontSpecHelper.build_font_spec_args(json_data, required_imports)
          tf_resolved_var = nil
          if tf_font_args[:has_any]
            tf_resolved_var = next_resolved_var
            code += Helpers::FontSpecHelper.emit_resolve_block(tf_resolved_var, tf_font_args, depth, required_imports) + "\n"
          end

          # Focus chain (fieldId / nextFocusId).
          #
          # Compose's standard `FocusRequester` is per-component. To support
          # spec-driven `nextFocusId` lookups we emit `val focusRequester_<id>
          # = remember { FocusRequester() }` for every field that declares
          # `fieldId`, then reference `focusRequester_<nextFocusId>` from the
          # source field's KeyboardActions.
          #
          # Contract:
          #   - Target field MUST set `fieldId: "<id>"` to be referenceable
          #   - Source field references it via `nextFocusId: "<id>"`
          #   - Both fields MUST share the same composable scope (siblings
          #     under the same parent layout); cross-screen focus chain is
          #     out of scope (matches the previous broken intent).
          #
          # Regression: kjui-keyboardactions-import-missing — the original
          # emit referenced a non-existent `FocusManager.requestFocus(...)`
          # helper. Refactored to use Compose stdlib `FocusRequester` only.
          # `fieldId` is an undeclared legacy override for the requester name;
          # `id` is the declared attribute and is what a nextFocus target is
          # named by, so it is the fallback right below.
          focus_field_id = json_data['fieldId']

          # ViewModel-driven focus binding — sjui parity
          # (kjui-textfield-isfocused-focus-binding-not-generated): every
          # TextField with an `id` gets a FocusRequester plus data.<id>IsFocused
          # wiring, so `data.xIsFocused = true` from a ViewModel focuses the
          # field and opens the keyboard (the invisible code-entry pattern —
          # e.g. a 2FA hidden input — has no tappable surface and relies on
          # this). The Data property is auto-added by DataModelUpdater.
          # The requester is shared with the fieldId/nextFocusId focus chain:
          # `fieldId` keeps naming priority so nextFocusId lookups still work.
          focus_requester_name = focus_field_id || json_data['id']
          focus_prop = json_data['id'] ? "#{snake_to_camel(json_data['id'])}IsFocused" : nil
          if focus_requester_name
            required_imports&.add(:focus_requester)
            required_imports&.add(:remember)
            code += indent("val focusRequester_#{focus_requester_name} = remember { FocusRequester() }", depth) + "\n"
          end
          if focus_prop
            required_imports&.add(:launched_effect)
            required_imports&.add(:software_keyboard_controller)
            code += indent("val keyboardController_#{json_data['id']} = LocalSoftwareKeyboardController.current", depth) + "\n"
            code += indent("LaunchedEffect(data.#{focus_prop}) { if (data.#{focus_prop}) { focusRequester_#{focus_requester_name}.requestFocus(); keyboardController_#{json_data['id']}?.show() } }", depth) + "\n"
          end

          if has_margins
            required_imports&.add(:box)
            code += indent("CustomTextFieldWithMargins(", depth)
          else
            code += indent("CustomTextField(", depth)
          end

          code += "\n" + indent("state = #{state_var},", depth + 1)
          
          # For CustomTextFieldWithMargins, we need to specify modifiers differently
          if has_margins
            # Box modifier with margins
            box_modifiers = []
            box_modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
            box_modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
            if is_hidden
              required_imports&.add(:alpha)
              box_modifiers << ".alpha(0f)"
            else
              box_modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
              box_modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
            end
            box_modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
            box_modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
            if box_modifiers.any?
              code += "\n" + indent("boxModifier = Modifier", depth + 1)
              box_modifiers.each do |mod|
                code += "\n" + indent("    #{mod}", depth + 1)
              end
              code += ","
            end

            # TextField modifier (size, padding goes to contentPadding)
            textfield_modifiers = []
            textfield_modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, nil, required_imports))
            # When the outer Box uses `Modifier.weight(N)` to claim a Row /
            # Column slot, the slot's measured size is bounded only on the
            # *outer* (Box) modifier. The inner BasicTextField inside the
            # Box defaults to wrap-content and does NOT inherit the Box's
            # bounded width/height, so the field renders narrow and leaves
            # blank space inside the weighted slot. Mirror Compose's
            # standard pattern: when weight is requested, the inner
            # textFieldModifier must explicitly `.fillMaxWidth()` (Row
            # parent) or `.fillMaxHeight()` (Column parent) to occupy the
            # outer slot. Skip when build_size already emitted the same
            # modifier via `width: matchParent` / `height: matchParent`.
            # Regression: kjui-textfield-weight-not-fillmaxwidth-inner.
            if json_data['weight'] && json_data['weight'].to_f > 0
              fill_modifier = case parent_type
                              when 'Row' then '.fillMaxWidth()'
                              when 'Column' then '.fillMaxHeight()'
                              end
              if fill_modifier && !textfield_modifiers.include?(fill_modifier)
                textfield_modifiers << fill_modifier
              end
            end
            if focus_prop
              required_imports&.add(:focus_changed)
              textfield_modifiers << ".onFocusChanged { if (it.isFocused != data.#{focus_prop}) viewModel.updateData(mapOf(\"#{focus_prop}\" to it.isFocused)) }"
            end
            textfield_modifiers << ".focusRequester(focusRequester_#{focus_requester_name})" if focus_requester_name
            if textfield_modifiers.any?
              code += "\n" + indent("textFieldModifier = Modifier", depth + 1)
              textfield_modifiers.each do |mod|
                code += "\n" + indent("    #{mod}", depth + 1)
              end
              code += ","
            end
          else
            # Regular modifiers for CustomTextField (size, margins, and weight, padding goes to contentPadding)
            modifiers = []
            modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
            modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
            modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, nil, required_imports))
            modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
            if is_hidden
              required_imports&.add(:alpha)
              modifiers << ".alpha(0f)"
            else
              modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
              modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
            end
            modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
            if focus_prop
              required_imports&.add(:focus_changed)
              modifiers << ".onFocusChanged { if (it.isFocused != data.#{focus_prop}) viewModel.updateData(mapOf(\"#{focus_prop}\" to it.isFocused)) }"
            end
            modifiers << ".focusRequester(focusRequester_#{focus_requester_name})" if focus_requester_name

            if modifiers.any?
              code += "\n" + indent("modifier = Modifier", depth + 1)
              modifiers.each do |mod|
                code += "\n" + indent("    #{mod}", depth + 1)
              end
              code += ","
            end
          end
          
          # Add placeholder/hint with styling
          # Always use Configuration.TextField.defaultPlaceholderColor if hintColor is not specified
          if placeholder && placeholder != '""'
            required_imports&.add(:configuration)
            placeholder_code = "placeholder = { Text("
            placeholder_code += "\n" + indent("text = #{placeholder}", depth + 2)

            # Use hintColor if specified, otherwise use Configuration default.
            # `placeholderColor` is the alias spelling of hintColor (SSoT:
            # "Placeholder color"); reading it here is what took it off the
            # coverage gap ledger.
            hint_color_value = json_data['hintColor'] || json_data['placeholderColor']
            if hint_color_value
              hint_color = Helpers::ResourceResolver.process_color(hint_color_value, required_imports)
              placeholder_code += ",\n" + indent("color = #{hint_color}", depth + 2)
            else
              placeholder_code += ",\n" + indent("color = Configuration.TextField.defaultPlaceholderColor", depth + 2)
            end

            if json_data['hintFontSize']
              placeholder_code += ",\n" + indent("fontSize = #{json_data['hintFontSize']}.sp", depth + 2)
            end

            if json_data['hintFont'] == 'bold'
              placeholder_code += ",\n" + indent("fontWeight = FontWeight.Bold", depth + 2)
            end

            # hintLineHeightMultiple — Compose has no multiplier, so it
            # resolves against the hint's own size (falling back to the
            # field's, then M3 bodyLarge's 16), derived from LocalTextStyle so
            # the M3 placeholder typography survives. Same emit as TextView's
            # build_placeholder; the row was unread on this component
            # (codegen_effect TextField.hintLineHeightMultiple android).
            if (hint_multiple = json_data['hintLineHeightMultiple'])
              required_imports&.add(:local_text_style)
              hint_base = json_data['hintFontSize'] || json_data['fontSize'] || 16
              line_height = (hint_base.to_f * hint_multiple.to_f)
              formatted = line_height == line_height.to_i ? line_height.to_i : line_height
              placeholder_code += ",\n" + indent("style = LocalTextStyle.current.copy(lineHeight = #{formatted}.sp)", depth + 2)
            end

            placeholder_code += "\n" + indent(") }", depth + 1)
            code += "\n" + indent(placeholder_code, depth + 1) + ","
          end
          
          # Secure fields use SecureTextField (handled at component level, not via visualTransformation)
          
          # Add custom TextField parameters
          
          # Shape with corner radius
          if json_data['cornerRadius']
            required_imports&.add(:shape)
            code += "\n" + indent("shape = RoundedCornerShape(#{json_data['cornerRadius']}.dp),", depth + 1)
          end

          # Content padding - internal padding within the text field (not for SecureTextField)
          # Supports: paddings (array or single value), fieldPadding (legacy single value)
          if !is_secure && json_data['paddings']
            required_imports&.add(:padding_values)
            paddings = json_data['paddings']
            if paddings.is_a?(Array)
              case paddings.length
              when 1
                code += "\n" + indent("contentPadding = PaddingValues(#{paddings[0]}.dp),", depth + 1)
              when 2
                # [vertical, horizontal]
                code += "\n" + indent("contentPadding = PaddingValues(horizontal = #{paddings[1]}.dp, vertical = #{paddings[0]}.dp),", depth + 1)
              when 4
                # [top, right, bottom, left]
                code += "\n" + indent("contentPadding = PaddingValues(start = #{paddings[3]}.dp, top = #{paddings[0]}.dp, end = #{paddings[1]}.dp, bottom = #{paddings[2]}.dp),", depth + 1)
              end
            else
              code += "\n" + indent("contentPadding = PaddingValues(#{paddings}.dp),", depth + 1)
            end
          elsif !is_secure && json_data['fieldPadding']
            required_imports&.add(:padding_values)
            code += "\n" + indent("contentPadding = PaddingValues(#{json_data['fieldPadding']}.dp),", depth + 1)
          end

          # Text padding left - start padding for text content.
          # CustomTextField's parameter is contentPadding (PaddingValues) —
          # `textPaddingStart` was never a parameter and did not compile
          # (codegen parity host, TextField/textPaddingLeft, 2026-08-02).
          # fieldPadding above wins when both are declared (one
          # contentPadding argument only).
          if !is_secure && json_data['textPaddingLeft'] && !json_data['fieldPadding']
            required_imports&.add(:padding_values)
            code += "\n" + indent("contentPadding = PaddingValues(start = #{json_data['textPaddingLeft']}.dp),", depth + 1)
          end
          
          # `tintColor` — the caret accent (UIKit vocabulary), forwarded to
          # CustomTextField's cursorColor (KotlinJsonUI >= 2.17.1).
          # `caretAttributes.fontColor` is the object form of the same fact and
          # reads behind it, matching sjui's `tintColor || caretAttributes`.
          caret_attrs = json_data['caretAttributes']
          caret_color_value = json_data['tintColor'] ||
                              (caret_attrs.is_a?(Hash) ? caret_attrs['fontColor'] : nil)
          if caret_color_value
            cursor_color = Helpers::ResourceResolver.process_color(caret_color_value, required_imports)
            code += "\n" + indent("cursorColor = #{cursor_color},", depth + 1)
          end

          # Background colors
          if json_data['background']
            bg_color = Helpers::ResourceResolver.process_color(json_data['background'], required_imports)
            code += "\n" + indent("backgroundColor = #{bg_color},", depth + 1)
          end

          if json_data['highlightBackground']
            highlight_bg_color = Helpers::ResourceResolver.process_color(json_data['highlightBackground'], required_imports)
            code += "\n" + indent("highlightBackgroundColor = #{highlight_bg_color},", depth + 1)
          end

          # Border color for outlined text fields
          if json_data['borderColor']
            border_color = Helpers::ResourceResolver.process_color(json_data['borderColor'], required_imports)
            code += "\n" + indent("borderColor = #{border_color},", depth + 1)
          end

          # Border style handling
          if json_data['borderStyle']
            case json_data['borderStyle'].downcase
            when 'none'
              code += "\n" + indent("isOutlined = false,", depth + 1)
            when 'line', 'bezel', 'roundedrect'
              code += "\n" + indent("isOutlined = true,", depth + 1)
            end
          elsif json_data['borderWidth'] == 0 || json_data['borderWidth'] == '0'
            code += "\n" + indent("isOutlined = false,", depth + 1)
          elsif json_data['outlined'] == true || json_data['borderColor'] || json_data['borderWidth']
            code += "\n" + indent("isOutlined = true,", depth + 1)
          end

          if is_secure
            code += "\n" + indent("isSecure = true,", depth + 1)
          end
          
          
          # Text styling - always add this last before closing.
          # Always include textStyle with at least a default color.
          # Font attrs (fontFamily / font weight / fontSize) flow through
          # Configuration.Font.resolve(FontSpec(...)) so the app's fontProvider sees
          # the full context. fontColor stays inline.
          required_imports&.add(:text_style)
          style_parts = []
          if tf_resolved_var
            style_parts.concat(Helpers::FontSpecHelper.style_arg_fragments(tf_resolved_var, required_imports))
          end

          # Use fontColor if specified; the undeclared default routes through
          # Configuration.TextField (the theming surface the dynamic component
          # already uses) — the old hardcoded #000000 made codegen fields
          # render darker than dynamic ones (parity family F5).
          if json_data['fontColor']
            color_value = Helpers::ResourceResolver.process_color(json_data['fontColor'], required_imports)
            style_parts << "color = #{color_value}" if color_value
          else
            # The import goes WITH the emission. The placeholder branch above
            # registers it too, which is why this was invisible: every
            # TextField fixture that declared a hint got the import from
            # there, and only a field with no hint AND no fontColor reached
            # this line alone — `Unresolved reference 'Configuration'`, and
            # the whole codegen host stopped compiling.
            required_imports&.add(:configuration)
            style_parts << "color = Configuration.TextField.defaultTextColor"
          end

          # Undeclared font size follows the same Configuration default the
          # dynamic component applies (LocalTextStyle's 16sp is not it).
          unless tf_resolved_var
            required_imports&.add(:configuration)
            style_parts << "fontSize = Configuration.TextField.defaultFontSize.sp"
          end

          if json_data['textAlign']
            required_imports&.add(:text_align)
            case json_data['textAlign'].downcase
            when 'center'
              style_parts << "textAlign = TextAlign.Center"
            when 'right'
              style_parts << "textAlign = TextAlign.End"
            when 'left'
              style_parts << "textAlign = TextAlign.Start"
            end
          end
          
          if style_parts.any?
            # Remove trailing comma before adding textStyle
            if code.end_with?(',')
              code = code[0..-2]
            end
            code += ",\n" + indent("textStyle = TextStyle(#{style_parts.join(', ')})", depth + 1)
          end
          
          # Add focus/blur event handlers
          if json_data['onFocus']
            code += ",\n" + indent("onFocus = { data.#{json_data['onFocus']}?.invoke() }", depth + 1)
          end

          if json_data['onBlur']
            code += ",\n" + indent("onBlur = { data.#{json_data['onBlur']}?.invoke() }", depth + 1)
          end

          if json_data['onBeginEditing']
            code += ",\n" + indent("onBeginEditing = { data.#{json_data['onBeginEditing']}?.invoke() }", depth + 1)
          end

          if json_data['onEndEditing']
            code += ",\n" + indent("onEndEditing = { data.#{json_data['onEndEditing']}?.invoke() }", depth + 1)
          end
          
          # Focus management — `fieldId` is already wired above (the
          # `val focusRequester_<id> = remember { FocusRequester() }`
          # declaration + `.focusRequester(...)` modifier). Here we
          # only need to wire KeyboardActions for `nextFocusId` lookup
          # and `onSubmit`.
          # `nextFocus` is the declared attribute (and what the iOS converter
          # reads); `nextFocusId` is the undeclared legacy spelling this file was
          # written against, so a layout that used the declared name got no focus
          # chain at all. Both work, declared name first.
          next_focus_id = json_data['nextFocus'] || json_data['nextFocusId']
          on_submit = json_data['onSubmit']

          # KeyboardActions for focus chain / submit
          if next_focus_id || on_submit
            required_imports&.add(:keyboard_actions)
            actions = []
            if next_focus_id
              # Target field MUST have `fieldId: "<next_focus_id>"` set so
              # `focusRequester_<next_focus_id>` exists in the same
              # composable scope. Spec-side contract; codegen does not
              # validate cross-field reachability.
              actions << "onNext = { focusRequester_#{next_focus_id}.requestFocus() }"
              actions << "onDone = { focusRequester_#{next_focus_id}.requestFocus() }"
            end
            if on_submit
              # `get_event_handler_invocation` is a 3-arity helper
              # (handler, view_id, value_expr). `onSubmit` carries no value
              # to pass to the handler, so `value_expr` is `nil` — which
              # also matches every other no-value call site in this codegen.
              # Regression: kjui-textfield-onsubmit-helper-arity-mismatch.
              submit_call = Helpers::ModifierBuilder.is_binding?(on_submit) ?
                Helpers::ModifierBuilder.get_event_handler_invocation(on_submit, json_data['id'] || 'textfield', nil) :
                "data.#{on_submit}?.invoke()"
              actions << "onDone = { #{submit_call} }" unless next_focus_id
              actions << "onGo = { #{submit_call} }"
              actions << "onSearch = { #{submit_call} }"
              actions << "onSend = { #{submit_call} }"
            end
            code += ",\n" + indent("keyboardActions = KeyboardActions(", depth + 1)
            actions.each_with_index do |action, i|
              separator = i < actions.size - 1 ? ',' : ''
              code += "\n" + indent("#{action}#{separator}", depth + 2)
            end
            code += "\n" + indent(")", depth + 1)
          end

          # Keyboard options (input, returnKeyType, contentType, autocapitalizationType, autocorrectionType)
          keyboard_options = []


          # Input type / contentType - contentType takes priority
          if json_data['contentType']
            required_imports&.add(:keyboard_type)
            # `contentType` is `["string", "binding"]` and the `case` below
            # could never match a `"@{...}"`, so a bound contentType froze to
            # KeyboardType.Text (plan 49 lane C: TextField.contentType).
            keyboard_type = Helpers::BoundValue.enum(
              json_data['contentType'], CONTENT_TYPE_KEYBOARD,
              bound_default: 'KeyboardType.Text', lowercase: true
            )
            keyboard_options << "keyboardType = #{keyboard_type}" if keyboard_type
          elsif json_data['input']
            required_imports&.add(:keyboard_type)
            keyboard_type = Helpers::BoundValue.enum(
              json_data['input'], INPUT_KEYBOARD,
              bound_default: 'KeyboardType.Text', lowercase: true
            )
            keyboard_options << "keyboardType = #{keyboard_type}" if keyboard_type
          elsif json_data['inputType']
            # inputType is the Android-XML spelling, and XML mode is the only
            # place it was ever read (xml/helpers/mappers/input_mapper.rb) — so a
            # layout migrated to Compose lost its keyboard silently. `input` is
            # the canonical attribute and wins; this is the migration fallback,
            # covering the XML mapper's own vocabulary plus the raw
            # `android:inputType` names it passes through untouched.
            required_imports&.add(:keyboard_type)
            keyboard_type = case json_data['inputType'].to_s.downcase
            when 'email', 'textemailaddress'
              'KeyboardType.Email'
            when 'password', 'textpassword'
              'KeyboardType.Password'
            when 'number'
              'KeyboardType.Number'
            when 'numberdecimal'
              'KeyboardType.Decimal'
            when 'phone'
              'KeyboardType.Phone'
            else
              'KeyboardType.Text'
            end
            keyboard_options << "keyboardType = #{keyboard_type}"
          end

          if json_data['returnKeyType']
            required_imports&.add(:ime_action)
            ime_action = case json_data['returnKeyType']
            when 'Done'
              'ImeAction.Done'
            when 'Next'
              'ImeAction.Next'
            when 'Search'
              'ImeAction.Search'
            when 'Send'
              'ImeAction.Send'
            when 'Go'
              'ImeAction.Go'
            else
              'ImeAction.Default'
            end
            keyboard_options << "imeAction = #{ime_action}"
          elsif next_focus_id && !json_data['returnKeyType']
            # Auto-set ImeAction.Next when nextFocusId is specified
            required_imports&.add(:ime_action)
            keyboard_options << "imeAction = ImeAction.Next"
          end

          # Auto-capitalization type
          if json_data['autocapitalizationType']
            required_imports&.add(:keyboard_capitalization)
            capitalization = case json_data['autocapitalizationType'].downcase
            when 'none'
              'KeyboardCapitalization.None'
            when 'words'
              'KeyboardCapitalization.Words'
            when 'sentences'
              'KeyboardCapitalization.Sentences'
            when 'allcharacters', 'characters'
              'KeyboardCapitalization.Characters'
            else
              'KeyboardCapitalization.None'
            end
            keyboard_options << "capitalization = #{capitalization}"
          end

          # Auto-correction type
          if json_data['autocorrectionType']
            # `default` means "leave it to the platform", so it emits nothing.
            # Folding it in with `yes` made those two spellings produce
            # identical output — measured as presence-only (plan 49 lane C:
            # TextField.autocorrectionType C2).
            auto_correct = case json_data['autocorrectionType'].downcase
            when 'no', 'false', 'off'
              'false'
            when 'yes', 'true', 'on'
              'true'
            end
            keyboard_options << "autoCorrectEnabled = #{auto_correct}" if auto_correct
          end

          if keyboard_options.any?
            required_imports&.add(:keyboard_type)
            code += ",\n" + indent("keyboardOptions = KeyboardOptions(#{keyboard_options.join(', ')})", depth + 1)
          end

          # Enabled state (boolean value context: supports `??` default and
          # `@{!flag}` negation via the canonical binding parser).
          # CustomTextField forwards it to the inner TextField, so input is
          # functionally gated — matching the a11y `disabled()` the common
          # modifier path already emits. TextView had this; TextField didn't.
          if json_data.key?('enabled')
            if json_data['enabled'].is_a?(String) && json_data['enabled'].start_with?('@{')
              inner_expr = json_data['enabled'][2..-2]
              code += ",\n" + indent("enabled = #{Helpers::BindingExpression.value_access(inner_expr, negatable: true)}", depth + 1)
            else
              code += ",\n" + indent("enabled = #{json_data['enabled']}", depth + 1)
            end
          end

          # Remove trailing comma and close
          if code.end_with?(',')
            code = code[0..-2]
          end

          code += "\n" + indent(")", depth)

          code
        end
        
        private
        
        def self.extract_variable_name(text)
          if text && text.match(/@\{([^}]+)\}/)
            $1.split('.').last
          else
            'value'
          end
        end

        # snake_case id -> lowerCamel property stem. MUST stay in sync with
        # DataModelUpdater#snake_to_camel — both derive the <id>IsFocused name.
        def self.snake_to_camel(str)
          parts = str.split('_')
          parts[0] + parts[1..].map(&:capitalize).join
        end

        # Strip @{} binding syntax from a value and return the property name
        def self.extract_binding_name(value)
          if value && value.match(/@\{([^}]+)\}/)
            $1
          else
            value
          end
        end
        
        def self.indent(text, level)
          return text if level == 0
          spaces = '    ' * level
          text.split("\n").map { |line| 
            line.empty? ? line : spaces + line 
          }.join("\n")
        end
      end
    end
  end
end