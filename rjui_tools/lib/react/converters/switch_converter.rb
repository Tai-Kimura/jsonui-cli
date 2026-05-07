# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      # SwitchConverter generates iOS-style toggle switches for both "Switch" and "Toggle" components
      # Switch is the primary component name, Toggle is supported as an alias for backward compatibility.
      class SwitchConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          style_attr = build_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr
          text = json['text'] || json['label'] || ''

          checked_attr = build_checked_attr
          on_change = build_on_change
          disabled_attr = build_disabled_attr
          tint_color = json['tintColor'] || json['onTintColor'] || '#34C759'
          thumb_color = json['thumbTintColor'] || '#FFFFFF'
          off_tint_color = json['offTintColor'] || '#E5E7EB'

          # iOS-style toggle switch using pure CSS
          switch_html = build_switch_element(checked_attr, on_change, disabled_attr, tint_color, thumb_color, off_tint_color)

          jsx = if text.empty?
            "#{indent_str(indent)}<div#{id_attr} className=\"#{class_name}\"#{style_attr}#{testid_attr}#{tag_attr}>#{switch_html}</div>"
          else
            <<~JSX.chomp
              #{indent_str(indent)}<label#{id_attr} className="#{class_name} flex items-center gap-3 cursor-pointer"#{style_attr}#{testid_attr}#{tag_attr}>
              #{indent_str(indent + 2)}#{switch_html}
              #{indent_str(indent + 2)}<span>#{convert_binding(text)}</span>
              #{indent_str(indent)}</label>
            JSX
          end

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]
          classes << 'inline-flex'

          # Disabled state
          if json['enabled'] == false
            classes << 'opacity-50 cursor-not-allowed'
          elsif has_binding?(json['enabled'])
            binding_expr = extract_binding_property(json['enabled'])
            classes << "${!#{binding_expr} ? 'opacity-50 cursor-not-allowed' : ''}"
          end

          classes.compact.reject(&:empty?).join(' ')
        end

        def build_switch_element(checked_attr, on_change, disabled_attr, tint_color, thumb_color, off_tint_color)
          # Create iOS-style toggle with hidden checkbox and styled span
          <<~HTML.gsub("\n", '').gsub(/\s+/, ' ').strip
            <span className="relative inline-block w-[51px] h-[31px]">
              <input type="checkbox" className="sr-only peer"#{checked_attr}#{on_change}#{disabled_attr} />
              <span className="absolute inset-0 bg-[#{off_tint_color}] rounded-full transition-colors duration-200 peer-checked:bg-[#{tint_color}]" />
              <span className="absolute left-[2px] top-[2px] w-[27px] h-[27px] bg-[#{thumb_color}] rounded-full shadow transition-transform duration-200 peer-checked:translate-x-[20px]" />
            </span>
          HTML
        end

        def build_checked_attr
          is_on = json['isOn'] || json['checked'] || json['value']

          if is_on && has_binding?(is_on)
            prop = extract_binding_property(is_on)
            " checked={#{prop}}"
          elsif is_on == true
            ' defaultChecked'
          else
            ''
          end
        end

        def build_on_change
          # If custom handler is defined, use it (passing the event object)
          handler = json['onValueChange']
          if handler && has_binding?(handler)
            prop = extract_binding_property(handler)
            return " onChange={(e) => #{prop}?.(e.target.checked)}"
          end

          # Auto-generate onChange from isOn/checked/value binding property
          # e.g., isOn: "@{isEnabled}" -> onChange={(e) => data.onIsEnabledChange?.(e.target.checked)}
          is_on = json['isOn'] || json['checked'] || json['value']
          if is_on && has_binding?(is_on)
            property_name = extract_raw_binding_property(is_on)
            handler_name = "on#{capitalize_first(property_name)}Change"
            return " onChange={(e) => data.#{handler_name}?.(e.target.checked)}"
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

          if has_binding?(enabled)
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
