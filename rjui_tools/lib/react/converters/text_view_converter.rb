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

        # The declared `resize` enum is the CSS `resize` vocabulary, one
        # Tailwind utility each.
        #
        # A value outside the enum keeps the historical presence-only reading:
        # any truthy value meant "resizable", which emitted no class at all
        # and left the textarea on the browser default — `resize: both`, i.e.
        # `resize`. Absent or false still means `resize-none`.
        RESIZE_UTILITIES = {
          'none' => 'resize-none',
          'both' => 'resize',
          'horizontal' => 'resize-x',
          'vertical' => 'resize-y'
        }.freeze

        def build_class_name
          classes = [super]

          # Default textarea styles
          classes << 'border'
          classes << 'outline-none'
          classes << 'focus:ring-2 focus:ring-blue-500'
          # `resize` is declared `["none","both","horizontal","vertical"]` —
          # the CSS `resize` vocabulary exactly. Only the PRESENCE of the key
          # was read (`unless attributes['resize']`), so all four values
          # produced the same textarea and the three non-default ones were
          # unreachable. The enum maps one-to-one onto the Tailwind utility.
          resize = attributes['resize']
          if !resize
            classes << 'resize-none'
          elsif (resize_expr = bound_value_expr(resize))
            dynamic_styles['resize'] = resize_expr
          else
            classes << RESIZE_UTILITIES.fetch(resize.to_s.downcase, 'resize')
          end

          # Scrollable
          classes << 'overflow-auto' if attributes['scrollEnabled'] != false

          # Flexible height
          classes << 'resize-y' if attributes['flexible']

          # Placeholder color. Through map_color, like every other colour:
          # interpolating the raw value emits `placeholder-#FF0000`, which is
          # not a Tailwind class at all (rjui-offpalette-hex-dead-tailwind-class
          # — the policy existed, this caller predated it).
          #
          # A BOUND colour is not a palette name either, and map_color made
          # `placeholder-@{v}`. `::placeholder` is a pseudo-element that no
          # inline declaration can reach, so the binding rides a custom
          # property the arbitrary value reads back.
          # `hintAttributes` carries the same spellings in a nested object and
          # the nested keys win: a bag scoped to the hint is the more specific
          # statement (the cascade every other reader takes — rjui
          # label_converter, sjui textview_converter, kjui textview_component).
          # This reader had it backwards for fontColor and did not read the
          # bag's other keys at all.
          hint_bag = attributes['hintAttributes'].is_a?(Hash) ? attributes['hintAttributes'] : {}
          hint_color = hint_bag['fontColor'] || attributes['hintColor'] || attributes['placeholderColor']
          if hint_color
            classes << (bound_state_color_class(hint_color, custom_property: '--jui-hint-color', prefix: 'placeholder') ||
                        TailwindMapper.map_color(hint_color, 'placeholder'))
          end

          # Placeholder typography, through the `placeholder:` variant so it
          # targets ::placeholder rather than the textarea's own text.
          hint_font_size = hint_bag['fontSize'] || attributes['hintFontSize']
          if hint_font_size
            classes << "placeholder:text-[#{hint_font_size.to_i}px]"
          end
          if (hint_font_name = hint_bag['font'] || attributes['hintFont'])
            hint_font = TailwindMapper.map_font(hint_font_name)
            classes << "placeholder:#{hint_font}" if hint_font && !hint_font.empty?
          end
          if (hint_leading = hint_bag['lineHeightMultiple'] || attributes['hintLineHeightMultiple'])
            classes << "placeholder:leading-[#{hint_leading}]"
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
          #
          # Two of the six declared values are WRAP modes, not truncation:
          # `Char` breaks mid-word, `Word` is ordinary word wrapping. Neither
          # had a branch, so both fell through to the unconditional
          # `overflow: hidden` below and were given truncation behaviour —
          # the opposite of what they ask for. Only the truncating modes clip.
          case attributes['lineBreakMode']
          when 'Char'
            @dynamic_styles['wordBreak'] = "'break-all'"
          when 'Word'
            @dynamic_styles['overflowWrap'] = "'break-word'"
          when 'Head'
            @dynamic_styles['textOverflow'] = "'ellipsis'"
            @dynamic_styles['direction'] = "'rtl'"
            @dynamic_styles['textAlign'] = "'left'"
            @dynamic_styles['overflow'] = "'hidden'"
          when 'Middle', 'Tail', 'Clip'
            @dynamic_styles['textOverflow'] = "'ellipsis'"
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

          # One renderer for every converter (BaseConverter#style_attr_for):
          # the SPREAD sentinel and the `React.CSSProperties` assertion a
          # custom-property key needs are handled in ONE place. Six converters
          # had hand-copied this loop, and four of the copies had lost the
          # assertion — which only surfaced when a bound colour started
          # writing `--jui-*` keys and the host's tsc rejected them.
          style_attr_for(@dynamic_styles)
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
          # `asciiCapable` is an explicit request for a text keyboard;
          # `default` is "whatever the platform picks", which on the web IS
          # the absence of an inputMode. Collapsing both onto 'text' made two
          # declared values emit byte-identical output (C2/presence-only).
          when 'asciicapable', 'text' then 'text'
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
