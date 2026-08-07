# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class RadioConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          # In the single-radio shape the gap-bearing <label> IS the subtree
          # root, so a bound `spacing` has to reach @dynamic_styles BEFORE the
          # root's style attribute is rendered. Emitting a second style={{…}}
          # on the same tag would be a duplicate JSX attribute (TS17001) —
          # the Fx0375 shape SliderConverter documents. The group shape puts
          # the gap on inner labels the root's style cannot reach, and those
          # carry their own (see item_gap_parts).
          @root_gap_class = root_item_gap_class if (attributes['items'] || []).empty?
          style_attr = build_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr
          items = attributes['items'] || []
          text = attributes['text'] || attributes['label'] || ''
          group = attributes['group'] || extract_id || 'radioGroup'

          jsx = if items.any?
            generate_radio_group(indent, id_attr, class_name, style_attr, testid_attr, tag_attr, items, group, text)
          else
            generate_single_radio(indent, id_attr, class_name, style_attr, testid_attr, tag_attr, group, text)
          end

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]

          classes << 'flex flex-col gap-2' if (attributes['items'] || []).any?
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

        private

        def generate_radio_group(indent, id_attr, class_name, style_attr, testid_attr, tag_attr, items, group, label_text)
          selected_binding = build_selected_binding
          on_change = build_on_change
          disabled_attr = build_disabled_attr
          tint_color = attributes['tintColor']

          gap, gap_style = item_gap_parts
          items_jsx = items.map do |item|
            escaped_item = item.gsub('"', '&quot;')
            input_style = tint_color ? " style={{ accentColor: #{color_style_expr(tint_color)} }}" : ''
            state_attrs = build_state_attrs(selected_binding, on_change, escaped_item)
            <<~JSX.chomp
              #{indent_str(indent + 2)}<label className="flex items-center #{gap} cursor-pointer"#{gap_style}>
              #{indent_str(indent + 4)}<input type="radio" name="#{group}" value="#{escaped_item}"#{state_attrs}#{disabled_attr}#{input_style} />
              #{indent_str(indent + 4)}<span>#{item}</span>
              #{indent_str(indent + 2)}</label>
            JSX
          end.join("\n")

          label_jsx = if label_text && !label_text.empty?
                        "#{indent_str(indent + 2)}<span className=\"font-medium\">#{convert_text_binding(label_text)}</span>\n"
                      else
                        ''
                      end

          <<~JSX.chomp
            #{indent_str(indent)}<div#{id_attr} className="#{class_name}"#{style_attr}#{testid_attr}#{tag_attr}#{build_aria_disabled_attr}>
            #{label_jsx}#{items_jsx}
            #{indent_str(indent)}</div>
          JSX
        end

        def generate_single_radio(indent, id_attr, class_name, style_attr, testid_attr, tag_attr, group, text)
          selected_binding = build_selected_binding
          on_change = build_on_change
          disabled_attr = build_disabled_attr
          # `value` is the option's identity within the group and the node id is
          # only the fallback (sjui radio_converter reads the same order). Taking
          # the id unconditionally compared selectedValue against the node name,
          # so a single Radio could never be checked no matter what was declared
          # — the host's tsc caught it as a comparison of non-overlapping
          # literals.
          radio_value = attributes['value'] || extract_id || 'option'
          tint_color = attributes['tintColor']
          input_style = tint_color ? " style={{ accentColor: #{color_style_expr(tint_color)} }}" : ''

          state_attrs = build_state_attrs(selected_binding, on_change, radio_value)
          state_attrs = checked_attr if state_attrs.empty?

          # Custom icon radio: hidden input + state-swapped images (the kjui/
          # sjui icon path — 33 cross-effect: web rendered the native circle
          # for declared icons). 'selected_icon' is the declared snake alias.
          icon_off = attributes['icon']
          icon_on = attributes['selectedIcon'] || attributes['selected_icon']
          if icon_on || icon_off
            off_src = icon_off || icon_on
            on_src = icon_on || icon_off
            control_jsx =
              "<input type=\"radio\" name=\"#{group}\" value=\"#{radio_value}\"#{state_attrs}#{disabled_attr} className=\"peer sr-only\" />"               "<img src=\"#{off_src}\" alt=\"\" className=\"w-6 h-6 peer-checked:hidden\" />"               "<img src=\"#{on_src}\" alt=\"\" className=\"w-6 h-6 hidden peer-checked:block\" />"
            return <<~JSX.chomp
              #{indent_str(indent)}<label#{id_attr} className="#{class_name} flex items-center #{@root_gap_class}"#{style_attr}#{testid_attr}#{tag_attr}#{build_aria_disabled_attr}>
              #{indent_str(indent + 2)}#{control_jsx}
              #{indent_str(indent + 2)}<span>#{convert_text_binding(text)}</span>
              #{indent_str(indent)}</label>
            JSX
          end

          <<~JSX.chomp
            #{indent_str(indent)}<label#{id_attr} className="#{class_name} flex items-center #{@root_gap_class}"#{style_attr}#{testid_attr}#{tag_attr}#{build_aria_disabled_attr}>
            #{indent_str(indent + 2)}<input type="radio" name="#{group}" value="#{radio_value}"#{state_attrs}#{disabled_attr}#{input_style} />
            #{indent_str(indent + 2)}<span>#{convert_text_binding(text)}</span>
            #{indent_str(indent)}</label>
          JSX
        end

        # `spacing` — the gap between the radio control and its label text
        # (kjui reads the same attribute for the row arrangement). Default
        # keeps the historical gap-2 (8px).
        # Root-label shape. A bound value has no place in an arbitrary-value
        # class — it produced `gap-[@{v}px]`, which matches nothing — so it
        # folds into the root's own inline `gap` and the class falls back to
        # the historical default.
        def root_item_gap_class
          spacing = bound_length_style('gap', attributes['spacing'])
          spacing ? "gap-[#{spacing}px]" : 'gap-2'
        end

        # Inner-label shape: [class, style attribute]. The root's style
        # cannot reach these labels, so a bound gap becomes theirs.
        def item_gap_parts
          spacing = attributes['spacing']
          return [spacing ? "gap-[#{spacing}px]" : 'gap-2', ''] unless (expr = bound_value_expr(spacing))

          ['gap-2', style_attr_for({ 'gap' => "`${#{expr}}px`" })]
        end

        # A single radio with no group selection still honours `checked` —
        # the effect check measured the generated input carrying no checked
        # state at all (the fixture rendered identically to its control).
        # Same shape as ToggleConverter: literal -> defaultChecked,
        # binding -> controlled checked.
        def checked_attr
          checked = with_bind_fallback(attributes['checked'])
          return '' if checked.nil? || checked == false

          if has_binding?(checked)
            " checked={#{extract_binding_property(checked)}} readOnly"
          else
            ' defaultChecked'
          end
        end

        # Selected-state expression for the radio input.
        # - `selectedValue: "@{prop}"`  -> JS expression (data-prefixed property)
        # - `selectedValue: "Static"`  -> quoted string literal
        # - absent                      -> nil (uncontrolled input; the old code
        #   emitted a bare `selectedValue` identifier which is undefined at
        #   runtime and crashed the component on render)
        def build_selected_binding
          selected = with_bind_fallback(attributes['selectedValue'])
          return nil unless selected

          if has_binding?(selected)
            extract_binding_property(selected)
          else
            "\"#{selected.to_s.gsub('"', '&quot;')}\""
          end
        end

        # onChange handler expression, or nil when neither onValueChange nor a
        # selectedValue binding provides one (static/uncontrolled radio).
        def build_on_change
          handler = attributes['onValueChange']

          if handler && has_binding?(handler)
            extract_binding_property(handler)
          else
            # Generate setter from the raw binding name (without viewModel.data. prefix)
            selected = with_bind_fallback(attributes['selectedValue'])
            return nil unless selected && has_binding?(selected)

            raw_binding = extract_raw_binding_property(selected)
            setter_name = "set#{raw_binding[0].upcase}#{raw_binding[1..]}"
            add_viewmodel_data_prefix(setter_name)
          end
        end

        # checked / onChange attribute pair. Controlled inputs need onChange
        # (or readOnly) to satisfy React; static selections emit readOnly.
        # Data closure props are always optional (type_converter makes all
        # function types `| undefined`), so calls must be optional-chained.
        # The literal `selectedValue` behind a `build_selected_binding` result,
        # or nil when that result was a binding expression (`data.x`, unquoted).
        def static_selected_value(selected_binding)
          selected_binding[/\A"(.*)"\z/m, 1]
        end

        def build_state_attrs(selected_binding, on_change, value_literal)
          if selected_binding
            # A STATIC `selectedValue` puts a string literal on both sides of
            # the comparison, and TypeScript narrows each to its own literal
            # type — so `"Beta" === "Alpha"` is TS2367, "these types have no
            # overlap". That is an error inside an @generated file, which no
            # consumer can patch, and it fails the host typecheck.
            #
            # The converter knows the answer at codegen time, so it emits the
            # answer instead of the comparison. Only the BOUND form still
            # compares, and there the left side is a runtime value with no
            # literal type to narrow.
            static_selected = static_selected_value(selected_binding)
            checked =
              if static_selected
                " checked={#{static_selected == value_literal}}"
              else
                " checked={#{selected_binding} === \"#{value_literal}\"}"
              end
            if on_change
              "#{checked} onChange={() => #{on_change}?.(\"#{value_literal}\")}"
            else
              "#{checked} readOnly"
            end
          elsif on_change
            " onChange={() => #{on_change}?.(\"#{value_literal}\")}"
          else
            ''
          end
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
