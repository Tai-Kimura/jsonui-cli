#!/usr/bin/env ruby

require_relative 'base_view_converter'
require_relative '../helpers/font_helper'

module SjuiTools
  module SwiftUI
    module Views
      # ToggleConverter handles both "Toggle" and "Switch" component types.
      # "Switch" is the primary name, "Toggle" is supported for backward compatibility.
      # This converter is registered for both component types in converter_factory.rb.
      class ToggleConverter < BaseViewConverter
        include SjuiTools::SwiftUI::Helpers::FontHelper
        def convert
          # Get toggle handler for this component
          toggle_handler = @binding_handler.is_a?(SjuiTools::SwiftUI::Binding::ToggleBindingHandler) ?
                           @binding_handler :
                           SjuiTools::SwiftUI::Binding::ToggleBindingHandler.new

          id = @component['id'] || 'toggle'
          text = @component['text'] || @component['label'] || ""

          # Get state binding from handler
          state_binding = if @component['isOn'] && is_binding?(@component['isOn'])
                           "$data.#{extract_binding_property(@component['isOn'])}"
                         elsif @component['checked'] && is_binding?(@component['checked'])
                           toggle_handler.get_state_binding(@component)
                         elsif @component['value'] && is_binding?(@component['value'])
                           # `value` is the cross-platform alias of the on/off
                           # state (kjui and web both accept it).
                           "$data.#{extract_binding_property(@component['value'])}"
                         else
                           # View-local @State fallback (injected by
                           # update_generated_body) — bare reference; `$data.`
                           # pointed at a property the Data model never grows
                           # and did not compile (codegen parity host,
                           # __control/Switch, 2026-08-02).
                           state_var = "#{id}IsOn"
                           add_state_variable(state_var, "Bool", @component['isOn'] || @component['checked'] || @component['value'] == true ? 'true' : 'false')
                           "$#{state_var}"
                         end

          # Toggle
          add_line "Toggle(isOn: #{state_binding}) {"
          indent do
            # Escape double quotes in text for Swift string literal
            escaped_text = text.gsub('"', '\\"')
            add_line "Text(\"#{escaped_text}\")"

            # labelAttributes の処理
            if @component['labelAttributes']
              label_attrs = @component['labelAttributes']

              # Apply font modifiers using helper - prioritize labelAttributes over component attributes
              merged_attrs = @component.merge(label_attrs)
              apply_font_modifiers(merged_attrs, self)

              # fontColor
              if label_attrs['fontColor'] || label_attrs['color']
                color = get_swiftui_color(label_attrs['fontColor'] || label_attrs['color'])
                add_modifier_line ".foregroundColor(#{color})"
              elsif @component['fontColor']
                color = get_swiftui_color(@component['fontColor'])
                add_modifier_line ".foregroundColor(#{color})"
              end
            else
              # Apply font modifiers using helper
              apply_font_modifiers(@component, self)

              # fontColor
              if @component['fontColor']
                color = get_swiftui_color(@component['fontColor'])
                add_modifier_line ".foregroundColor(#{color})"
              end
            end
          end
          add_line "}"

          # Mirror the dynamic ToggleConverter's layout contract (measured as
          # the whole Switch parity family, d=37-49):
          # - no label -> hide the empty label slot; otherwise SwiftUI keeps a
          #   full-width row with the control pinned trailing while dynamic
          #   (and kjui/rjui) hug the control.
          # - explicit wrapContent -> hug content instead of Toggle's greedy
          #   full-width layout.
          add_modifier_line '.labelsHidden()' if text.to_s.empty?
          if @component['width'] == 'wrapContent'
            add_modifier_line '.fixedSize(horizontal: true, vertical: false)'
          end

          # toggleStyle
          if @component['toggleStyle']
            case @component['toggleStyle']
            when 'switch'
              add_modifier_line ".toggleStyle(SwitchToggleStyle())"
            when 'button'
              add_modifier_line ".toggleStyle(ButtonToggleStyle())"
            when 'checkbox'
              add_modifier_line ".toggleStyle(CheckboxToggleStyle())"
            else
              add_modifier_line ".toggleStyle(DefaultToggleStyle())"
            end
          end

          # onTintColor / tintColor / tint -> .tint() modifier (`tint` is the
          # short spelling kjui's switch precedence also accepts).
          #
          # trackTintColor closes the chain, matching the dynamic
          # ToggleConverter. Canonically it is the OFF track and onTintColor
          # overrides it while on (attribute_semantics.json
          # trackColors.switchTrack, 2026-08-06); SwiftUI's Toggle exposes no
          # OFF-track surface, so both sides degrade it identically to the
          # `.tint()` fallback rather than painting the view's background —
          # the reading the same ruling names as wrong (`.background()` was
          # the previous emit here, ios parity d 23).
          tint = @component['onTintColor'] || @component['tintColor'] ||
                 @component['tint'] || @component['trackTintColor']
          if tint
            color = get_swiftui_color(tint)
            add_modifier_line ".tint(#{color})"
          end

          apply_thumb_tint_color

          # onValueChange handler - called when toggle state changes
          # onValueChange (camelCase) -> binding format only (@{functionName})
          # onToggle is an alias of onValueChange (parity with kjui_tools).
          handler_attr = @component['onValueChange'] || @component['onToggle']
          if handler_attr && is_binding?(handler_attr)
            binding_prop = if @component['isOn'] && is_binding?(@component['isOn'])
                            extract_binding_property(@component['isOn'])
                          elsif @component['checked'] && is_binding?(@component['checked'])
                            extract_binding_property(@component['checked'])
                          else
                            "#{id}IsOn"
                          end
            handler_call = get_event_handler_invocation(handler_attr, id, 'newValue')
            add_modifier_line ".onChange(of: data.#{binding_prop}) { _, newValue in"
            indent do
              add_line handler_call
            end
            add_line "}"
          end

          # 共通のモディファイアを適用
          apply_modifiers

          generated_code
        end

        private

        # thumbTintColor — the knob, not the track.
        #
        # `.tint()` colours the track, and SwiftUI exposes nothing for the knob,
        # so this goes through UISwitch.appearance() in .onAppear — the same
        # route Segment takes for its own UIKit-only appearance keys. A binding
        # is resolved at appear time, which is when the appearance proxy is read.
        def apply_thumb_tint_color
          thumb = @component['thumbTintColor']
          return if thumb.nil?

          add_modifier_line ".onAppear {"
          add_modifier_line "    UISwitch.appearance().thumbTintColor = UIColor(#{get_swiftui_color(thumb)})"
          add_modifier_line "}"
        end

        def add_state_variable(name, type, default_value)
          @state_variables ||= []
          @state_variables << "@State private var #{name}: #{type} = #{default_value}"
        end
      end
    end
  end
end
