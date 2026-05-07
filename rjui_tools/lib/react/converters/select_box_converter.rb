# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class SelectBoxConverter < BaseConverter
        def convert(indent = 2)
          # Date picker mode: selectItemType == "Date"
          select_item_type = json['selectItemType']
          if select_item_type&.downcase == 'date'
            return generate_date_picker(indent)
          end

          class_name = build_class_name
          style_attr = build_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr
          items = json['items'] || []

          value_attr = build_value_attr
          on_change = build_on_change
          disabled_attr = build_disabled_attr

          jsx = if items.is_a?(String) && has_binding?(items)
            generate_dynamic_select(indent, id_attr, class_name, style_attr, testid_attr, tag_attr, value_attr, on_change, disabled_attr, items)
          else
            generate_static_select(indent, id_attr, class_name, style_attr, testid_attr, tag_attr, value_attr, on_change, disabled_attr, items)
          end

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]

          # Default select styling
          classes << 'border'
          classes << 'rounded-md'
          classes << 'pl-3 pr-8 py-2'
          classes << 'bg-white' unless json['background']
          classes << 'cursor-pointer'
          classes << 'outline-none'
          classes << 'focus:ring-2 focus:ring-blue-500 focus:border-blue-500'

          # Border color
          border_color = json['borderColor']
          classes << TailwindMapper.map_color(border_color, 'border') if border_color

          # Font color
          font_color = json['fontColor']
          classes << TailwindMapper.map_color(font_color, 'text') if font_color

          # Font size
          font_size = json['fontSize']
          classes << TailwindMapper.map_font_size(font_size) if font_size

          # Hint/placeholder color for when no value is selected
          hint_color = json['hintColor'] || json['placeholderColor']
          @select_hint_color = hint_color || 'gray-400'

          # Disabled state
          if json['enabled'] == false
            classes << 'opacity-50 cursor-not-allowed'
          elsif has_binding?(json['enabled'])
            binding_expr = extract_binding_property(json['enabled'])
            classes << "${!#{binding_expr} ? 'opacity-50 cursor-not-allowed' : ''}"
          end

          classes.compact.reject(&:empty?).join(' ')
        end

        private

        # Build className attribute for select, with dynamic hint color when no value is selected
        def build_select_class_attr(class_name)
          hint_color = @select_hint_color
          value_binding = json['selectedValue'] || json['value']

          if value_binding && has_binding?(value_binding)
            prop = extract_binding_property(value_binding)
            hint_class = "text-#{hint_color}"
            font_color = json['fontColor']
            normal_class = font_color ? "text-#{font_color}" : ''
            "className={`#{class_name} ${#{prop} ? '#{normal_class}' : '#{hint_class}'}`}"
          else
            "className=\"#{class_name}\""
          end
        end

        def resolve_hint_text(hint)
          return hint unless hint
          resolved = convert_binding(hint)
          if resolved != hint && resolved.include?('{')
            resolved
          else
            hint
          end
        end

        def generate_dynamic_select(indent, id_attr, class_name, style_attr, testid_attr, tag_attr, value_attr, on_change, disabled_attr, items)
          items_prop = extract_binding_property(items)
          hint = json['hint'] || json['placeholder']
          hint_text = resolve_hint_text(hint)
          hint_option = hint ? "\n#{indent_str(indent + 2)}<option value=\"\" disabled hidden>#{hint_text}</option>" : ''
          class_attr = build_select_class_attr(class_name)

          <<~JSX.chomp
            #{indent_str(indent)}<select#{id_attr} #{class_attr}#{value_attr}#{on_change}#{disabled_attr}#{style_attr}#{testid_attr}#{tag_attr}>#{hint_option}
            #{indent_str(indent + 2)}{#{items_prop}?.map((item) => (
            #{indent_str(indent + 4)}<option key={item.value || item.id} value={item.value || item.id}>{item.text || item.label}</option>
            #{indent_str(indent + 2)}))}
            #{indent_str(indent)}</select>
          JSX
        end

        def generate_static_select(indent, id_attr, class_name, style_attr, testid_attr, tag_attr, value_attr, on_change, disabled_attr, items)
          options_jsx = items.map do |item|
            if item.is_a?(Hash)
              value = item['value'] || item['id'] || item['text']
              label = item['text'] || item['label'] || value
              "#{indent_str(indent + 2)}<option value=\"#{value}\">#{label}</option>"
            else
              "#{indent_str(indent + 2)}<option value=\"#{item}\">#{item}</option>"
            end
          end.join("\n")

          hint = json['hint'] || json['placeholder']
          if hint
            hint_text = resolve_hint_text(hint)
            options_jsx = "#{indent_str(indent + 2)}<option value=\"\" disabled hidden>#{hint_text}</option>\n#{options_jsx}"
          end

          class_attr = build_select_class_attr(class_name)

          <<~JSX.chomp
            #{indent_str(indent)}<select#{id_attr} #{class_attr}#{value_attr}#{on_change}#{disabled_attr}#{style_attr}#{testid_attr}#{tag_attr}>
            #{options_jsx}
            #{indent_str(indent)}</select>
          JSX
        end

        def build_value_attr
          value = json['selectedValue'] || json['value']

          if value && has_binding?(value)
            prop = extract_binding_property(value)
            " value={#{prop}}"
          elsif value
            " defaultValue=\"#{value}\""
          else
            ''
          end
        end

        def build_on_change
          handler = json['onValueChange'] || json['onValueChanged'] || json['onChange']
          if handler
            if has_binding?(handler)
              prop = extract_binding_property(handler)
              return " onChange={(e) => #{prop}?.(e.target.value)}"
            else
              return " onChange={(e) => #{handler}?.(e.target.value)}"
            end
          end

          # Auto-generate onChange from value binding (two-way binding)
          value_key = json['selectedValue'] || json['value'] || json['selectedIndex']
          if value_key && has_binding?(value_key)
            property_name = value_key.match(/@\{(.+)\}/)[1]
            handler_name = "on#{property_name[0].upcase}#{property_name[1..]}Change"
            return " onChange={(e) => data.#{handler_name}?.(e.target.value)}"
          end

          ''
        end

        def build_disabled_attr
          enabled = json['enabled']
          return '' if enabled.nil?

          if has_binding?(enabled)
            " disabled={#{extract_binding_property(enabled)} !== \"true\"}"
          elsif enabled == false
            ' disabled'
          else
            ''
          end
        end

        def generate_date_picker(indent)
          class_name = build_class_name
          style_attr = build_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr
          disabled_attr = build_disabled_attr

          # Determine input type from datePickerMode
          date_picker_mode = json['datePickerMode']&.downcase
          input_type = case date_picker_mode
                       when 'time' then 'time'
                       when 'datetime', 'dateandtime' then 'datetime-local'
                       else 'date'
                       end

          # Value binding (selectedDate or selectedValue)
          date_value = json['selectedDate'] || json['selectedValue'] || json['value']
          value_attr = if date_value && has_binding?(date_value)
                         prop = extract_binding_property(date_value)
                         " value={#{prop} || ''}"
                       elsif date_value
                         " value=\"#{date_value}\""
                       else
                         ''
                       end

          # Min/max date
          min_attr = json['minimumDate'] ? " min=\"#{json['minimumDate']}\"" : ''
          max_attr = json['maximumDate'] ? " max=\"#{json['maximumDate']}\"" : ''

          # onChange handler
          on_change = build_date_on_change(date_value)

          # Apply color-scheme for dark backgrounds so the calendar icon is visible
          date_style = build_date_style_attr
          combined_style = date_style.empty? ? style_attr : date_style

          jsx = "#{indent_str(indent)}<input#{id_attr} className=\"#{class_name}\" type=\"#{input_type}\"#{value_attr}#{on_change}#{min_attr}#{max_attr}#{disabled_attr}#{combined_style}#{testid_attr}#{tag_attr} />"

          wrap_with_visibility(jsx, indent)
        end

        def build_date_style_attr
          color_scheme = json['colorScheme']
          existing_style = build_style_attr

          if color_scheme
            if existing_style.include?('style=')
              existing_style.sub('style={{', "style={{ colorScheme: '#{color_scheme}',")
            else
              " style={{ colorScheme: '#{color_scheme}' }}"
            end
          else
            existing_style
          end
        end

        def build_date_on_change(date_value)
          # Custom handler takes priority
          handler = json['onValueChange'] || json['onChange']
          if handler && has_binding?(handler)
            prop = extract_binding_property(handler)
            return " onChange={(e) => #{prop}?.(e.target.value)}"
          end

          # Auto-generate from selectedDate binding
          if date_value && has_binding?(date_value)
            property_name = date_value.match(/@\{(.+)\}/)[1]
            handler_name = "on#{property_name[0].upcase}#{property_name[1..]}Change"
            return " onChange={(e) => data.#{handler_name}?.(e.target.value)}"
          end

          ''
        end
      end
    end
  end
end
