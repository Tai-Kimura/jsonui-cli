# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class TextViewConverter < BaseConverter
        def convert(indent = 2)
          apply_defaults
          class_name = build_class_name
          style_attr = build_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr

          attrs = build_attributes
          on_change = build_on_change
          disabled_attr = build_disabled_attr

          focus_attrs = build_focus_binding_attrs

          jsx = "#{indent_str(indent)}<textarea#{id_attr} className=\"#{class_name}\"#{style_attr}#{attrs}#{on_change}#{focus_attrs}#{disabled_attr}#{testid_attr}#{tag_attr}></textarea>"

          wrap_with_visibility(jsx, indent)
        end

        protected

        def apply_defaults
          # Apply textView defaults if not explicitly set
          text_view_defaults = defaults('textView')
          return if text_view_defaults.empty?

          @json = json.dup
          @attributes['fontColor'] ||= text_view_defaults['fontColor']
          @attributes['padding'] ||= text_view_defaults['padding']
          @attributes['background'] ||= text_view_defaults['background']
          @attributes['cornerRadius'] ||= text_view_defaults['cornerRadius']
        end

        def build_class_name
          classes = [super]

          # Default textarea styles
          classes << 'border'
          classes << 'outline-none'
          classes << 'focus:ring-2 focus:ring-blue-500'
          classes << 'resize-none' unless attributes['resize']

          # Scrollable
          classes << 'overflow-auto' if attributes['scrollEnabled'] != false

          # Flexible height
          classes << 'resize-y' if attributes['flexible']

          # Placeholder color. Through map_color, like every other colour:
          # interpolating the raw value emits `placeholder-#FF0000`, which is
          # not a Tailwind class at all (rjui-offpalette-hex-dead-tailwind-class
          # — the policy existed, this caller predated it).
          if attributes['hintColor'] || attributes['placeholderColor']
            color = attributes['hintColor'] || attributes['placeholderColor']
            classes << TailwindMapper.map_color(color, 'placeholder')
          elsif attributes['hintAttributes'] && attributes['hintAttributes']['fontColor']
            classes << TailwindMapper.map_color(
              attributes['hintAttributes']['fontColor'], 'placeholder'
            )
          end

          # Placeholder typography, through the `placeholder:` variant so it
          # targets ::placeholder rather than the textarea's own text.
          if attributes['hintFontSize']
            classes << "placeholder:text-[#{attributes['hintFontSize'].to_i}px]"
          end
          if attributes['hintFont']
            hint_font = TailwindMapper.map_font(attributes['hintFont'])
            classes << "placeholder:#{hint_font}" if hint_font && !hint_font.empty?
          end
          if attributes['hintLineHeightMultiple']
            classes << "placeholder:leading-[#{attributes['hintLineHeightMultiple']}]"
          end

          # hideOnFocused defaults to true: the hint goes away when the field is
          # focused, not when the first character arrives. That is the declared
          # default and how the iOS and Android runtimes behave, whereas a browser
          # keeps the placeholder visible until there is text — so the class is
          # emitted unless the layout explicitly opts out.
          unless attributes['hideOnFocused'] == false
            classes << 'focus:placeholder-transparent'
          end

          # Text selection
          classes << 'select-none' if attributes['selectable'] == false

          # Disabled state
          if attributes['enabled'] == false || attributes['enabled'].is_a?(String)
            if attributes['disabledBackground']
              classes << "disabled:#{TailwindMapper.map_color(attributes['disabledBackground'], 'bg')}"
            else
              classes << 'disabled:bg-gray-100'
            end
            classes << 'disabled:cursor-not-allowed'
          end

          finalize_classes(classes)
        end

        def build_style_attr
          super

          # Corner radius
          if attributes['cornerRadius']
            @dynamic_styles['borderRadius'] = "'#{attributes['cornerRadius']}px'"
          end

          # lineBreakMode — same truncation mapping as Label (a textarea shows
          # its own scrollbar rather than truncating, so this only matters for
          # the read-only/one-line styling cases, but the declared attribute
          # must not be silently dropped).
          if attributes['lineBreakMode']
            case attributes['lineBreakMode']
            when 'Head'
              @dynamic_styles['textOverflow'] = "'ellipsis'"
              @dynamic_styles['direction'] = "'rtl'"
              @dynamic_styles['textAlign'] = "'left'"
            when 'Middle', 'Tail', 'Clip'
              @dynamic_styles['textOverflow'] = "'ellipsis'"
            end
            @dynamic_styles['overflow'] = "'hidden'"
          end

          # Hint/placeholder color is now handled via Tailwind class in build_class_name

          # Container inset (internal padding). `edgeInset` is the UIKit
          # spelling of the same content inset (the Label converter already
          # reads it) — routing it here took TextView.edgeInset off the
          # coverage gap ledger.
          if attributes['containerInset'] || attributes['edgeInset']
            inset = attributes['containerInset'] || attributes['edgeInset']
            if inset.is_a?(Array)
              case inset.length
              when 1
                @dynamic_styles['padding'] = "'#{inset[0]}px'"
              when 2
                @dynamic_styles['padding'] = "'#{inset[0]}px #{inset[1]}px'"
              when 4
                @dynamic_styles['padding'] = "'#{inset[0]}px #{inset[1]}px #{inset[2]}px #{inset[3]}px'"
              end
            else
              @dynamic_styles['padding'] = "'#{inset}px'"
            end
          end

          # Min/max height for flexible textareas
          if attributes['minHeight']
            @dynamic_styles['minHeight'] = "'#{attributes['minHeight']}px'"
          end

          if attributes['maxHeight']
            @dynamic_styles['maxHeight'] = "'#{attributes['maxHeight']}px'"
          end

          # Border
          if attributes['borderWidth'] && attributes['borderColor']
            @dynamic_styles['borderWidth'] = "'#{attributes['borderWidth']}px'"
            @dynamic_styles['borderColor'] = color_style_expr(attributes['borderColor'])
            @dynamic_styles['borderStyle'] = "'solid'"
          end

          return '' if @dynamic_styles.nil? || @dynamic_styles.empty?

          # Delegate per-entry rendering to BaseConverter so the SPREAD
          # sentinel (Configuration.Font.resolve(...) emission) is handled
          # consistently across every converter.
          style_pairs = @dynamic_styles.map do |key, value|
            format_dynamic_style_pair(key, value)
          end

          " style={{ #{style_pairs.join(', ')} }}"
        end

        def build_attributes
          attrs = []

          # Placeholder (hint)
          placeholder = attributes['hint'] || attributes['placeholder']
          if placeholder
            resolved = convert_binding(placeholder)
            if resolved != placeholder && resolved.include?('{')
              attrs << " placeholder={#{resolved.gsub(/^\{|\}$/, '')}}"
            elsif (string_resolved = convert_string_key(placeholder))
              # strings.json key -> StringManager, matching sjui's hint
              # contract (get_text_with_string_manager). Unregistered keys
              # and plain literals fall through unchanged.
              attrs << " placeholder=#{string_resolved}"
            else
              attrs << " placeholder=\"#{placeholder}\""
            end
          end

          # Name attribute
          attrs << " name=\"#{attributes['name']}\"" if attributes['name']

          # Value handling depends on binding presence
          if attributes['text']
            if has_binding?(attributes['text'])
              # Binding present: use controlled component (value + onChange)
              value = convert_binding(attributes['text'])
              attrs << " value={#{value.gsub(/[{}]/, '')}}"
            else
              # No binding: use uncontrolled component (defaultValue only)
              attrs << " defaultValue=\"#{attributes['text']}\""
            end
          end

          # Rows
          if attributes['lines'] || attributes['rows']
            rows = attributes['lines'] || attributes['rows']
            attrs << " rows={#{rows}}"
          end

          # Max length
          attrs << " maxLength={#{attributes['maxLength']}}" if attributes['maxLength']

          # Read only
          attrs << ' readOnly' if attributes['readOnly'] || attributes['editable'] == false

          # Auto focus
          attrs << ' autoFocus' if attributes['autoFocus'] || attributes['becomeFirstResponder']

          # Soft-keyboard hints — same UIKit-spelling vocabulary as TextField,
          # mapped by the shared base helpers. A textarea has no `type`, so
          # `input` only contributes the mobile keyboard mode here.
          if attributes['input']
            inputmode = map_input_mode(attributes['input'])
            attrs << " inputMode=\"#{inputmode}\"" if inputmode
          end
          if attributes['returnKeyType']
            enter_key_hint = map_return_key(attributes['returnKeyType'])
            attrs << " enterKeyHint=\"#{enter_key_hint}\"" if enter_key_hint
          end

          # Columns — the horizontal counterpart of `rows`.
          attrs << " cols={#{attributes['cols'].to_i}}" if attributes['cols']

          # Native browser validation. `required` is a textarea attribute;
          # `pattern` is NOT — HTML only defines it for <input> — so the same
          # contract is met through the constraint-validation API, which still
          # blocks form submission and still drives :invalid.
          attrs << ' required' if attributes['required'] == true || attributes['required'] == 'true'
          if attributes['pattern']
            escaped = attributes['pattern'].to_s.gsub('\\', '\\\\\\\\').gsub("'", "\\\\'")
            # `currentTarget`, not `target`: React types onInput as a FormEvent,
            # whose `target` is a bare EventTarget — reading `.value` off it is
            # a type error in a strict consumer, and the file is @generated.
            attrs << " onInput={(e) => e.currentTarget.setCustomValidity(" \
                     "new RegExp('^(?:#{escaped})$').test(e.currentTarget.value) ? '' : 'Invalid format')}"
          end

          # Soft keyboard. `input` is the TextField spelling of the same idea and
          # already maps through here; keyboardType is the UIKit one.
          if attributes['keyboardType']
            inputmode = map_keyboard_type(attributes['keyboardType'])
            attrs << " inputMode=\"#{inputmode}\"" if inputmode
          end

          attrs.join
        end

        # UIKeyboardType spellings -> the HTML inputmode vocabulary.
        def map_keyboard_type(value)
          case value.to_s.downcase.sub(/^uikeyboardtype/, '')
          when 'numberpad', 'number', 'numbersandpunctuation' then 'numeric'
          when 'decimalpad', 'decimal' then 'decimal'
          when 'phonepad', 'phone' then 'tel'
          when 'emailaddress', 'email' then 'email'
          when 'url', 'weburl' then 'url'
          when 'websearch', 'search' then 'search'
          when 'default', 'asciicapable', 'text' then 'text'
          end
        end

        def build_on_change
          # If custom handler is defined, use it (passing the event object)
          handler = attributes['onTextChange'] || attributes['onChange']
          if handler
            if has_binding?(handler)
              prop = extract_binding_property(handler)
              # If text binding is present, pass (previousValue, newValue) for (String, String) callbacks
              if attributes['text'] && has_binding?(attributes['text'])
                text_prop = extract_binding_property(attributes['text'])
                return " onChange={(e) => #{prop}?.(#{text_prop}, e.target.value)}"
              else
                return " onChange={(e) => #{prop}?.(e.target.value)}"
              end
            else
              return " onChange={(e) => #{handler}?.(e.target.value)}"
            end
          end

          # Auto-generate onChange from text binding property
          # e.g., text: "@{description}" -> onChange={(e) => data.onDescriptionChange?.(e.target.value)}
          if attributes['text'] && has_binding?(attributes['text'])
            property_name = extract_raw_binding_property(attributes['text'])
            handler_name = "on#{capitalize_first(property_name)}Change"
            return " onChange={(e) => data.#{handler_name}?.(e.target.value)}"
          end

          ''
        end

        def capitalize_first(str)
          return str if str.nil? || str.empty?

          str[0].upcase + str[1..]
        end

        def build_disabled_attr
          enabled = attributes['enabled']
          return '' if enabled.nil?

          if enabled.is_a?(String) && enabled.start_with?('@{') && enabled.end_with?('}')
            " disabled={!#{extract_binding_property(enabled)}}"
          elsif enabled == false
            ' disabled'
          else
            ''
          end
        end
      end
    end
  end
end
