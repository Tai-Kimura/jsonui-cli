# frozen_string_literal: true

require_relative 'text_component'
require_relative '../helpers/bound_value'
require_relative 'textfield_component'
require_relative '../helpers/modifier_builder'
require_relative '../helpers/binding_expression'
require_relative '../helpers/resource_resolver'
require_relative '../helpers/font_spec_helper'

module KjuiTools
  module Compose
    module Components
      class TextViewComponent
        @counter ||= 0

        # Per-file determinism: compose_builder calls this before each layout
        # so resolved_* local names don't drift with process build history.
        def self.reset_counter!
          @counter = 0
        end

        # One key of the `hintAttributes` object, if it is there.
        def self.hint_attr(json_data, key)
          attrs = json_data['hintAttributes']
          attrs.is_a?(Hash) ? attrs[key] : nil
        end

        def self.build_placeholder(json_data, placeholder, depth, required_imports)
          # The flat fallbacks are written out rather than looked up by a passed
          # key name: the coverage scan matches literal single-quoted attribute
          # reads, so an indirected one reads as "nobody consumes this" — which
          # is exactly what happened to hintLineHeightMultiple when this method
          # was first refactored.
          color = hint_attr(json_data, 'fontColor') || json_data['hintColor']
          size = hint_attr(json_data, 'fontSize') || json_data['hintFontSize']
          font = hint_attr(json_data, 'font') || json_data['hintFont']
          multiple = hint_attr(json_data, 'lineHeightMultiple') || json_data['hintLineHeightMultiple']

          args = []
          args << "text = #{placeholder}"
          if color
            args << "color = #{Helpers::ResourceResolver.process_color(color, required_imports)}"
          end
          args << "fontSize = #{size}.sp" if size
          if (weight = font_weight_for(font))
            required_imports&.add(:font_weight)
            args << "fontWeight = #{weight}"
          end
          if multiple
            # Compose has no multiplier, so it resolves against the hint's own
            # size (falling back to the field's, then M3 bodyLarge's 16).
            # The style derives from LocalTextStyle — a bare TextStyle()
            # discarded the M3 placeholder typography (the theme-destruction
            # class; the dynamic component mirrors this exactly).
            required_imports&.add(:local_text_style)
            base_size = size || json_data['fontSize'] || 16
            args << "style = LocalTextStyle.current.copy(lineHeight = #{format_sp(base_size.to_f * multiple.to_f)}.sp)"
          end

          return "\n" + indent("placeholder = { Text(#{placeholder}) },", depth + 1) if args.length == 1

          code = "\n" + indent("placeholder = {", depth + 1)
          code += "\n" + indent("Text(", depth + 2)
          code += args.map { |a| "\n" + indent("#{a},", depth + 3) }.join
          code = code.chomp(',')
          code += "\n" + indent(")", depth + 2)
          code += "\n" + indent("},", depth + 1)
          code
        end

        # 19.599999999999998.sp is float noise, not a measurement.
        def self.format_sp(value)
          rounded = value.round(2)
          rounded == rounded.to_i ? rounded.to_i.to_s : rounded.to_s
        end

        # `font` on a hint carries a weight name, the same way IconLabel's does.
        WEIGHT_NAMES = {
          'thin' => 'FontWeight.Thin', 'extralight' => 'FontWeight.ExtraLight',
          'light' => 'FontWeight.Light', 'normal' => 'FontWeight.Normal',
          'regular' => 'FontWeight.Normal', 'medium' => 'FontWeight.Medium',
          'semibold' => 'FontWeight.SemiBold', 'bold' => 'FontWeight.Bold',
          'extrabold' => 'FontWeight.ExtraBold', 'heavy' => 'FontWeight.ExtraBold',
          'black' => 'FontWeight.Black'
        }.freeze

        def self.font_weight_for(font)
          font.is_a?(String) ? WEIGHT_NAMES[font.downcase] : nil
        end

        def self.next_resolved_var
          @counter += 1
          "resolved_textview#{@counter}"
        end

        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # TextView is multi-line text input (like TextArea)
          # Uses 'text' for value and supports both 'hint' and 'placeholder' (hint is primary)
          value = process_data_binding(json_data['text'] || '')
          placeholder_text = json_data['hint'] || json_data['placeholder'] || ''
          placeholder = placeholder_text.empty? ? nil : Helpers::ResourceResolver.process_text(placeholder_text, required_imports)

          # Check if we need to wrap in Box for margins
          has_margins = json_data['margins'] || json_data['topMargin'] || json_data['bottomMargin'] ||
                       json_data['leftMargin'] || json_data['rightMargin']

          # Always use CustomTextField
          required_imports&.add(:custom_textfield)

          # For data-bound TextViews, use a local remember state to avoid
          # BasicTextField resetting on async StateFlow recomposition.
          code = ""
          has_data_binding = json_data['text'] && json_data['text'].match(/@\{([^}]+)\}/)
          local_state_var = nil

          # TextFieldState-based API (Compose BOM 2026.03.00+)
          required_imports&.add(:text_field_state)
          required_imports&.add(:launched_effect)
          state_var = "textFieldState_#{json_data['id'] || 'textview'}"
          code += indent("val #{state_var} = rememberTextFieldState(initialText = #{value})", depth) + "\n"

          if has_data_binding
            variable = extract_variable_name(json_data['text'])
            view_id = json_data['id'] || 'textview'
            # Sync external → state
            code += indent("LaunchedEffect(#{value}) { if (#{state_var}.text.toString() != #{value}) #{state_var}.edit { replace(0, length, #{value}) } }", depth) + "\n"
            # Sync state → external
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
            view_id = json_data['id'] || 'textview'
            if Helpers::ModifierBuilder.is_binding?(json_data['onTextChange'])
              handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(json_data['onTextChange'], view_id, 'newValue')
              code += indent("LaunchedEffect(#{state_var}.text) { val newValue = #{state_var}.text.toString(); #{handler_call} }", depth) + "\n"
            else
              code += indent("LaunchedEffect(#{state_var}.text) { data.#{json_data['onTextChange']}?.invoke() }", depth) + "\n"
            end
          end

          # Build FontSpec resolve block ahead of CustomTextField(...) so the
          # textStyle parameter can reference the resolved local. Emits only when
          # at least one font attribute is set.
          tv_font_args = Helpers::FontSpecHelper.build_font_spec_args(json_data, required_imports)
          tv_resolved_var = nil
          if tv_font_args[:has_any]
            tv_resolved_var = next_resolved_var
            code += Helpers::FontSpecHelper.emit_resolve_block(tv_resolved_var, tv_font_args, depth, required_imports) + "\n"
          end

          # ViewModel-driven focus binding — same wiring as TextFieldComponent
          # (kjui-textfield-isfocused-focus-binding-not-generated, extended to
          # TextView): every TextView with an `id` gets a FocusRequester plus
          # data.<id>IsFocused wiring. The Data property is auto-added by
          # DataModelUpdater. (TextView has no fieldId focus chain.)
          focus_prop = json_data['id'] ? "#{snake_to_camel(json_data['id'])}IsFocused" : nil
          if focus_prop
            required_imports&.add(:focus_requester)
            required_imports&.add(:remember)
            required_imports&.add(:launched_effect)
            required_imports&.add(:software_keyboard_controller)
            code += indent("val focusRequester_#{json_data['id']} = remember { FocusRequester() }", depth) + "\n"
            code += indent("val keyboardController_#{json_data['id']} = LocalSoftwareKeyboardController.current", depth) + "\n"
            code += indent("LaunchedEffect(data.#{focus_prop}) { if (data.#{focus_prop}) { focusRequester_#{json_data['id']}.requestFocus(); keyboardController_#{json_data['id']}?.show() } }", depth) + "\n"
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
            box_modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
            box_modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
            if box_modifiers.any?
              code += "\n" + indent("boxModifier = Modifier", depth + 1)
              box_modifiers.each do |mod|
                code += "\n" + indent("    #{mod}", depth + 1)
              end
              code += ","
            end

            # TextField modifier
            textfield_modifiers = []
            # Size - default to fillMaxWidth for text areas.
            # When flexible, the height is governed by the heightIn(min)
            # emitted below — strip the height keys so build_size does not
            # also emit a fixed .height() that would pin the constraints
            # and neutralize the flexible bound.
            size_source = json_data['flexible'] ? json_data.reject { |k, _| %w[height minHeight maxHeight].include?(k) } : json_data
            if json_data['width'] == 'matchParent' || !json_data['width']
              textfield_modifiers << ".fillMaxWidth()"
            else
              textfield_modifiers.concat(Helpers::ModifierBuilder.build_size(size_source, parent_type, required_imports))
            end

            # Height for multi-line
            if json_data['flexible']
              # flexible: height adjusts to content within min/max bounds
              min_h = json_data['minHeight'] || json_data['height'] || 24
              if json_data['maxHeight']
                textfield_modifiers << ".heightIn(min = #{min_h}.dp, max = #{json_data['maxHeight']}.dp)"
              else
                textfield_modifiers << ".heightIn(min = #{min_h}.dp)"
              end
            elsif json_data['height']
              if json_data['height'] == 'matchParent'
                textfield_modifiers << ".fillMaxHeight()"
              elsif json_data['height'] == 'wrapContent'
                textfield_modifiers << ".wrapContentHeight()"
              else
                textfield_modifiers << ".height(#{json_data['height']}.dp)"
              end
            else
              # Default height for text area
              textfield_modifiers << ".height(120.dp)"
            end

            textfield_modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
            textfield_modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
            textfield_modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
            textfield_modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
            if focus_prop
              required_imports&.add(:focus_changed)
              textfield_modifiers << ".onFocusChanged { if (it.isFocused != data.#{focus_prop}) viewModel.updateData(mapOf(\"#{focus_prop}\" to it.isFocused)) }"
              textfield_modifiers << ".focusRequester(focusRequester_#{json_data['id']})"
            end

            if textfield_modifiers.any?
              code += "\n" + indent("textFieldModifier = Modifier", depth + 1)
              textfield_modifiers.each do |mod|
                code += "\n" + indent("    #{mod}", depth + 1)
              end
              code += ","
            end
          else
            # Regular modifiers for CustomTextField
            modifiers = []
            modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))

            # Size - default to fillMaxWidth for text areas (same
            # flexible-height stripping as the margins branch above).
            size_source = json_data['flexible'] ? json_data.reject { |k, _| %w[height minHeight maxHeight].include?(k) } : json_data
            if json_data['width'] == 'matchParent' || !json_data['width']
              modifiers << ".fillMaxWidth()"
            else
              modifiers.concat(Helpers::ModifierBuilder.build_size(size_source, parent_type, required_imports))
            end

            # Height for multi-line
            if json_data['flexible']
              min_h = json_data['minHeight'] || json_data['height'] || 24
              if json_data['maxHeight']
                modifiers << ".heightIn(min = #{min_h}.dp, max = #{json_data['maxHeight']}.dp)"
              else
                modifiers << ".heightIn(min = #{min_h}.dp)"
              end
            elsif json_data['height']
              if json_data['height'] == 'matchParent'
                modifiers << ".fillMaxHeight()"
              elsif json_data['height'] == 'wrapContent'
                modifiers << ".wrapContentHeight()"
              else
                modifiers << ".height(#{json_data['height']}.dp)"
              end
            else
              # Default height for text area
              modifiers << ".height(120.dp)"
            end

            modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
            modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
            modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
            modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
            modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
            modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
            if focus_prop
              required_imports&.add(:focus_changed)
              modifiers << ".onFocusChanged { if (it.isFocused != data.#{focus_prop}) viewModel.updateData(mapOf(\"#{focus_prop}\" to it.isFocused)) }"
              modifiers << ".focusRequester(focusRequester_#{json_data['id']})"
            end

            if modifiers.any?
              code += "\n" + indent("modifier = Modifier", depth + 1)
              modifiers.each do |mod|
                code += "\n" + indent("    #{mod}", depth + 1)
              end
              code += ","
            end
          end

          # Placeholder, styled from `hintAttributes` (the object form) or the
          # flat `hint*` keys. The object wins per key, which is the precedence
          # the SwiftUI converter uses; only lineHeight was honoured here before,
          # so a hint colour or size was silently dropped.
          if placeholder
            code += build_placeholder(json_data, placeholder, depth, required_imports)
          end

          # Container inset - internal padding.
          #
          # `edgeInset` is the UIKit spelling of the same content inset and the
          # Compose TextView path read only `containerInset`, so the alias
          # reached nothing (plan 49 lane C; E retracted the "Compose Text has
          # no edgeInset" deprecation on 2026-08-05 — Label already maps it to
          # `.padding()` in both codegen and the dynamic renderer, so it was
          # unimplemented here, not impossible). sjui reads the same pair
          # (`textview_converter.rb:166`). Array shapes of 1/2/4 are all
          # accepted, matching the declaration.
          inset = json_data['containerInset'] || json_data['edgeInset']
          if inset
            if inset.is_a?(Array) && inset.length == 4
              code += "\n" + indent("contentPadding = PaddingValues(top = #{Helpers::BoundValue.dp(inset[0])}, end = #{Helpers::BoundValue.dp(inset[1])}, bottom = #{Helpers::BoundValue.dp(inset[2])}, start = #{Helpers::BoundValue.dp(inset[3])}),", depth + 1)
            elsif inset.is_a?(Array) && inset.length == 2
              code += "\n" + indent("contentPadding = PaddingValues(vertical = #{Helpers::BoundValue.dp(inset[0])}, horizontal = #{Helpers::BoundValue.dp(inset[1])}),", depth + 1)
            elsif inset.is_a?(Array) && inset.length == 1
              code += "\n" + indent("contentPadding = PaddingValues(#{Helpers::BoundValue.dp(inset[0])}),", depth + 1)
            elsif inset.is_a?(Numeric)
              code += "\n" + indent("contentPadding = PaddingValues(#{Helpers::BoundValue.dp(inset)}),", depth + 1)
            end
          end

          # Shape with corner radius
          if json_data['cornerRadius']
            required_imports&.add(:shape)
            code += "\n" + indent("shape = RoundedCornerShape(#{json_data['cornerRadius']}.dp),", depth + 1)
          end

          # Background colors
          if json_data['background']
            bg_color = Helpers::ResourceResolver.process_color(json_data['background'], required_imports)
            code += "\n" + indent("backgroundColor = #{bg_color},", depth + 1)
          end

          if json_data['highlightBackground']
            highlight_color = Helpers::ResourceResolver.process_color(json_data['highlightBackground'], required_imports)
            code += "\n" + indent("highlightBackgroundColor = #{highlight_color},", depth + 1)
          end

          # Border color for outlined text fields
          if json_data['borderColor']
            border_color = Helpers::ResourceResolver.process_color(json_data['borderColor'], required_imports)
            code += "\n" + indent("borderColor = #{border_color},", depth + 1)
          end

          # Set isOutlined flag (TextView usually wants outlined style)
          code += "\n" + indent("isOutlined = true,", depth + 1)

          # Max lines for TextView
          if json_data['maxLines']
            code += "\n" + indent("maxLines = #{json_data['maxLines']},", depth + 1)
          else
            # Default to multiple lines
            code += "\n" + indent("maxLines = Int.MAX_VALUE,", depth + 1)
          end

          # Single line false for multi-line
          code += "\n" + indent("singleLine = false,", depth + 1)

          # Line break mode (overflow handling)
          if json_data['lineBreakMode']
            # Note: For multi-line TextField, overflow is less relevant
            # but we include it for completeness
            case json_data['lineBreakMode'].to_s.downcase
            when 'clip'
              code += "\n" + indent("// lineBreakMode: clip", depth + 1)
            when 'tail', 'truncatetail'
              code += "\n" + indent("// lineBreakMode: truncate tail", depth + 1)
            when 'head', 'truncatehead'
              code += "\n" + indent("// lineBreakMode: truncate head", depth + 1)
            when 'middle', 'truncatemiddle'
              code += "\n" + indent("// lineBreakMode: truncate middle", depth + 1)
            when 'wordwrap', 'word'
              code += "\n" + indent("// lineBreakMode: word wrap (default)", depth + 1)
            when 'charwrap', 'char'
              code += "\n" + indent("// lineBreakMode: character wrap", depth + 1)
            end
          end

          # Text styling — font attrs flow through Configuration.Font.resolve(FontSpec(...)).
          # fontColor stays inline as it's not part of the FontSpec contract.
          # `textAlign` is declared on TextView and read by nobody on Compose
          # (plan 49 lane C: TextView.textAlign). It belongs in the same
          # TextStyle the font attrs already build, and reuses Label's
          # vocabulary rather than growing a fourth copy of it.
          tv_align = json_data['textAlign'] &&
                     TextComponent.compose_text_align(json_data['textAlign'])
          if tv_resolved_var || json_data['fontColor'] || tv_align
            required_imports&.add(:text_style)
            style_parts = []
            if tv_resolved_var
              style_parts.concat(Helpers::FontSpecHelper.style_arg_fragments(tv_resolved_var, required_imports))
            end
            if json_data['fontColor']
              font_color = Helpers::ResourceResolver.process_color(json_data['fontColor'], required_imports)
              style_parts << "color = #{font_color}"
            end
            if tv_align
              required_imports&.add(:text_align)
              style_parts << "textAlign = #{tv_align}"
            end
            if style_parts.any?
              code += "\n" + indent("textStyle = TextStyle(#{style_parts.join(', ')}),", depth + 1)
            end
          end

          # Keyboard options
          keyboard_options = []

          # keyboardType
          if json_data['keyboardType'] || json_data['input']
            required_imports&.add(:keyboard_type)
            input_type = json_data['keyboardType'] || json_data['input']
            keyboard_type = Helpers::BoundValue.enum(
              input_type, TextFieldComponent::INPUT_KEYBOARD,
              bound_default: 'KeyboardType.Text', lowercase: true
            )
            keyboard_options << "keyboardType = #{keyboard_type}" if keyboard_type
          end

          if json_data['returnKeyType']
            required_imports&.add(:ime_action)
            ime_action = case json_data['returnKeyType']
            when 'Done'
              'ImeAction.Done'
            when 'Next'
              'ImeAction.Next'
            when 'Default'
              'ImeAction.Default'
            else
              'ImeAction.Default'
            end
            keyboard_options << "imeAction = #{ime_action}"
          end

          # From here down, argument chunks carry their own trailing comma and
          # comment chunks carry none — the earlier args (isOutlined, maxLines,
          # singleLine, textStyle) already end with "," so a leading ",\n" here
          # doubled the comma (`singleLine = false,,`) whenever textStyle was
          # absent: broken Kotlin. Comments are transparent between args as
          # long as every arg line supplies its own separator.
          if keyboard_options.any?
            required_imports&.add(:keyboard_type)
            code += "\n" + indent("keyboardOptions = KeyboardOptions(#{keyboard_options.join(', ')}),", depth + 1)
          end

          # scrollEnabled - controls vertical scroll within TextView
          if json_data.key?('scrollEnabled')
            # In Compose, scrolling is controlled via verticalScroll modifier
            # For TextField, we just note it - actual implementation may need custom handling
            if json_data['scrollEnabled'] == false
              code += "\n" + indent("// scrollEnabled = false - scrolling disabled", depth + 1)
            end
          end

          # hideOnFocused - hide placeholder when focused
          # Note: Compose TextField hides placeholder by default when there's text
          # This is primarily for when you want different behavior
          if json_data.key?('hideOnFocused')
            code += "\n" + indent("// hideOnFocused = #{json_data['hideOnFocused']}", depth + 1)
          end

          # Enabled state (boolean value context: supports `??` default and
          # `@{!flag}` negation via the canonical binding parser).
          #
          # `editable` rides the same argument. It was declared on TextView and
          # read by nobody on Compose — only `lib/xml`, which is frozen (plan
          # 49 lane C: TextView.editable). Compose's own `readOnly` would be
          # the closer word, but `CustomTextField` (KotlinJsonUI, another
          # lane's file) does not expose it, and sjui already settled the
          # semantic by mapping `editable: false` onto `.disabled`. So the two
          # flags AND together into the one argument the library does expose.
          if json_data.key?('enabled') || json_data.key?('editable')
            enabled_state = json_data.key?('enabled') ? Helpers::BoundValue.bool(json_data['enabled']) : :on
            editable_state = json_data.key?('editable') ? Helpers::BoundValue.bool(json_data['editable']) : :on
            combined = Helpers::BoundValue.all_of(enabled_state, editable_state)
            expr = case combined
                   when :on then 'true'
                   when :off then 'false'
                   else combined
                   end
            code += "\n" + indent("enabled = #{expr},", depth + 1)
          end

          # Remove trailing comma and close
          if code.end_with?(',')
            code = code[0..-2]
          end

          code += "\n" + indent(")", depth)
          code
        end

        private

        def self.process_data_binding(text)
          return quote(text) unless text.is_a?(String)

          if (inner = Helpers::BindingExpression.extract_inner(text))
            # Two-way context: flat path only (a `??` default here is a
            # validator error — binding-two-way-complex); shared parse via
            # BindingExpression.
            "data.#{Helpers::BindingExpression.two_way_path(inner)}"
          else
            quote(text)
          end
        end

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

        def self.quote(text)
          # Escape special characters properly
          escaped = text.gsub('\\', '\\\\\\\\')  # Escape backslashes first
                       .gsub('"', '\\"')           # Escape quotes
                       .gsub("\n", '\\n')           # Escape newlines
                       .gsub("\r", '\\r')           # Escape carriage returns
                       .gsub("\t", '\\t')           # Escape tabs
          "\"#{escaped}\""
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
