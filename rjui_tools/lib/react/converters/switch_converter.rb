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
          text = attributes['text'] || attributes['label'] || ''

          checked_attr = build_checked_attr
          on_change = build_on_change
          disabled_attr = build_disabled_attr
          # `onTintColor` is the track colour when on, `tint` and `tintColor` are the
          # generic spellings (kjui: onTintColor || tint || tintColor).
          tint_color = attributes['onTintColor'] || attributes['tint'] ||
                       attributes['tintColor'] || '#34C759'
          thumb_color = attributes['thumbTintColor'] || '#FFFFFF'
          # `trackTintColor` is the declared spelling for the track itself and
          # skins the OFF state; `onTintColor` overrides it when on
          # (switch.trackColors in shared/core/attribute_semantics.json).
          off_tint_color = attributes['trackTintColor'] ||
                           attributes['offTintColor'] || '#E5E7EB'

          # iOS-style toggle switch using pure CSS
          switch_html = build_switch_element(checked_attr, on_change, disabled_attr, tint_color, thumb_color, off_tint_color)

          # The layout `id` lands on the wrapper (div/label), not on the inner
          # <input>, so reflect the disabled state on the wrapper for
          # accessibility / testability (mirrors the native `disabled` attr).
          aria_disabled_attr = build_aria_disabled_attr

          # Both branches must render a <label>: the real <input> is visually
          # hidden (sr-only) behind the styled track/knob spans, and only a
          # wrapping <label> forwards clicks to it — with a bare <div> a
          # text-less Switch renders fine but can never be toggled.
          jsx = if text.empty?
            "#{indent_str(indent)}<label#{id_attr} className=\"#{class_name} cursor-pointer\"#{style_attr}#{testid_attr}#{tag_attr}#{aria_disabled_attr}>#{switch_html}</label>"
          else
            <<~JSX.chomp
              #{indent_str(indent)}<label#{id_attr} className="#{class_name} flex items-center gap-3 cursor-pointer"#{style_attr}#{testid_attr}#{tag_attr}#{aria_disabled_attr}>
              #{indent_str(indent + 2)}#{switch_html}
              #{indent_str(indent + 2)}<span>#{convert_text_binding(text)}</span>
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
          if attributes['enabled'] == false
            classes << 'opacity-50 cursor-not-allowed'
          elsif has_binding?(attributes['enabled'])
            binding_expr = extract_binding_property(attributes['enabled'])
            classes << "${!#{binding_expr} ? 'opacity-50 cursor-not-allowed' : ''}"
          end

          finalize_classes(classes)
        end

        def build_switch_element(checked_attr, on_change, disabled_attr, tint_color, thumb_color, off_tint_color)
          # A bound colour cannot be an arbitrary-value class: `bg-[@{v}]`
          # matches nothing, so the track and the knob simply lost their
          # colour. These spans are composed here rather than being the
          # subtree root, so they carry their own inline style.
          #
          # The OFF track colour and the knob colour are unconditional and go
          # straight into `backgroundColor`. The ON colour is behind
          # `peer-checked:` — a pseudo-class no inline declaration can be
          # scoped to — so it rides a custom property that the variant reads
          # back on the same element.
          track_style = {}
          off_class =
            if has_binding?(off_tint_color)
              track_style['backgroundColor'] = color_style_expr(off_tint_color)
              nil
            else
              "bg-[#{off_tint_color}]"
            end
          on_class =
            if has_binding?(tint_color)
              track_style['--jui-switch-on'] = color_style_expr(tint_color)
              'peer-checked:bg-[var(--jui-switch-on)]'
            else
              "peer-checked:bg-[#{tint_color}]"
            end

          knob_style = {}
          knob_color_class =
            if has_binding?(thumb_color)
              knob_style['backgroundColor'] = color_style_expr(thumb_color)
              nil
            else
              "bg-[#{thumb_color}]"
            end

          track_classes = ['absolute inset-0', off_class, 'rounded-full transition-colors duration-200', on_class].compact.join(' ')
          knob_classes = ['absolute left-[2px] top-[2px] w-[27px] h-[27px]', knob_color_class,
                          'rounded-full shadow transition-transform duration-200 peer-checked:translate-x-[20px]'].compact.join(' ')

          # Create iOS-style toggle with hidden checkbox and styled span
          <<~HTML.gsub("\n", '').gsub(/\s+/, ' ').strip
            <span className="relative inline-block w-[51px] h-[31px]">
              <input type="checkbox" className="sr-only peer"#{checked_attr}#{on_change}#{disabled_attr} />
              <span className="#{track_classes}"#{style_attr_for(track_style)} />
              <span className="#{knob_classes}"#{style_attr_for(knob_style)} />
            </span>
          HTML
        end

        def build_checked_attr
          is_on = with_bind_fallback(attributes['isOn'] || attributes['checked'] || attributes['value'])

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
          handler = attributes['onValueChange']
          if handler && has_binding?(handler)
            prop = extract_binding_property(handler)
            return " onChange={(e) => #{prop}?.(e.target.checked)}"
          end

          # Auto-generate onChange from isOn/checked/value binding property
          # e.g., isOn: "@{isEnabled}" -> onChange={(e) => data.onIsEnabledChange?.(e.target.checked)}
          is_on = with_bind_fallback(attributes['isOn'] || attributes['checked'] || attributes['value'])
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
      end
    end
  end
end
