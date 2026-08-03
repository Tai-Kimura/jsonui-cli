# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      # ToggleConverter generates simple checkbox UI for "CheckBox" and "Check" components.
      # CheckBox is the primary component name, Check is supported as an alias for backward compatibility.
      # Note: "Switch" and "Toggle" use SwitchConverter for iOS-style toggle switches.
      class ToggleConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          style_attr = build_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr
          # 'label' is the CheckBox-specific spelling and wins over the
          # generic text (kjui reads the same order — 33 cross-effect
          # adjudication: label overrides text on every platform).
          text = attributes['label'] || attributes['text'] || ''

          # Get state binding
          checked_attr = build_checked_attr
          on_change = build_on_change
          disabled_attr = build_disabled_attr
          checkbox_style = build_checkbox_style

          jsx = if text.empty?
            # Checkbox only (no label)
            <<~JSX.chomp
              #{indent_str(indent)}<input#{id_attr} type="checkbox" className="#{class_name}"#{checked_attr}#{on_change}#{disabled_attr}#{checkbox_style}#{style_attr}#{testid_attr}#{tag_attr} />
            JSX
          else
            # Checkbox with label. The layout `id` lands on the <label>
            # wrapper, so reflect the disabled state there too (the native
            # `disabled` attr only exists on the inner <input>).
            # Custom icon checkbox: hidden input + state-swapped images
            # ('src' is the unchecked spelling, selectedIcon the checked one
            # — 33 cross-effect: web rendered the native box for them).
            icon_off = attributes['icon'] || attributes['src']
            icon_on = attributes['selectedIcon'] || icon_off
            if icon_off || icon_on
              off_src = icon_off || icon_on
              control_jsx =
                "<input type=\"checkbox\"#{checked_attr}#{on_change}#{disabled_attr} className=\"peer sr-only\" />"                 "<img src=\"#{off_src}\" alt=\"\" className=\"w-6 h-6 peer-checked:hidden\" />"                 "<img src=\"#{icon_on}\" alt=\"\" className=\"w-6 h-6 hidden peer-checked:block\" />"
              <<~JSX.chomp
                #{indent_str(indent)}<label#{id_attr} className="#{class_name}"#{style_attr}#{testid_attr}#{tag_attr}#{build_aria_disabled_attr}>
                #{indent_str(indent + 2)}#{control_jsx}
                #{indent_str(indent + 2)}<span>#{convert_text_binding(text)}</span>
                #{indent_str(indent)}</label>
              JSX
            else
              <<~JSX.chomp
                #{indent_str(indent)}<label#{id_attr} className="#{class_name}"#{style_attr}#{testid_attr}#{tag_attr}#{build_aria_disabled_attr}>
                #{indent_str(indent + 2)}<input type="checkbox"#{checked_attr}#{on_change}#{disabled_attr}#{checkbox_style} />
                #{indent_str(indent + 2)}<span>#{convert_text_binding(text)}</span>
                #{indent_str(indent)}</label>
              JSX
            end
          end

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]

          if attributes['text'] || attributes['label']
            # `spacing` = control-to-label gap, same reading as kjui's checkbox.
            spacing = attributes['spacing']
            classes << 'flex items-center'
            classes << (spacing ? "gap-[#{spacing}px]" : 'gap-2')
          end
          classes << 'cursor-pointer'

          # Disabled state
          if attributes['enabled'] == false
            classes << 'opacity-50 cursor-not-allowed'
          elsif has_binding?(attributes['enabled'])
            binding_expr = extract_binding_property(attributes['enabled'])
            classes << "${!#{binding_expr} ? 'opacity-50 cursor-not-allowed' : ''}"
          end

          finalize_classes(classes)
        end

        def build_checked_attr
          is_on = with_bind_fallback(attributes['isOn'] || attributes['checked'])

          if is_on && has_binding?(is_on)
            prop = extract_binding_property(is_on)
            " checked={#{prop}}"
          elsif is_on
            ' defaultChecked'
          else
            ''
          end
        end

        def build_on_change
          # If custom handler is defined, use it (passing the event object)
          handler = attributes['onValueChange']
          if handler && has_binding?(handler)
            prop = extract_binding_property(handler)
            return " onChange={(e) => #{prop}?.(e.target.checked)}"
          end

          # Auto-generate onChange from isOn/checked binding property
          # e.g., isOn: "@{isEnabled}" -> onChange={(e) => data.onIsEnabledChange?.(e.target.checked)}
          is_on = with_bind_fallback(attributes['isOn'] || attributes['checked'])
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
          enabled = attributes['enabled']
          return '' if enabled.nil?

          if has_binding?(enabled)
            " disabled={!#{extract_binding_property(enabled)}}"
          elsif enabled == false
            ' disabled'
          else
            ''
          end
        end

        def build_checkbox_style
          # Same precedence as kjui's switch_component: onTintColor || tint || tintColor.
          tint_color = attributes['onTintColor'] || attributes['tint'] || attributes['tintColor']
          return '' unless tint_color

          " style={{ accentColor: '#{tint_color}' }}"
        end
      end
    end
  end
end
