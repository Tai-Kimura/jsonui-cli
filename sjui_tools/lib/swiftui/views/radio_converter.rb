#!/usr/bin/env ruby

require_relative 'base_view_converter'
require_relative '../helpers/font_helper'

module SjuiTools
  module SwiftUI
    module Views
      class RadioConverter < BaseViewConverter
        include SjuiTools::SwiftUI::Helpers::FontHelper
        def convert
          id = @component['id'] || 'radio'
          items = @component['items'] || []
          # `label` is the specific declared row and wins over the `text`
          # alias — the same precedence CheckBox has taken since it was
          # written. Nothing here read `label` at all, so the attribute was
          # inert on this platform in both its literal and its bound form.
          text = @component['label'] || @component['text'] || ""

          # Check if this is a radio group with items
          if items.any?
            # Get selection binding
            if @component['selectedValue'] && is_binding?(@component['selectedValue'])
              selection_binding = "data.#{extract_binding_property(@component['selectedValue'])}"
            else
              state_var = "selected#{id.split('_').map(&:capitalize).join}"
              # A LITERAL selectedValue names the option that starts selected.
              # Only the bound spelling was read here, so a written-out
              # selection opened the group with nothing chosen — the web
              # converter reads both, and it is the canonical reading
              # (plan 34 / plan 44 Phase 0).
              add_state_variable(state_var, "String", static_selection || '""')
              selection_binding = state_var
            end
            
            # Create radio group with ForEach
            add_line "VStack(alignment: .leading, spacing: 8) {"
            indent do
              if text && !text.empty?
                add_line "Text(#{label_expression(text)})"
                # Apply font modifiers using helper
                apply_font_modifiers(@component, self)
              end

              items.each_with_index do |item, index|
                add_line "HStack#{icon_text_spacing} {"
                indent do
                  add_radio_icon_lines("#{selection_binding} == \"#{item}\"")
                  add_modifier_line ".onTapGesture {"
                  indent do
                    add_line "#{selection_binding} = \"#{item}\""
                    # onValueChange handler - called when radio selection changes
                    # onValueChange (camelCase) -> binding format only (@{functionName})
                    if @component['onValueChange'] && is_binding?(@component['onValueChange'])
                      handler_call = get_event_handler_invocation(@component['onValueChange'], id, index.to_s)
                      add_line handler_call
                    end
                  end
                  add_line "}"
                  # Escape double quotes in item text for Swift string literal
                  escaped_item = item.gsub('"', '\\"')
                  add_line "Text(\"#{escaped_item}\")"
                end
                add_line "}"
              end
            end
            add_line "}"
          else
            # Single radio button (old implementation). `value` is the
            # option's identity within the group (the web converter submits
            # it); the node id is the fallback identity.
            radio_value = @component['value'] || id
            group = @component['group'] || 'defaultGroup'
            
            # Create @State variable name for selection (グループごとに管理)
            state_var = "selected#{group.split('_').map(&:capitalize).join}"
            
            # Add state variable to requirements. The variable is injected
            # into the generated VIEW as `@State private var …`, so references
            # are the bare name — a `data.` prefix points at a property the
            # Data model never grows (uncompilable; caught by the codegen
            # parity host on __control/Radio, 2026-08-02). The items-based
            # branch above already references it bare.
            # A literal `checked: true` seeds the group state with this
            # option's value — the dynamic path renders it selected while an
            # empty seed left every literal-checked radio unselected
            # (32 parity: checked__true / checkedColor / the checked control).
            checked_literal = @component['checked'] == true || @component['isOn'] == true
            # A literal selectedValue names the selected option of the group
            # and wins over this option's own `checked` — it is the group-level
            # statement.
            seed = static_selection || (checked_literal ? "\"#{radio_value}\"" : '""')
            add_state_variable(state_var, "String", seed)

            # A BOUND checked/isOn cannot seed the @State declaration — a
            # property initializer cannot read `data` — so it seeds the glyph
            # the same way the dynamic path does: selected when the group has
            # made no choice yet and the binding says so
            # (RadioConverter.swift `literalChecked && selection.isEmpty`).
            # Ruby truthiness made `"@{x}" == true` false, so the bound form
            # was dropped outright.
            bound_checked = bound_bool(@component['checked']) || bound_bool(@component['isOn'])
            seed = bound_checked ? " || (#{bound_checked} && #{state_var}.isEmpty)" : ''
            
            # カスタムRadioButton実装
            add_line "HStack#{icon_text_spacing} {"
            indent do
              add_radio_icon_lines("#{state_var} == \"#{radio_value}\"#{seed}")
              add_modifier_line ".onTapGesture {"
              indent do
                add_line "#{state_var} = \"#{radio_value}\""
                # onClick handler - called when radio is clicked
                # onClick (camelCase) -> binding format only (@{functionName})
                if @component['onClick'] && is_binding?(@component['onClick'])
                  handler_call = get_event_handler_invocation(@component['onClick'], id, nil)
                  add_line handler_call
                end
              end
              add_line "}"
              
              if text && !text.empty?
                add_line "Text(#{label_expression(text)})"

                # Apply font modifiers using helper
                apply_font_modifiers(@component, self)
                
                if @component['fontColor']
                  color = get_swiftui_color(@component['fontColor'])
                  add_modifier_line ".foregroundColor(#{color})"
                end
              end
            end
            add_line "}"
          end
          
          # Disabled state
          if @component['enabled'] == false
            add_modifier_line ".disabled(true)"
            add_modifier_line ".opacity(0.6)"
          end
          
          # One element carrying the label, the way the dynamic face forms it
          # (RadioConverter.swift: `.accessibilityElement(children: .ignore)`
          # + `.accessibilityLabel(text)`).
          #
          # A radio is in CERTAIN_ACCESSIBILITY_ELEMENT_TYPES — classified a
          # LEAF — but it renders as `HStack { Image; Text }`, which is two
          # elements. Without this the id lands on a container whose
          # accessibility resolves to its first child, so the radio read as
          # the SF Symbol's name ("circle") instead of its own text. The
          # classification said leaf, the emission said container, and nothing
          # reconciled them.
          #
          # `.ignore` rather than `.combine`, matching the dynamic face: the
          # glyph carries nothing a reader needs, and combining would prepend
          # its name to every label.
          a11y_text = @component['label'] || @component['text']
          if a11y_text.is_a?(String) && !a11y_text.empty?
            add_modifier_line ".accessibilityElement(children: .ignore)"
            add_modifier_line ".accessibilityLabel(#{label_expression(a11y_text)})"
          end

          # 共通のモディファイアを適用
          apply_modifiers
          
          generated_code
        end
        
        private

        # A written-out `selectedValue` as a Swift string literal, or nil when
        # it is absent or bound (a binding is the selection itself, not a
        # seed for one).
        def static_selection
          value = @component['selectedValue']
          return nil if value.nil? || is_binding?(value)

          "\"#{value.to_s.gsub('"', '\\"')}\""
        end

        # The `spacing:` argument of the row that holds the glyph and the
        # label, or "" when none is declared (SwiftUI's default spacing is
        # not a number the generator can spell, so an undeclared spacing has
        # to stay an omitted argument rather than become a 0).
        # `Radio.spacing` — "space between icon and text" — was read by
        # nothing here: both rows opened a bare `HStack {`.
        def icon_text_spacing
          spacing = @component['spacing']
          return '' if spacing.nil?

          "(spacing: #{bound_number(spacing) || spacing})"
        end

        # The radio's own label as a Swift `Text` argument. A binding used to
        # be pasted inside the quotes, so the row rendered the characters
        # `@{label}`; a literal keeps the escaping it always had.
        def label_expression(text)
          bound_string(text) || "\"#{text.gsub('"', '\\"')}\""
        end

        # The radio glyph.
        #
        # `icon` / `selectedIcon` name asset images; without them the SF Symbol
        # pair is used, as before. `iconColor` replaces the hard-coded blue, and
        # reaches a custom asset only through template rendering — a tint applied
        # to an original-mode asset does nothing. `iconSize` needs .resizable()
        # to have any effect, because an SF Symbol otherwise scales with the
        # font rather than the frame.
        def add_radio_icon_lines(selected_expr)
          # snake_case rows (icon / selected_icon) are declared aliases the
          # dynamic path reads — the camelCase-only read left the declared
          # asset unrendered (d=166, 32 parity).
          icon = @component['icon']
          selected_icon = @component['selectedIcon'] || @component['selected_icon']
          size = @component['iconSize']
          icon_color = @component['iconColor'] ? get_swiftui_color(@component['iconColor']) : nil

          if icon || selected_icon
            on_name = selected_icon || icon
            off_name = icon || selected_icon
            add_line "Image(#{selected_expr} ? \"#{on_name}\" : \"#{off_name}\")"
            add_modifier_line ".renderingMode(.template)" if icon_color
            add_modifier_line ".resizable()"
            add_modifier_line ".aspectRatio(contentMode: .fit)"
          else
            add_line "Image(systemName: #{selected_expr} ? \"largecircle.fill.circle\" : \"circle\")"
            if size
              add_modifier_line ".resizable()"
              add_modifier_line ".aspectRatio(contentMode: .fit)"
            end
          end
          add_modifier_line ".frame(width: #{size}, height: #{size})" if size
          # checkedColor / uncheckedColor swap with the selection (the
          # CheckBox converter has taken the same pair since it was written);
          # iconColor stays the single-colour override, .blue the default.
          checked = @component['checkedColor'] ? get_swiftui_color(@component['checkedColor']) : nil
          unchecked = @component['uncheckedColor'] ? get_swiftui_color(@component['uncheckedColor']) : nil
          if checked || unchecked
            add_modifier_line ".foregroundColor(#{selected_expr} ? #{checked || icon_color || '.blue'} : #{unchecked || icon_color || '.gray'})"
          else
            add_modifier_line ".foregroundColor(#{icon_color || '.blue'})"
          end
        end
        
        def add_state_variable(name, type, default_value)
          @state_variables ||= []
          @state_variables << "@State private var #{name}: #{type} = #{default_value}"
        end
      end
    end
  end
end