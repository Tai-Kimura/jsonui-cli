# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class TextFieldConverter < BaseConverter
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

          jsx = "#{indent_str(indent)}<input#{id_attr} className=\"#{class_name}\"#{style_attr}#{attrs}#{on_change}#{focus_attrs}#{disabled_attr}#{testid_attr}#{tag_attr} />"

          wrap_with_visibility(jsx, indent)
        end

        protected

        def apply_defaults
          # Apply textField defaults if not explicitly set
          text_field_defaults = defaults('textField')
          return if text_field_defaults.empty?

          @json = json.dup
          @attributes['fontColor'] ||= text_field_defaults['fontColor']
          @attributes['padding'] ||= text_field_defaults['padding']
          @attributes['background'] ||= text_field_defaults['background']
          @attributes['cornerRadius'] ||= text_field_defaults['cornerRadius']
        end

        def build_class_name
          classes = [super]

          # Default input styles (no border unless explicitly set via borderWidth)
          classes << 'outline-none'
          classes << 'focus:ring-2 focus:ring-blue-500'

          # Border style (only when borderWidth is set)
          if attributes['borderWidth'] || attributes['borderStyle']
            case attributes['borderStyle']&.downcase
            when 'roundedrect'
              classes << 'rounded-md'
            when 'line'
              classes << 'border-b border-t-0 border-l-0 border-r-0 rounded-none'
            when 'none'
              classes << 'border-0'
            end
          end

          # Placeholder color using Tailwind
          if attributes['hintColor'] || attributes['placeholderColor']
            color = attributes['hintColor'] || attributes['placeholderColor']
            classes << "placeholder-#{color}"
          end

          # Disabled state
          if attributes['enabled'] == false || attributes['enabled'].is_a?(String)
            if attributes['disabledBackground']
              classes << "disabled:#{TailwindMapper.map_color(attributes['disabledBackground'], 'bg')}"
            else
              classes << 'disabled:bg-gray-100'
            end
            classes << 'disabled:cursor-not-allowed'
          end

          classes.compact.reject(&:empty?).join(' ')
        end

        def build_style_attr
          super

          # Corner radius
          if attributes['cornerRadius']
            @dynamic_styles['borderRadius'] = "'#{attributes['cornerRadius']}px'"
          end

          # Hint/placeholder color is now handled via Tailwind class in build_class_name

          # Caret (cursor) color
          if attributes['caretAttributes'] && attributes['caretAttributes']['fontColor']
            @dynamic_styles['caretColor'] = color_style_expr(attributes['caretAttributes']['fontColor'])
          end

          # Text padding left
          if attributes['textPaddingLeft']
            @dynamic_styles['paddingLeft'] = "'#{attributes['textPaddingLeft']}px'"
          end

          # Shadow
          if attributes['shadow']
            if attributes['shadow'].is_a?(Hash)
              radius = attributes['shadow']['radius'] || 5
              x = attributes['shadow']['offsetX'] || 0
              y = attributes['shadow']['offsetY'] || 0
              color = attributes['shadow']['color'] || 'rgba(0,0,0,0.2)'
              @dynamic_styles['boxShadow'] = "'#{x}px #{y}px #{radius}px #{color}'"
            else
              @dynamic_styles['boxShadow'] = "'0 2px 4px rgba(0,0,0,0.1)'"
            end
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

          # Type based on input attribute
          input_type = determine_input_type
          attrs << " type=\"#{input_type}\""

          # Name attribute
          attrs << " name=\"#{attributes['name']}\"" if attributes['name']

          # Placeholder (hint in SwiftJsonUI terminology)
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

          # Max length
          attrs << " maxLength={#{attributes['maxLength']}}" if attributes['maxLength']

          # Auto complete / content type
          if attributes['contentType']
            autocomplete = map_content_type(attributes['contentType'])
            attrs << " autoComplete=\"#{autocomplete}\"" if autocomplete
          end

          # Input mode (for mobile keyboards)
          if attributes['input']
            inputmode = map_input_mode(attributes['input'])
            attrs << " inputMode=\"#{inputmode}\"" if inputmode
          end

          # Return key type (for form submission)
          if attributes['returnKeyType']
            enter_key_hint = map_return_key(attributes['returnKeyType'])
            attrs << " enterKeyHint=\"#{enter_key_hint}\"" if enter_key_hint
          end

          # Auto focus
          attrs << ' autoFocus' if attributes['autoFocus'] || attributes['becomeFirstResponder']

          # Read only
          attrs << ' readOnly' if attributes['readOnly'] || attributes['editable'] == false

          attrs.join
        end

        def determine_input_type
          # Secure field takes precedence
          return 'password' if attributes['secure'] || attributes['input']&.downcase == 'password'

          case attributes['input']&.downcase
          when 'email'
            'email'
          when 'number', 'decimal', 'numberpad', 'decimalpad'
            'number'
          when 'tel', 'phonenumber', 'namephonepad'
            'tel'
          when 'url'
            'url'
          when 'search', 'websearch'
            'search'
          else
            'text'
          end
        end

        def map_content_type(type)
          case type&.downcase
          when 'username'
            'username'
          when 'password'
            'current-password'
          when 'newpassword'
            'new-password'
          when 'email'
            'email'
          when 'name'
            'name'
          when 'givenname'
            'given-name'
          when 'familyname'
            'family-name'
          when 'tel', 'telephonenumber'
            'tel'
          when 'streetaddress'
            'street-address'
          when 'postalcode'
            'postal-code'
          when 'country'
            'country'
          when 'creditcardnumber'
            'cc-number'
          else
            nil
          end
        end

        def map_input_mode(input)
          case input&.downcase
          when 'number', 'numberpad'
            'numeric'
          when 'decimal', 'decimalpad'
            'decimal'
          when 'tel', 'phonenumber'
            'tel'
          when 'email'
            'email'
          when 'url'
            'url'
          when 'search', 'websearch'
            'search'
          else
            nil
          end
        end

        def map_return_key(return_key)
          case return_key
          when 'Done'
            'done'
          when 'Go'
            'go'
          when 'Next'
            'next'
          when 'Search'
            'search'
          when 'Send'
            'send'
          when 'Enter', 'Return'
            'enter'
          else
            nil
          end
        end

        def build_on_change
          # If custom handler is defined, use it (passing the event object)
          handler = attributes['onTextChange'] || attributes['onChange']
          if handler
            if has_binding?(handler)
              prop = extract_binding_property(handler)
              return " onChange={(e) => #{prop}?.(e.target.value)}"
            else
              return " onChange={(e) => #{handler}?.(e.target.value)}"
            end
          end

          # Auto-generate onChange from text binding property
          # e.g., text: "@{email}" -> onChange={(e) => data.onEmailChange?.(e.target.value)}
          if attributes['text'] && has_binding?(attributes['text'])
            # Use raw property name without data. prefix
            property_name = extract_raw_binding_property(attributes['text'])
            # Convert property name to onChange handler name (e.g., email -> onEmailChange)
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
