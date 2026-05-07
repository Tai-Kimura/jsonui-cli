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

          jsx = "#{indent_str(indent)}<input#{id_attr} className=\"#{class_name}\"#{style_attr}#{attrs}#{on_change}#{disabled_attr}#{testid_attr}#{tag_attr} />"

          wrap_with_visibility(jsx, indent)
        end

        protected

        def apply_defaults
          # Apply textField defaults if not explicitly set
          text_field_defaults = defaults('textField')
          return if text_field_defaults.empty?

          @json = json.dup
          @json['fontColor'] ||= text_field_defaults['fontColor']
          @json['padding'] ||= text_field_defaults['padding']
          @json['background'] ||= text_field_defaults['background']
          @json['cornerRadius'] ||= text_field_defaults['cornerRadius']
        end

        def build_class_name
          classes = [super]

          # Default input styles (no border unless explicitly set via borderWidth)
          classes << 'outline-none'
          classes << 'focus:ring-2 focus:ring-blue-500'

          # Border style (only when borderWidth is set)
          if json['borderWidth'] || json['borderStyle']
            case json['borderStyle']&.downcase
            when 'roundedrect'
              classes << 'rounded-md'
            when 'line'
              classes << 'border-b border-t-0 border-l-0 border-r-0 rounded-none'
            when 'none'
              classes << 'border-0'
            end
          end

          # Placeholder color using Tailwind
          if json['hintColor'] || json['placeholderColor']
            color = json['hintColor'] || json['placeholderColor']
            classes << "placeholder-#{color}"
          end

          # Disabled state
          if json['enabled'] == false || json['enabled'].is_a?(String)
            if json['disabledBackground']
              classes << "disabled:#{TailwindMapper.map_color(json['disabledBackground'], 'bg')}"
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
          if json['cornerRadius']
            @dynamic_styles['borderRadius'] = "'#{json['cornerRadius']}px'"
          end

          # Hint/placeholder color is now handled via Tailwind class in build_class_name

          # Caret (cursor) color
          if json['caretAttributes'] && json['caretAttributes']['fontColor']
            @dynamic_styles['caretColor'] = "'#{json['caretAttributes']['fontColor']}'"
          end

          # Text padding left
          if json['textPaddingLeft']
            @dynamic_styles['paddingLeft'] = "'#{json['textPaddingLeft']}px'"
          end

          # Shadow
          if json['shadow']
            if json['shadow'].is_a?(Hash)
              radius = json['shadow']['radius'] || 5
              x = json['shadow']['offsetX'] || 0
              y = json['shadow']['offsetY'] || 0
              color = json['shadow']['color'] || 'rgba(0,0,0,0.2)'
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
          attrs << " name=\"#{json['name']}\"" if json['name']

          # Placeholder (hint in SwiftJsonUI terminology)
          placeholder = json['hint'] || json['placeholder']
          if placeholder
            resolved = convert_binding(placeholder)
            if resolved != placeholder && resolved.include?('{')
              attrs << " placeholder={#{resolved.gsub(/^\{|\}$/, '')}}"
            else
              attrs << " placeholder=\"#{placeholder}\""
            end
          end

          # Value handling depends on binding presence
          if json['text']
            if has_binding?(json['text'])
              # Binding present: use controlled component (value + onChange)
              value = convert_binding(json['text'])
              attrs << " value={#{value.gsub(/[{}]/, '')}}"
            else
              # No binding: use uncontrolled component (defaultValue only)
              attrs << " defaultValue=\"#{json['text']}\""
            end
          end

          # Max length
          attrs << " maxLength={#{json['maxLength']}}" if json['maxLength']

          # Auto complete / content type
          if json['contentType']
            autocomplete = map_content_type(json['contentType'])
            attrs << " autoComplete=\"#{autocomplete}\"" if autocomplete
          end

          # Input mode (for mobile keyboards)
          if json['input']
            inputmode = map_input_mode(json['input'])
            attrs << " inputMode=\"#{inputmode}\"" if inputmode
          end

          # Return key type (for form submission)
          if json['returnKeyType']
            enter_key_hint = map_return_key(json['returnKeyType'])
            attrs << " enterKeyHint=\"#{enter_key_hint}\"" if enter_key_hint
          end

          # Auto focus
          attrs << ' autoFocus' if json['autoFocus'] || json['becomeFirstResponder']

          # Read only
          attrs << ' readOnly' if json['readOnly'] || json['editable'] == false

          attrs.join
        end

        def determine_input_type
          # Secure field takes precedence
          return 'password' if json['secure'] || json['input']&.downcase == 'password'

          case json['input']&.downcase
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
          handler = json['onTextChange'] || json['onChange']
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
          if json['text'] && has_binding?(json['text'])
            # Use raw property name without data. prefix
            property_name = extract_raw_binding_property(json['text'])
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
          enabled = json['enabled']
          return '' if enabled.nil?

          if enabled.is_a?(String) && enabled.start_with?('@{') && enabled.end_with?('}')
            property_name = enabled[2...-1]
            " disabled={data.#{property_name} !== \"true\"}"
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
